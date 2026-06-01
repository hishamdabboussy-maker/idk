"""Signal scoring for Binance-listed spot coins.

Each coin gets:
  - pump_score (0..100): weighted TA components, with a per-component breakdown
  - reasons: human-readable "why" for the score (RSI, vol surge, range, etc.)
  - direction: LONG/SHORT bias (reversion or momentum mode)
  - target_pct / target_price: a measured % target (ATR- and range-derived)
  - whale_* : if a tracked Hyperliquid whale holds this coin, score is forced to
    100 (whale long, reversion/long bias) and the reason names the whale.

Transparent screener — not financial advice.
"""
from __future__ import annotations


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _target(c: dict, direction: str) -> tuple[float, float]:
    """Measured % target + absolute price.

    Base move = max(ATR%, a third of the 24h range). LONG targets up, SHORT
    targets down. Falls back to a modest 3% if no volatility data.
    """
    atr_pct = c.get("atr_pct", 0.0) or 0.0
    vol24 = c.get("volatility_24h", 0.0) or 0.0
    base = max(atr_pct * 1.5, vol24 / 3.0, 3.0)
    base = min(base, 25.0)  # cap to a believable single-move target
    price = c.get("price", 0.0)
    if direction == "SHORT":
        return -base, price * (1 - base / 100.0)
    return base, price * (1 + base / 100.0)


def score_coin(c: dict, bias_mode: str = "reversion", whale: dict | None = None) -> dict:
    rp = c.get("range_pos", 0.5)
    mom_recent = c.get("mom_recent", 0.0)
    rsi = c.get("rsi")
    surge_x = c.get("vol_surge", 0.0)
    vol24 = c.get("volatility_24h", 0.0)

    # --- components (0..1) ---------------------------------------------------
    surge = _clamp((surge_x - 1.0) / 3.0)                 # 1x->0, 4x+->1
    mom = _clamp(abs(mom_recent) / 5.0)                   # 5%+ candle -> full
    edge = _clamp(abs(rp - 0.5) / 0.5)                    # mid->0, extreme->1
    vol = _clamp(vol24 / 15.0)                            # 15% 24h range -> full
    # RSI extremity helps reversion: oversold/overbought = opportunity.
    rsi_ext = 0.0
    if rsi is not None:
        rsi_ext = _clamp(abs(rsi - 50.0) / 35.0)          # 50->0, <=15 or >=85 ->1

    score = 100.0 * (0.32 * surge + 0.24 * mom + 0.16 * edge + 0.13 * vol + 0.15 * rsi_ext)

    # --- direction -----------------------------------------------------------
    if bias_mode == "momentum":
        direction = "LONG" if (mom_recent > 0 and rp >= 0.55) else "SHORT" if (mom_recent < 0 and rp <= 0.45) else "—"
    else:  # reversion (default)
        direction = "LONG" if rp <= 0.45 else "SHORT" if rp >= 0.55 else "—"

    # --- reasons (the "why") -------------------------------------------------
    reasons: list[str] = []
    if surge_x >= 2.5:
        reasons.append(f"volume surge {surge_x:.1f}x (+{surge*100:.0f}pt)")
    elif surge_x >= 1.5:
        reasons.append(f"rising volume {surge_x:.1f}x")
    if rsi is not None:
        if rsi <= 30:
            reasons.append(f"RSI {rsi:.0f} oversold")
        elif rsi >= 70:
            reasons.append(f"RSI {rsi:.0f} overbought")
        else:
            reasons.append(f"RSI {rsi:.0f}")
    if rp <= 0.15:
        reasons.append(f"near 24h low ({rp*100:.0f}% of range)")
    elif rp >= 0.85:
        reasons.append(f"near 24h high ({rp*100:.0f}% of range)")
    if abs(mom_recent) >= 2:
        reasons.append(f"{mom_recent:+.1f}% last candle")
    if abs(c.get("sma_dist", 0.0)) >= 3:
        reasons.append(f"{c['sma_dist']:+.1f}% vs SMA20")
    if vol24 >= 10:
        reasons.append(f"{vol24:.0f}% 24h range")
    if c.get("chg_24h", 0.0) >= 20:
        reasons.append(f"already {c['chg_24h']:+.0f}% 24h")

    target_pct, target_price = _target(c, direction if direction != "—" else "LONG")

    out = {
        **c,
        "comp_surge": round(surge * 100),
        "comp_mom": round(mom * 100),
        "comp_edge": round(edge * 100),
        "comp_vol": round(vol * 100),
        "comp_rsi": round(rsi_ext * 100),
        "direction": direction,
        "target_pct": round(target_pct, 1),
        "target_price": target_price,
        "whale": False,
    }

    # --- whale override ------------------------------------------------------
    # A tracked Hyperliquid whale holding this coin is the strongest signal we
    # have -> force the score and lead the reasons with it.
    if whale:
        side = whale.get("side", "LONG")
        out["whale"] = True
        out["direction"] = side
        out["pump_score"] = 100.0 if side == "LONG" else 5.0
        tp, tpx = _target(c, side)
        out["target_pct"], out["target_price"] = round(tp, 1), tpx
        whale_reason = (
            f"🐋 whale {side} {whale.get('address','')} "
            f"${whale.get('position_value',0):,.0f}"
            + (f" @ {whale.get('leverage')}x" if whale.get('leverage') else "")
            + (f" · opened {whale['opened_age_h']:.0f}h ago" if whale.get("opened_age_h") is not None else "")
        )
        out["reasons"] = ", ".join([whale_reason] + reasons) if reasons else whale_reason
        return out

    out["pump_score"] = round(score, 1)
    out["reasons"] = ", ".join(reasons) if reasons else "low activity"
    return out


def score_all(
    coins: list[dict],
    min_quote_vol: float,
    max_results: int = 100,
    bias_mode: str = "reversion",
    whale_map: dict[str, dict] | None = None,
) -> list[dict]:
    """whale_map: {BASE_SYMBOL -> whale position dict} for tracked wallets."""
    whale_map = whale_map or {}
    out: list[dict] = []
    for c in coins:
        if c.get("quote_vol", 0.0) < min_quote_vol:
            continue
        out.append(score_coin(c, bias_mode=bias_mode, whale=whale_map.get(c.get("base", ""))))
    out.sort(key=lambda x: x["pump_score"], reverse=True)
    return out[:max_results]
