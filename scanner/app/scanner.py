"""Orchestrates a scan cycle: fetch -> score -> cache. Thread/async safe enough
for a single-process MVP (one writer, many readers of an immutable snapshot)."""
from __future__ import annotations

import time

import httpx

from .config import settings
from .scoring import score_all
from .sources import dexscreener, hyperliquid

# Immutable snapshot replaced atomically after each scan.
STORE: dict = {
    "updated_at": 0.0,
    "tokens": [],       # scored alt/micro-cap pairs (sorted by pump_score)
    "perp_heat": [],    # hyperliquid OI/funding table
    "whales": [],       # tracked wallet positions
    "scanning": False,
    "error": "",
}


async def run_scan() -> None:
    STORE["scanning"] = True
    err = ""
    try:
        async with httpx.AsyncClient() as client:
            raw = await dexscreener.fetch_all(client, settings.DEX_QUERIES)
            tokens = score_all(
                raw,
                min_liq=settings.MIN_LIQUIDITY_USD,
                chains=settings.CHAINS,
                max_age_h=settings.MAX_PAIR_AGE_HOURS,
            )
            heat = await hyperliquid.perp_heat(client)
            whales = (
                await hyperliquid.whale_positions(client, settings.HL_WHALE_ADDRESSES)
                if settings.HL_WHALE_ADDRESSES
                else []
            )
        STORE.update(
            {
                "updated_at": time.time(),
                "tokens": tokens,
                "perp_heat": heat,
                "whales": whales,
                "error": "",
            }
        )
    except Exception as e:  # never let the loop die
        err = f"{type(e).__name__}: {e}"
        STORE["error"] = err
    finally:
        STORE["scanning"] = False


def snapshot() -> dict:
    return STORE
