"""API del kiosco (sin autenticación; el servidor solo escucha en 127.0.0.1)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import get_ctx
from app.context import AppContext
from app.errors import AppError
from app.fingerprint.base import SimulatedProvider
from app.models import Person
from app.timeutil import tz_name

router = APIRouter(prefix="/api/kiosk", tags=["kiosco"])

MAX_FRAME_BYTES = 3_000_000


class SessionIn(BaseModel):
    code: str | None = Field(default=None, max_length=40)


class CodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class SimulateIn(BaseModel):
    person_id: int | None = None
    level: Literal["high", "medium", "none", "bad_image"]


@router.get("/status")
def kiosk_status(ctx: AppContext = Depends(get_ctx)):
    fp = ctx.fingerprint_status()
    return {
        "engine": ctx.engines.status(),
        "enrolled_people": ctx.engines.index.person_count,
        "liveness_enabled": ctx.runtime.liveness_enabled,
        "liveness_timeout_seconds": ctx.runtime.liveness_timeout_seconds,
        "fallback_mode": ctx.runtime.fallback_mode,
        "fingerprint": {
            "provider": fp.get("provider"),
            "connected": fp.get("connected", False),
            "label": fp.get("label"),
            "simulated": fp.get("provider") == "simulated",
            "scan_enabled": fp.get("provider") == "as608" and fp.get("connected", False),
        },
        "timezone": tz_name(ctx.tz),
        "server_time": ctx.now().isoformat(),
    }


@router.post("/sessions")
def create_session(body: SessionIn | None = None, ctx: AppContext = Depends(get_ctx)):
    session = ctx.kiosk.create()
    if body and body.code:
        try:
            return session.handle_code(body.code)
        except AppError:
            ctx.kiosk.drop(session.id)
            raise
    return session.view()


@router.get("/sessions/{session_id}")
def get_session(session_id: str, ctx: AppContext = Depends(get_ctx)):
    return ctx.kiosk.get(session_id).view()


@router.post("/sessions/{session_id}/frames")
async def post_frame(session_id: str, request: Request, ctx: AppContext = Depends(get_ctx)):
    session = ctx.kiosk.get(session_id)
    data = await request.body()
    if not data:
        raise AppError("Frame vacío: envía una imagen JPEG en el cuerpo")
    if len(data) > MAX_FRAME_BYTES:
        raise AppError("El frame es demasiado grande (máx. 3 MB)", status_code=413)
    return await run_in_threadpool(session.handle_frame, data)


@router.post("/sessions/{session_id}/code")
def post_code(session_id: str, body: CodeIn, ctx: AppContext = Depends(get_ctx)):
    return ctx.kiosk.get(session_id).handle_code(body.code)


@router.post("/sessions/{session_id}/fingerprint/simulate")
def simulate_fingerprint(session_id: str, body: SimulateIn, ctx: AppContext = Depends(get_ctx)):
    provider = ctx.fingerprint
    if not isinstance(provider, SimulatedProvider):
        raise AppError("La simulación solo está disponible con FINGERPRINT_PROVIDER=simulated", status_code=409)
    session = ctx.kiosk.get(session_id)
    slot = None
    if body.person_id is not None:
        with ctx.session() as db:
            person = db.get(Person, body.person_id)
            if person is None:
                raise AppError("Persona no encontrada", status_code=404)
            slot = person.fingerprint_slot
    result = provider.simulate(body.person_id, slot, body.level)
    return session.handle_fingerprint(result)


@router.post("/sessions/{session_id}/fingerprint/scan")
async def scan_fingerprint(session_id: str, ctx: AppContext = Depends(get_ctx)):
    session = ctx.kiosk.get(session_id)
    result = await run_in_threadpool(ctx.fingerprint.scan, ctx.settings.fingerprint_scan_timeout)
    if result.status.value == "no_finger":
        view = session.view()
        view["fingerprint"] = {"status": "no_finger", "score": None, "level": "none"}
        return view
    return await run_in_threadpool(session.handle_fingerprint, result)


@router.delete("/sessions/{session_id}")
def cancel_session(session_id: str, ctx: AppContext = Depends(get_ctx)):
    try:
        view = ctx.kiosk.get(session_id).cancel()
    except AppError:
        return {"ok": True}
    ctx.kiosk.drop(session_id)
    return view


@router.get("/fingerprint/people")
def simulated_people(ctx: AppContext = Depends(get_ctx)):
    if not isinstance(ctx.fingerprint, SimulatedProvider):
        raise AppError("Solo disponible con la huella simulada", status_code=404)
    with ctx.session() as db:
        people = db.scalars(select(Person).where(Person.active.is_(True)).order_by(Person.last_name)).all()
        return [{"id": p.id, "code": p.code, "full_name": p.full_name} for p in people]
