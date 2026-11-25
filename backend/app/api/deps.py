"""Dependencias comunes: contexto, sesión de base de datos y autenticación del panel."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.context import AppContext
from app.errors import AppError

COOKIE_NAME = "asistencia_admin"
_failures: dict[str, deque] = defaultdict(deque)


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def get_db(ctx: AppContext = Depends(get_ctx)) -> Iterator[Session]:
    db = ctx.session()
    try:
        yield db
    finally:
        db.close()


def _secret(ctx: AppContext) -> bytes:
    secret = getattr(ctx, "_session_secret", None)
    if secret is None:
        secret = (ctx.settings.session_secret or secrets.token_hex(32)).encode()
        ctx._session_secret = secret  # type: ignore[attr-defined]
    return secret


def make_token(ctx: AppContext) -> str:
    payload = {"exp": int(time.time()) + ctx.settings.admin_session_hours * 3600, "n": secrets.token_hex(8)}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(ctx), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(ctx: AppContext, token: str | None) -> bool:
    if not token or "." not in token:
        return False
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret(ctx), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, json.JSONDecodeError):
        return False
    return int(payload.get("exp", 0)) > time.time()


def check_password(ctx: AppContext, password: str, client: str) -> bool:
    window = _failures[client]
    now = time.time()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= 5:
        raise AppError("Demasiados intentos fallidos. Espera un minuto.", status_code=429, code="rate_limited")
    expected = ctx.settings.admin_password
    if not expected:
        raise AppError("ADMIN_PASSWORD no está configurada en .env (ejecuta scripts/setup.sh)", status_code=500)
    ok = hmac.compare_digest(password.encode(), expected.encode())
    if not ok:
        window.append(now)
    return ok


def require_admin(request: Request, ctx: AppContext = Depends(get_ctx)) -> str:
    if not verify_token(ctx, request.cookies.get(COOKIE_NAME)):
        raise AppError("Debes iniciar sesión en el panel", status_code=401, code="unauthorized")
    return "admin"
