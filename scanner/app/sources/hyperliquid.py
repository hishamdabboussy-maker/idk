"""Hyperliquid client (public info API).

  - metaAndAssetCtxs  -> per-coin open interest, funding, mark/prevDay px, volume
  - clearinghouseState -> positions for a specific wallet (whale tracking)

Market-wide perp heat needs no auth. Individual "whale positions" require known
wallet addresses (set HL_WHALE_ADDRESSES) since there is no public all-traders
feed. Never raises on network errors.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

URL = "https://api.hyperliquid.xyz/info"
_HEADERS = {"Content-Type": "application/json", "User-Agent": "whale-scanner/0.1"}


def _num(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


async def _post(client: httpx.AsyncClient, body: dict) -> Any:
    try:
        r = await client.post(URL, json=body, headers=_HEADERS, timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def perp_heat(client: httpx.AsyncClient) -> list[dict]:
    """Per-coin OI / funding / 24h change / day notional volume."""
    data = await _post(client, {"type": "metaAndAssetCtxs"})
    if not isinstance(data, list) or len(data) < 2:
        return []
    universe = (data[0] or {}).get("universe") or []
    ctxs = data[1] or []
    out: list[dict] = []
    for meta, ctx in zip(universe, ctxs):
        mark = _num(ctx.get("markPx"))
        prev = _num(ctx.get("prevDayPx"))
        chg = ((mark - prev) / prev * 100.0) if prev else 0.0
        oi_coins = _num(ctx.get("openInterest"))
        out.append(
            {
                "coin": meta.get("name", "?"),
                "mark_px": mark,
                "chg_24h": chg,
                "funding": _num(ctx.get("funding")) * 100.0,  # to %
                "oi_usd": oi_coins * mark,
                "day_ntl_vlm": _num(ctx.get("dayNtlVlm")),
                "max_leverage": meta.get("maxLeverage"),
            }
        )
    out.sort(key=lambda x: x["day_ntl_vlm"], reverse=True)
    return out


async def whale_positions(client: httpx.AsyncClient, addresses: list[str]) -> list[dict]:
    """Open positions for each tracked wallet."""
    rows: list[dict] = []
    for addr in addresses:
        data = await _post(client, {"type": "clearinghouseState", "user": addr})
        if not isinstance(data, dict):
            continue
        for ap in data.get("assetPositions") or []:
            pos = ap.get("position") or {}
            szi = _num(pos.get("szi"))
            if szi == 0:
                continue
            rows.append(
                {
                    "address": addr[:6] + "…" + addr[-4:],
                    "full_address": addr,
                    "coin": pos.get("coin", "?"),
                    "side": "LONG" if szi > 0 else "SHORT",
                    "size": abs(szi),
                    "entry_px": _num(pos.get("entryPx")),
                    "position_value": _num(pos.get("positionValue")),
                    "unrealized_pnl": _num(pos.get("unrealizedPnl")),
                    "leverage": (pos.get("leverage") or {}).get("value"),
                }
            )
    rows.sort(key=lambda x: x["position_value"], reverse=True)
    return rows


_LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
_lb_cache: list[str] = []
_lb_ts: float = 0.0
_LB_TTL = 1800.0  # refresh top-traders list every 30 min


async def top_traders(client: httpx.AsyncClient, top_n: int = 20) -> list[str]:
    """Auto-discover whale wallets from the public Hyperliquid leaderboard,
    ranked by account value. Cached. Returns a list of 0x addresses."""
    global _lb_cache, _lb_ts
    if _lb_cache and (time.time() - _lb_ts) < _LB_TTL:
        return _lb_cache[:top_n]
    try:
        r = await client.get(_LEADERBOARD_URL, headers={"User-Agent": "whale-scanner/0.3"}, timeout=20.0)
        r.raise_for_status()
        rows = (r.json() or {}).get("leaderboardRows") or []
    except Exception:
        return _lb_cache[:top_n]

    def acct_val(row: dict) -> float:
        return _num(row.get("accountValue"))

    rows.sort(key=acct_val, reverse=True)
    addrs = [row.get("ethAddress") for row in rows if row.get("ethAddress")]
    if addrs:
        _lb_cache = addrs
        _lb_ts = time.time()
    return _lb_cache[:top_n]
