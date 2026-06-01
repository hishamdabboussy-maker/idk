# Binance Spot / Whale Scanner

A single-user web dashboard that scans **Binance-listed USDT spot pairs** for
unusual activity, plus perp / whale context from Hyperliquid. Only Binance
coins — no DEX / pump.fun tokens. Public-data analytics / screener —
**not financial advice**.

- **Binance spot radar** — every tradable USDT pair, ranked by an activity score
  (volume surge vs typical, short-term momentum, position in 24h range, volatility).
- **Directional bias** — LONG / SHORT read from momentum + range position.
- **Perp heat** — Hyperliquid market-wide OI / funding / volume.
- **Whale tracking** — open positions for wallets in `HL_WHALE_ADDRESSES`.

Data source: Binance public market data via `data-api.binance.vision`
(no API key; works from regions where `api.binance.com` is geo-blocked),
with `api.binance.com` as a fallback.

---

## Run locally

```bash
cd scanner
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # set ADMIN_PASSWORD + SESSION_SECRET
python run.py                 # http://localhost:8000
```

## Deploy a public URL (Render)
- **New + → Blueprint** → connect this repo. It reads `render.yaml`
  (root) or set Blueprint Path to `scanner/render.yaml`. Both use `rootDir: scanner`.
- Set `ADMIN_USERNAME` + `ADMIN_PASSWORD` in the service Environment tab
  (`SESSION_SECRET` auto-generates). You get `https://<name>.onrender.com`.

## Config (`.env`)
| Var | Meaning |
|-----|---------|
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | login credentials |
| `SESSION_SECRET` | long random string for cookie signing |
| `SCAN_INTERVAL_SECONDS` | refresh cadence (default 120) |
| `MIN_QUOTE_VOL_USD` | ignore pairs below this 24h USDT volume (default 2,000,000) |
| `ENRICH_TOP_N` | how many top-volume symbols get kline enrichment (default 120) |
| `MAX_RESULTS` | rows kept after scoring (default 100) |
| `KLINE_INTERVAL` | candle interval for surge/momentum: `15m`, `1h`, `4h` |
| `HL_WHALE_ADDRESSES` | comma-sep 0x wallets to track |

## Endpoints
- `/` dashboard (login required) · `/login` · `/logout`
- `/api/scan` (JSON snapshot) · `/api/rescan` (POST) · `/healthz`

## Scoring (transparent)
`score = 40% volume-surge + 28% recent momentum + 17% range-edge + 15% volatility`
- **volume surge** = last `KLINE_INTERVAL` candle quote-volume ÷ average of prior 23
- **momentum** = % move of the last candle
- **range edge** = how far price sits from the middle of the 24h range (breakout/reclaim)
- **volatility** = 24h high-low range as % of open
