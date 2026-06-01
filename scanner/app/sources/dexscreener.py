"""DexScreener client (public API, no key).

Endpoints used:
  - GET /latest/dex/search?q=<term>     -> pairs with volume/liquidity/priceChange/txns
  - GET /token-boosts/latest/v1         -> recently boosted tokens (often new/pumping)
  - GET /latest/dex/tokens/<addresses>  -> pairs for given token addresses

Returns normalised pair dicts; never raises on network errors (returns []).
"""
from __future__ import annotations

import time
from typing import Any

import httpx

BASE = "https://api.dexscreener.com"
_HEADERS = {"User-Agent": "whale-scanner/0.1 (+https://github.com)"}


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def normalise_pair(p: dict) -> dict | None:
    """Flatten a DexScreener pair into the fields the scorer needs."""
    base = p.get("baseToken") or {}
    if not base.get("address"):
        return None
    vol = p.get("volume") or {}
    chg = p.get("priceChange") or {}
    txns = p.get("txns") or {}
    liq = p.get("liquidity") or {}
    created_ms = p.get("pairCreatedAt")
    age_h = None
    if created_ms:
        age_h = max(0.0, (time.time() * 1000 - float(created_ms)) / 3_600_000.0)

    def tx(window: str) -> tuple[int, int]:
        w = txns.get(window) or {}
        return int(w.get("buys") or 0), int(w.get("sells") or 0)

    b1, s1 = tx("h1")
    b24, s24 = tx("h24")
    return {
        "chain": p.get("chainId", ""),
        "dex": p.get("dexId", ""),
        "symbol": base.get("symbol", "?"),
        "name": base.get("name", ""),
        "token_address": base.get("address", ""),
        "pair_address": p.get("pairAddress", ""),
        "price_usd": _num(p.get("priceUsd")),
        "liq_usd": _num(liq.get("usd")),
        "fdv": _num(p.get("fdv")),
        "market_cap": _num(p.get("marketCap")),
        "vol_m5": _num(vol.get("m5")),
        "vol_h1": _num(vol.get("h1")),
        "vol_h6": _num(vol.get("h6")),
        "vol_h24": _num(vol.get("h24")),
        "chg_m5": _num(chg.get("m5")),
        "chg_h1": _num(chg.get("h1")),
        "chg_h6": _num(chg.get("h6")),
        "chg_h24": _num(chg.get("h24")),
        "buys_h1": b1,
        "sells_h1": s1,
        "buys_h24": b24,
        "sells_h24": s24,
        "age_hours": age_h,
        "url": p.get("url", ""),
    }


async def _get_json(client: httpx.AsyncClient, path: str) -> Any:
    try:
        r = await client.get(BASE + path, headers=_HEADERS, timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def search(client: httpx.AsyncClient, term: str) -> list[dict]:
    data = await _get_json(client, f"/latest/dex/search?q={term}")
    pairs = (data or {}).get("pairs") or []
    out = [normalise_pair(p) for p in pairs]
    return [x for x in out if x]


async def boosted_tokens(client: httpx.AsyncClient) -> list[dict]:
    """Boosted tokens -> resolve to their pairs (cheap proxy for 'trending/new')."""
    data = await _get_json(client, "/token-boosts/latest/v1")
    if not isinstance(data, list):
        return []
    # group addresses by chain, fetch in batches of 30 (API limit)
    by_chain: dict[str, list[str]] = {}
    for t in data[:60]:
        addr = t.get("tokenAddress")
        chain = t.get("chainId")
        if addr and chain:
            by_chain.setdefault(chain, []).append(addr)

    out: list[dict] = []
    for chain, addrs in by_chain.items():
        for i in range(0, len(addrs), 30):
            batch = ",".join(addrs[i : i + 30])
            d = await _get_json(client, f"/latest/dex/tokens/{batch}")
            for p in (d or {}).get("pairs") or []:
                np = normalise_pair(p)
                if np:
                    out.append(np)
    return out


async def fetch_all(client: httpx.AsyncClient, queries: list[str]) -> list[dict]:
    """Crawl the configured search terms + boosted tokens, de-duped by pair."""
    seen: dict[str, dict] = {}
    collections: list[list[dict]] = [await boosted_tokens(client)]
    for q in queries:
        collections.append(await search(client, q))
    for coll in collections:
        for pair in coll:
            key = pair["pair_address"] or pair["token_address"]
            # keep the row with the most 24h volume if duplicated
            if key not in seen or pair["vol_h24"] > seen[key]["vol_h24"]:
                seen[key] = pair
    return list(seen.values())
