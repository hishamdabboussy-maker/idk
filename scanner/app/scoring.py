"""Signal scoring for alt / micro-cap pump potential and rug risk.

Everything here is transparent, public-data analytics — a screener, not a
guarantee. `pump_score` ranks *unusual activity / momentum*; `risk_score`
ranks *how easily this could be a trap*. Always read them together.
"""
from __future__ import annotations


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_pair(p: dict) -> dict:
    liq = p["liq_usd"]
    vol24 = p["vol_h24"]
    vol1 = p["vol_h1"]
    b1, s1 = p["buys_h1"], p["sells_h1"]
    age = p["age_hours"]

    # --- Pump-potential components (each 0..1) ------------------------------
    # 1) Volume acceleration: this hour vs the average hour of the last 24h.
    avg_hour = vol24 / 24.0 if vol24 > 0 else 0.0
    accel = _clamp((vol1 / avg_hour - 1.0) / 3.0) if avg_hour > 0 else 0.0

    # 2) Buy pressure in the last hour.
    tot1 = b1 + s1
    buy_ratio = (b1 / tot1) if tot1 > 0 else 0.5
    buy_press = _clamp((buy_ratio - 0.5) / 0.3)  # 0.5->0, 0.8+->1

    # 3) Short-term momentum (1h price change).
    mom = _clamp(p["chg_h1"] / 25.0)  # +25% h1 -> full

    # 4) Turnover (24h volume / liquidity): high = actively traded.
    turnover = _clamp((vol24 / liq) / 5.0) if liq > 0 else 0.0

    pump = 100.0 * (0.34 * accel + 0.24 * buy_press + 0.24 * mom + 0.18 * turnover)

    # --- Rug / trap risk (0..100, higher = riskier) -------------------------
    risk = 0.0
    notes: list[str] = []
    if liq < 10_000:
        risk += 35; notes.append("very low liquidity")
    elif liq < 30_000:
        risk += 18; notes.append("low liquidity")

    # Liquidity tiny vs valuation -> easy to dump.
    val = p["market_cap"] or p["fdv"]
    if val > 0 and liq > 0 and (liq / val) < 0.03:
        risk += 20; notes.append("thin liq vs mcap")

    if age is not None and age < 6:
        risk += 15; notes.append("very new (<6h)")

    if tot1 > 0 and buy_ratio < 0.4:
        risk += 15; notes.append("sell-dominated")

    if p["chg_h24"] > 300:
        risk += 20; notes.append("already +300% 24h (late)")

    risk = min(100.0, risk)
    risk_label = "HIGH" if risk >= 55 else "MED" if risk >= 30 else "LOW"

    return {
        **p,
        "buy_ratio_h1": round(buy_ratio, 3),
        "turnover": round((vol24 / liq) if liq > 0 else 0.0, 2),
        "pump_score": round(pump, 1),
        "risk_score": round(risk, 1),
        "risk_label": risk_label,
        "risk_notes": ", ".join(notes) if notes else "—",
    }


def score_all(pairs: list[dict], min_liq: float, chains: list[str], max_age_h: float) -> list[dict]:
    out: list[dict] = []
    for p in pairs:
        if chains and p["chain"] not in chains:
            continue
        if p["liq_usd"] < min_liq:
            continue
        if max_age_h and p["age_hours"] is not None and p["age_hours"] > max_age_h:
            continue
        out.append(score_pair(p))
    out.sort(key=lambda x: x["pump_score"], reverse=True)
    return out
