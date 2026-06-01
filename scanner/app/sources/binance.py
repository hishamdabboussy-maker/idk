"""Binance public market-data client (spot).

Uses the official public data mirror `data-api.binance.vision` by default
(no API key, works from restricted regions where api.binance.com returns 451),
with api.binance.com as a fallback.

Endpoints:
  - GET /api/v3/exchangeInfo   -> tradable symbols + status (cached)
  - GET /api/v3/ticker/24hr    -> 24h stats for every symbol (one call)
  - GET /api/v3/klines         -> recent candles for a symbol (volume surge / momentum)

Only returns Binance-listed pairs — no DEX / pump.fun tokens. Never raises on
network errors (returns [] / None).
"""
from __future__ import annotations

import time
from typing import Any

import httpx

BASES = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]
_HEADERS = {"User-Agent": "whale-scanner/0.2"}

# exchangeInfo cache (symbol -> dict), refreshed hourly
_info_cache: dict[str, dict] = {}
_info_ts: float = 0.0
_INFO_TTL = 3600.0


def _num(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


async def _get(client: httpx.AsyncClient, path: str) -> Any:
    """Try each base URL until one returns JSON."""
    for base in BASES:
        try:
            r = await client.get(base + path, headers=_HEADERS, timeout=15.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


async def tradable_usdt_symbols(client: httpx.AsyncClient) -> set[str]:
    """Set of spot USDT symbols whose status == TRADING (cached hourly)."""
    global _info_cache, _info_ts
    if _info_cache and (time.time() - _info_ts) < _INFO_TTL:
        return set(_info_cache.keys())
    data = await _get(client, "/api/v3/exchangeInfo")
    syms = (data or {}).get("symbols") or []
    out: dict[str, dict] = {}
    for s in syms:
        if (
            s.get("quoteAsset") == "USDT"
            and s.get("status") == "TRADING"
            and s.get("isSpotTradingAllowed", True)
        ):
            out[s["symbol"]] = s
    if out:
        _info_cache = out
        _info_ts = time.time()
    return set(_info_cache.keys())


def _is_leveraged(base: str) -> bool:
    # Skip leveraged tokens (UP/DOWN/BULL/BEAR) — noisy, not spot coins.
    return base.endswith(("UP", "DOWN", "BULL", "BEAR"))


async def tickers_24h(client: httpx.AsyncClient) -> list[dict]:
    """24h stats for all tradable USDT spot pairs, normalised."""
    allowed = await tradable_usdt_symbols(client)
    data = await _get(client, "/api/v3/ticker/24hr")
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for t in data:
        sym = t.get("symbol", "")
        if sym not in allowed:
            continue
        base = sym[:-4]  # strip USDT
        if _is_leveraged(base):
            continue
        last = _num(t.get("lastPrice"))
        hi = _num(t.get("highPrice"))
        lo = _num(t.get("lowPrice"))
        op = _num(t.get("openPrice"))
        rng_pos = ((last - lo) / (hi - lo)) if hi > lo else 0.5
        out.append(
            {
                "symbol": sym,
                "base": base,
                "price": last,
                "chg_24h": _num(t.get("priceChangePercent")),
                "quote_vol": _num(t.get("quoteVolume")),  # 24h USDT volume
                "trades": int(_num(t.get("count"))),
                "high_24h": hi,
                "low_24h": lo,
                "open_24h": op,
                "range_pos": rng_pos,                      # 0=at low, 1=at high
                "volatility_24h": ((hi - lo) / op * 100.0) if op > 0 else 0.0,
            }
        )
    return out


async def klines(client: httpx.AsyncClient, symbol: str, interval: str = "1h", limit: int = 24) -> list[list]:
    data = await _get(client, f"/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}")
    return data if isinstance(data, list) else []


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI on a list of closes."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    seed = deltas[:period]
    up = sum(d for d in seed if d > 0) / period
    down = -sum(d for d in seed if d < 0) / period
    for d in deltas[period:]:
        up = (up * (period - 1) + (d if d > 0 else 0.0)) / period
        down = (down * (period - 1) + (-d if d < 0 else 0.0)) / period
    if down == 0:
        return 100.0
    rs = up / down
    return 100.0 - 100.0 / (1.0 + rs)


def _atr_pct(ks: list[list], period: int = 14) -> float:
    """ATR as a % of the last close (volatility proxy)."""
    if len(ks) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(ks)):
        h, l, pc = _num(ks[i][2]), _num(ks[i][3]), _num(ks[i - 1][4])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    use = trs[-period:] if len(trs) >= period else trs
    atr = sum(use) / len(use) if use else 0.0
    last_close = _num(ks[-1][4])
    return (atr / last_close * 100.0) if last_close > 0 else 0.0


async def enrich_momentum(client: httpx.AsyncClient, rows: list[dict], interval: str = "1h") -> None:
    """Fetch recent klines per symbol and add TA: volume surge, recent momentum,
    RSI(14), ATR%, and distance from the SMA(20). Mutates rows in place."""
    for r in rows:
        ks = await klines(client, r["symbol"], interval=interval, limit=50)
        if len(ks) < 4:
            r["vol_surge"] = 0.0
            r["mom_recent"] = 0.0
            r["rsi"] = None
            r["atr_pct"] = 0.0
            r["sma_dist"] = 0.0
            continue
        # kline: [openT, open, high, low, close, volume, closeT, quoteVol, trades, ...]
        quote_vols = [_num(k[7]) for k in ks]
        closes = [_num(k[4]) for k in ks]
        last_qv = quote_vols[-1]
        prior = quote_vols[:-1]
        avg_qv = sum(prior) / len(prior) if prior else 0.0
        r["vol_surge"] = (last_qv / avg_qv) if avg_qv > 0 else 0.0
        c_open = _num(ks[-1][1])
        c_close = closes[-1]
        r["mom_recent"] = ((c_close - c_open) / c_open * 100.0) if c_open > 0 else 0.0
        r["rsi"] = _rsi(closes, 14)
        r["atr_pct"] = _atr_pct(ks, 14)
        sma_n = closes[-20:] if len(closes) >= 20 else closes
        sma = sum(sma_n) / len(sma_n) if sma_n else 0.0
        r["sma_dist"] = ((c_close - sma) / sma * 100.0) if sma > 0 else 0.0
