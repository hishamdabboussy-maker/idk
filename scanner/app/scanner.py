"""Orchestrates a scan cycle: fetch Binance tickers -> shortlist -> enrich the
most active with klines -> score -> cache. Single writer, immutable snapshot."""
from __future__ import annotations

import time

import httpx

from .config import settings
from .scoring import score_all
from .sources import binance, hyperliquid

# Immutable snapshot replaced atomically after each scan.
STORE: dict = {
    "updated_at": 0.0,
    "coins": [],        # scored Binance spot coins (sorted by pump_score)
    "perp_heat": [],    # hyperliquid OI/funding table
    "whales": [],       # tracked wallet positions
    "scanning": False,
    "error": "",
}


async def run_scan() -> None:
    STORE["scanning"] = True
    try:
        async with httpx.AsyncClient() as client:
            # 1) one call: 24h stats for every tradable USDT spot pair
            tickers = await binance.tickers_24h(client)

            # 2) shortlist by 24h quote volume, then by 24h move, to bound
            #    how many per-symbol kline calls we make (rate-limit friendly)
            tickers = [t for t in tickers if t["quote_vol"] >= settings.MIN_QUOTE_VOL_USD]
            tickers.sort(key=lambda t: t["quote_vol"], reverse=True)
            shortlist = tickers[: settings.ENRICH_TOP_N]

            # 3) enrich shortlist with recent klines (volume surge + momentum)
            await binance.enrich_momentum(client, shortlist, interval=settings.KLINE_INTERVAL)

            # 4) Hyperliquid perp context + whale wallets.
            #    Use manually-tracked wallets if set, else auto-discover the
            #    top traders from the public leaderboard.
            heat = await hyperliquid.perp_heat(client)
            addrs = settings.HL_WHALE_ADDRESSES
            if not addrs and settings.WHALE_AUTODISCOVER:
                addrs = await hyperliquid.top_traders(client, settings.WHALE_TOP_N)
            whales = await hyperliquid.whale_positions(client, addrs, recent_days=settings.WHALE_RECENT_DAYS) if addrs else []
            # only treat sizeable positions as whale signals
            whales = [w for w in whales if w.get("position_value", 0) >= settings.WHALE_MIN_USD]

            # Build a {coin -> strongest whale position} map so the scorer can
            # flag/boost coins that tracked whales are actually holding.
            whale_map: dict[str, dict] = {}
            for w in whales:
                coin = w.get("coin", "")
                cur = whale_map.get(coin)
                if cur is None or w.get("position_value", 0) > cur.get("position_value", 0):
                    whale_map[coin] = w

            fa = {
                "account": settings.ACCOUNT_SIZE_USD,
                "risk_pct": settings.RISK_PER_TRADE_PCT,
                "max_daily": settings.MAX_DAILY_LOSS_PCT,
                "max_dd": settings.MAX_TOTAL_DD_PCT,
                "max_lev": settings.MAX_LEVERAGE,
                "min_rr": settings.MIN_RR,
                "max_hold": settings.MAX_HOLD_HOURS,
            }

            coins = score_all(
                shortlist,
                min_quote_vol=settings.MIN_QUOTE_VOL_USD,
                max_results=settings.MAX_RESULTS,
                bias_mode=settings.BIAS_MODE,
                whale_map=whale_map,
                kline_interval=settings.KLINE_INTERVAL,
                fa=fa,
            )

        STORE.update(
            {
                "updated_at": time.time(),
                "coins": coins,
                "perp_heat": heat,
                "whales": whales,
                "error": "",
            }
        )
    except Exception as e:  # never let the loop die
        STORE["error"] = f"{type(e).__name__}: {e}"
    finally:
        STORE["scanning"] = False


def snapshot() -> dict:
    return STORE
