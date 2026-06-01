"""FastAPI app: login + dashboard + JSON API + background scan loop."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import auth, scanner
from .config import settings

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Whale / Alt Pump Scanner", version="0.1")
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_scan_task: asyncio.Task | None = None


async def _scan_loop() -> None:
    # First scan immediately, then on the configured interval.
    while True:
        await scanner.run_scan()
        await asyncio.sleep(max(30, settings.SCAN_INTERVAL_SECONDS))


@app.on_event("startup")
async def _startup() -> None:
    global _scan_task
    _scan_task = asyncio.create_task(_scan_loop())


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if auth.is_authed(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    if auth.check_credentials(username, password):
        request.session["user"] = username
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid credentials"}, status_code=401
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    redirect = auth.require_login(request)
    if redirect:
        return redirect
    snap = scanner.snapshot()
    age = int(time.time() - snap["updated_at"]) if snap["updated_at"] else None
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "coins": snap["coins"][:80],
            "heat": snap["perp_heat"][:25],
            "whales": snap["whales"][:40],
            "updated_age": age,
            "scanning": snap["scanning"],
            "error": snap["error"],
            "interval": settings.SCAN_INTERVAL_SECONDS,
            "min_vol": settings.MIN_QUOTE_VOL_USD,
            "kline_interval": settings.KLINE_INTERVAL,
            "bias_mode": settings.BIAS_MODE,
            "fa": {
                "account": settings.ACCOUNT_SIZE_USD,
                "risk_pct": settings.RISK_PER_TRADE_PCT,
                "max_daily": settings.MAX_DAILY_LOSS_PCT,
                "max_dd": settings.MAX_TOTAL_DD_PCT,
                "max_lev": settings.MAX_LEVERAGE,
                "min_rr": settings.MIN_RR,
            },
        },
    )


@app.get("/api/scan")
async def api_scan(request: Request):
    if not auth.is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    snap = scanner.snapshot()
    return {
        "updated_at": snap["updated_at"],
        "scanning": snap["scanning"],
        "error": snap["error"],
        "coins": snap["coins"][:100],
        "perp_heat": snap["perp_heat"][:50],
        "whales": snap["whales"],
    }


@app.post("/api/rescan")
async def api_rescan(request: Request):
    if not auth.is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    asyncio.create_task(scanner.run_scan())
    return {"ok": True}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "updated_at": scanner.snapshot()["updated_at"]}
