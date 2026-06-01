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
        # strip inline comments and surrounding quotes
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
    DEX_QUERIES: list[str] = _csv("DEX_QUERIES", "SOL/USDC,WETH/USDC,bonk,pepe")
    CHAINS: list[str] = _csv("CHAINS", "solana,ethereum,base")
    MIN_LIQUIDITY_USD: float = float(os.environ.get("MIN_LIQUIDITY_USD", "15000"))
    MAX_PAIR_AGE_HOURS: float = float(os.environ.get("MAX_PAIR_AGE_HOURS", "720"))

    HL_WHALE_ADDRESSES: list[str] = _csv("HL_WHALE_ADDRESSES", "")
    USE_RUGCHECK: bool = os.environ.get("USE_RUGCHECK", "false").lower() == "true"


settings = Settings()
