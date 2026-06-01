# Pump / Whale Scanner

A single-user web dashboard that scans crypto for **alt / micro-cap pump potential**
and **perp / whale activity**. Public-data analytics / screener — **not financial advice**.

- **Pump radar** — DexScreener pairs ranked by a transparent pump score
  (volume acceleration, 1h buy pressure, momentum, turnover).
- **Risk score** — flags low liquidity, thin liq vs market cap, very new, sell-dominated,
  already-pumped → LOW / MED / HIGH.
- **Perp heat** — Hyperliquid market-wide OI / funding / volume.
- **Whale tracking** — open positions for wallets in `HL_WHALE_ADDRESSES`.

---

## Run locally

```bash
cd scanner
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # set ADMIN_PASSWORD + SESSION_SECRET
python run.py                 # http://localhost:8000
```

---

## Get a public URL (free)

### Option A — Render (easiest, ~3 min)
1. Push this repo to GitHub (already done).
2. Go to <https://render.com> → **New +** → **Blueprint** → connect this repo.
   Render reads `scanner/render.yaml` automatically.
   *(Or: New + → Web Service → Root Directory `scanner` → Build `pip install -r requirements.txt` → Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.)*
3. In the service's **Environment** tab set `ADMIN_USERNAME` and `ADMIN_PASSWORD`
   (`SESSION_SECRET` is auto-generated).
4. Deploy → you get a live URL like `https://pump-whale-scanner.onrender.com`.

> Free tier sleeps after inactivity and cold-starts in ~30s. The background
> scanner only runs while the instance is awake — fine for an MVP.

### Option B — Railway
New Project → Deploy from repo → set Root Directory to `scanner` → add the
same env vars. Railway detects the `Procfile`.

### Option C — Docker (any host / VPS)
```bash
cd scanner
docker build -t scanner .
docker run -p 8000:8000 --env-file .env scanner
```

---

## Config (`.env`)
| Var | Meaning |
|-----|---------|
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | login credentials |
| `SESSION_SECRET` | long random string for cookie signing |
| `SCAN_INTERVAL_SECONDS` | refresh cadence (default 120) |
| `DEX_QUERIES` | comma-sep DexScreener search terms |
| `CHAINS` | e.g. `solana,ethereum,base` (blank = all) |
| `MIN_LIQUIDITY_USD` | filter illiquid pairs |
| `MAX_PAIR_AGE_HOURS` | ignore old pairs (0 = no limit) |
| `HL_WHALE_ADDRESSES` | comma-sep 0x wallets to track |

## Endpoints
- `/` dashboard (login required) · `/login` · `/logout`
- `/api/scan` (JSON snapshot) · `/api/rescan` (POST, force refresh) · `/healthz`
