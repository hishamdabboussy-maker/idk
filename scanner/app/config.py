"""Configuration loaded from environment / .env (no external deps)."""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader so we don't pull in python-dotenv."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.split("#", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv()


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


class Settings:
    ADMIN_USERNAME: str = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.environ.get("ADMIN_PASSWORD", "changeme")
    SESSION_SECRET: str = os.environ.get("SESSION_SECRET", "dev-insecure-secret-change-me")

    SCAN_INTERVAL_SECONDS: int = int(os.environ.get("SCAN_INTERVAL_SECONDS", "120"))

    # Binance spot scanning
    MIN_QUOTE_VOL_USD: float = float(os.environ.get("MIN_QUOTE_VOL_USD", "2000000"))  # 24h USDT vol floor
    ENRICH_TOP_N: int = int(os.environ.get("ENRICH_TOP_N", "120"))   # how many symbols to pull klines for
    MAX_RESULTS: int = int(os.environ.get("MAX_RESULTS", "100"))
    KLINE_INTERVAL: str = os.environ.get("KLINE_INTERVAL", "1h")
    # Directional read: "reversion" (near low=LONG / near high=SHORT) or
    # "momentum" (near high+rising=LONG / near low+falling=SHORT).
    BIAS_MODE: str = os.environ.get("BIAS_MODE", "reversion").strip().lower()

    # --- Funded / prop account risk model -------------------------------------
    # The scanner sizes each idea against these so it respects challenge rules.
    ACCOUNT_SIZE_USD: float = float(os.environ.get("ACCOUNT_SIZE_USD", "100000"))
    RISK_PER_TRADE_PCT: float = float(os.environ.get("RISK_PER_TRADE_PCT", "0.5"))  # % of account risked per trade
    MAX_DAILY_LOSS_PCT: float = float(os.environ.get("MAX_DAILY_LOSS_PCT", "4"))    # prop daily loss limit
    MAX_TOTAL_DD_PCT: float = float(os.environ.get("MAX_TOTAL_DD_PCT", "8"))        # prop max drawdown
    MAX_LEVERAGE: float = float(os.environ.get("MAX_LEVERAGE", "5"))                # firm leverage cap
    MIN_RR: float = float(os.environ.get("MIN_RR", "1.5"))                          # reject setups below this R:R
    MAX_HOLD_HOURS: float = float(os.environ.get("MAX_HOLD_HOURS", "0"))            # flag holds longer than this (0=off; e.g. news/overnight rules)

    # Hyperliquid whale wallets (optional)
    HL_WHALE_ADDRESSES: list[str] = _csv("HL_WHALE_ADDRESSES", "")
    # Auto-discover whales from the public leaderboard when none are listed.
    WHALE_AUTODISCOVER: bool = os.environ.get("WHALE_AUTODISCOVER", "true").lower() == "true"
    WHALE_TOP_N: int = int(os.environ.get("WHALE_TOP_N", "25"))      # leaderboard wallets to scan
    WHALE_MIN_USD: float = float(os.environ.get("WHALE_MIN_USD", "250000"))  # min position to count
    WHALE_RECENT_DAYS: float = float(os.environ.get("WHALE_RECENT_DAYS", "2"))  # only positions opened/added within N days (0=any)


settings = Settings()
