"""Signal scoring for Binance-listed spot coins.

Binance pairs are already vetted/liquid, so the old DEX rug-risk model is
dropped. Instead we rank coins by *unusual activity* that precedes moves:
volume surge (recent vs typical), short-term momentum, where price sits in the
24h range, and overall volatility. Transparent screener — not financial advice.
"""
from __future__ import annotations


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_coin(c: dict) -> dict:
    # --- components (0..1) ---------------------------------------------------
    # 1) Volume surge: last 1h candle quote-vol vs avg of prior 23h.
    surge = _clamp((c.get("vol_surge", 0.0) - 1.0) / 3.0)  # 1x->0, 4x+->1

    # 2) Recent momentum (last candle % move), direction-aware.
    mom_recent = c.get("mom_recent", 0.0)
    mom = _clamp(abs(mom_recent) / 5.0)  # 5%+ in one candle -> full

    # 3) Position in 24h range: breakouts (near high) or reclaims (near low).
    rp = c.get("range_pos", 0.5)
    edge = _clamp(abs(rp - 0.5) / 0.5)  # mid->0, at high/low->1

    # 4) Volatility: more range = more opportunity (and risk).
    vol = _clamp(c.get("volatility_24h", 0.0) / 15.0)  # 15% 24h range -> full

    score = 100.0 * (0.40 * surge + 0.28 * mom + 0.17 * edge + 0.15 * vol)

    # Directional read for the signal.
    if mom_recent > 0 and rp >= 0.55:
        direction = "LONG"
    elif mom_recent < 0 and rp <= 0.45:
        direction = "SHORT"
    else:
        direction = "—"

    # Plain-language tags.
    tags: list[str] = []
    if c.get("vol_surge", 0.0) >= 2.5:
        tags.append("vol surge")
    if rp >= 0.9:
        tags.append("near 24h high")
    elif rp <= 0.1:
        tags.append("near 24h low")
    if abs(mom_recent) >= 3:
        tags.append(f"{mom_recent:+.1f}% last 1h")
    if c.get("chg_24h", 0.0) >= 20:
        tags.append("already +20% 24h")

    return {
        **c,
        "pump_score": round(score, 1),
        "direction": direction,
        "tags": ", ".join(tags) if tags else "—",
    }


def score_all(coins: list[dict], min_quote_vol: float, max_results: int = 100) -> list[dict]:
    out: list[dict] = []
    for c in coins:
        if c.get("quote_vol", 0.0) < min_quote_vol:
            continue
        out.append(score_coin(c))
    out.sort(key=lambda x: x["pump_score"], reverse=True)
    return out[:max_results]
