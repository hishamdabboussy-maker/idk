"""Tiny session-based auth for the single-user MVP.

Credentials come from .env (ADMIN_USERNAME / ADMIN_PASSWORD). Session is a
signed cookie via Starlette's SessionMiddleware. Harden before any public
deployment (per-user accounts, hashed passwords, rate limiting, HTTPS-only).
"""
from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import RedirectResponse

from .config import settings


def check_credentials(username: str, password: str) -> bool:
    u_ok = hmac.compare_digest(username or "", settings.ADMIN_USERNAME)
    p_ok = hmac.compare_digest(password or "", settings.ADMIN_PASSWORD)
    return u_ok and p_ok


def is_authed(request: Request) -> bool:
    return bool(request.session.get("user"))


def require_login(request: Request) -> RedirectResponse | None:
    if not is_authed(request):
        return RedirectResponse(url="/login", status_code=302)
    return None
