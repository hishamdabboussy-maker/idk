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

            coins = score_all(
                shortlist,
                min_quote_vol=settings.MIN_QUOTE_VOL_USD,
                max_results=settings.MAX_RESULTS,
                bias_mode=settings.BIAS_MODE,
            )

            # 4) Hyperliquid perp context + optional whale wallets
            heat = await hyperliquid.perp_heat(client)
            whales = (
                await hyperliquid.whale_positions(client, settings.HL_WHALE_ADDRESSES)
                if settings.HL_WHALE_ADDRESSES
                else []
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
