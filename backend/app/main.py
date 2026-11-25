"""Aplicación FastAPI: API + build del frontend en http://localhost:8000."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api import admin_attendance, admin_people, admin_system, kiosk
from app.config import PROJECT_ROOT, Settings
from app.context import AppContext
from app.errors import install_error_handlers

log = logging.getLogger("app.main")

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

_MISSING_FRONTEND = """<!doctype html><html lang="es"><meta charset="utf-8"><title>Asistencia</title>
<body style="font-family:system-ui;padding:3rem;max-width:40rem">
<h1>Frontend no compilado</h1><p>Ejecuta <code>scripts/setup.sh</code> (o <code>npm run build</code> en
<code>frontend/</code>) y recarga. La API está disponible en <a href="/docs">/docs</a>.</p></body></html>"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not hasattr(app.state, "ctx"):
            app.state.ctx = AppContext(settings)
        ctx = app.state.ctx
        status = ctx.engines.status()
        log.info(
            "Servidor listo. Motor facial: %s%s. Huella: %s",
            status["active"],
            " (respaldo)" if status["fallback"] else "",
            ctx.fingerprint.name,
        )
        yield
        ctx.close()

    app = FastAPI(title="Asistencia Biométrica", version=__version__, lifespan=lifespan)
    extra_hosts = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver", *extra_hosts])
    install_error_handlers(app)

    @app.middleware("http")
    async def _no_store_api(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/") and "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    app.include_router(admin_system.public)
    app.include_router(kiosk.router)
    app.include_router(admin_people.router)
    app.include_router(admin_attendance.router)
    app.include_router(admin_system.router)

    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Recurso no encontrado", "code": "http_404"})
        index = FRONTEND_DIST / "index.html"
        if not index.exists():
            return HTMLResponse(_MISSING_FRONTEND, status_code=503)
        candidate = (FRONTEND_DIST / full_path).resolve()
        if full_path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app() if __name__ != "__main__" else None
