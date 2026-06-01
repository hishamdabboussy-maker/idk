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

    # Hyperliquid whale wallets (optional)
    HL_WHALE_ADDRESSES: list[str] = _csv("HL_WHALE_ADDRESSES", "")


settings = Settings()
