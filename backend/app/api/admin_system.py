"""Panel: inicio de sesión, configuración, re-indexado, calibración, auditoría y salud."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import COOKIE_NAME, check_password, get_ctx, get_db, make_token, require_admin, verify_token
from app.api.serializers import file_url
from app.context import AppContext
from app.errors import AppError
from app.face.insightface_engine import DET_FILE, REC_FILE
from app.face.sface_engine import SFACE_FILE, YUNET_FILE
from app.models import AuditLog
from app.services import calibration, enrollment
from app.services.audit import ACTION_LABELS, audit
from app.services.runtime_config import LABELS
from app.timeutil import day_bounds_utc, iso_local, tz_name

public = APIRouter(tags=["salud y sesión"])
router = APIRouter(prefix="/api/admin", tags=["panel: sistema"], dependencies=[Depends(require_admin)])


@public.get("/api/health")
def health(ctx: AppContext = Depends(get_ctx)):
    engine = ctx.engines.status()
    fp = ctx.fingerprint_status()
    return {
        "status": "ok" if engine["ready"] else "degraded",
        "version": __version__,
        "face_engine": engine["active"],
        "face_engine_requested": engine["requested"],
        "face_engine_fallback": engine["fallback"],
        "face_engine_error": engine["error"],
        "enrolled_people": engine["enrolled_people"],
        "fingerprint": {"provider": fp.get("provider"), "connected": fp.get("connected", False), "label": fp.get("label")},
        "liveness_enabled": ctx.runtime.liveness_enabled,
        "timezone": tz_name(ctx.tz),
        "time": ctx.now().isoformat(),
    }


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@public.post("/api/admin/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)):
    client = request.client.host if request.client else "local"
    if not check_password(ctx, body.password, client):
        audit(db, "anónimo", "login_fallido", "session", None, client=client)
        db.commit()
        raise AppError("Contraseña incorrecta", status_code=401, code="bad_password")
    response.set_cookie(
        COOKIE_NAME,
        make_token(ctx),
        httponly=True,
        samesite="strict",
        secure=False,  # localhost por HTTP
        max_age=ctx.settings.admin_session_hours * 3600,
        path="/",
    )
    audit(db, "admin", "login", "session", None, client=client)
    db.commit()
    return {"ok": True}


@public.post("/api/admin/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@public.get("/api/admin/me")
def me(request: Request, ctx: AppContext = Depends(get_ctx)):
    return {"authenticated": verify_token(ctx, request.cookies.get(COOKIE_NAME))}


# ------------------------------------------------------------------ configuración
def _models_present(ctx: AppContext) -> dict[str, bool]:
    m = ctx.settings.models_path
    return {
        "insightface": (m / "buffalo_l" / DET_FILE).exists() and (m / "buffalo_l" / REC_FILE).exists(),
        "sface": (m / "opencv" / YUNET_FILE).exists() and (m / "opencv" / SFACE_FILE).exists(),
        "fake": True,
    }


@router.get("/settings")
def get_settings(ctx: AppContext = Depends(get_ctx)):
    s = ctx.settings
    present = _models_present(ctx)
    return {
        "values": ctx.runtime.model_dump(),
        "labels": LABELS,
        "engine": ctx.engines.status(),
        "engines": [
            {"name": "insightface", "label": "InsightFace buffalo_l (por defecto, uso no comercial)", "models": present["insightface"]},
            {"name": "sface", "label": "OpenCV YuNet + SFace (respaldo, Apache-2.0)", "models": present["sface"]},
        ],
        "fingerprint": ctx.fingerprint_status(),
        "undecryptable_templates": ctx.undecryptable_templates,
        "env": {
            "timezone": tz_name(ctx.tz),
            "consensus": f"{s.consensus_required} de {s.consensus_window} frames",
            "max_identify_frames": s.max_identify_frames,
            "min_face_ratio": s.min_face_ratio,
            "min_brightness": s.min_brightness,
            "max_brightness": s.max_brightness,
            "fingerprint_provider": s.fingerprint_provider,
            "fingerprint_port": s.fingerprint_port,
            "fingerprint_baudrate": s.fingerprint_baudrate,
            "fingerprint_high_score": s.fingerprint_high_score,
            "fingerprint_medium_score": s.fingerprint_medium_score,
            "data_dir": str(ctx.data_path),
        },
    }


class SettingsIn(BaseModel):
    changes: dict[str, Any]


@router.put("/settings")
async def update_settings(body: SettingsIn, ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)):
    await run_in_threadpool(ctx.update_runtime, body.changes, actor)
    return get_settings(ctx)


class ReindexIn(BaseModel):
    engine: str | None = None


@router.post("/reindex")
async def reindex(body: ReindexIn | None = None, ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)):
    engine = body.engine if body else None
    if engine not in (None, "insightface", "sface", "fake"):
        raise AppError("Motor inválido")
    return await run_in_threadpool(enrollment.reindex, ctx, engine, actor)


def _with_urls(summary: dict | None) -> dict | None:
    if summary is None:
        return None
    return {**summary, "urls": {k: file_url(v) for k, v in summary.get("files", {}).items()}}


@router.post("/calibration")
async def run_calibration(ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)):
    return _with_urls(await run_in_threadpool(calibration.run_calibration, ctx, actor))


@router.get("/calibration/latest")
def latest_calibration(ctx: AppContext = Depends(get_ctx)):
    return {"result": _with_urls(calibration.latest_calibration(ctx))}


# ------------------------------------------------------------------ auditoría
@router.get("/audit")
def list_audit(
    action: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if date_from or date_to:
        today = ctx.now().astimezone(ctx.tz).date()
        lo, hi = day_bounds_utc(date_from or date(2000, 1, 1), date_to or today, ctx.tz)
        query = query.where(AuditLog.ts >= lo, AuditLog.ts < hi)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(min(max(limit, 1), 500)).offset(max(offset, 0)))
    return {
        "items": [
            {
                "id": r.id,
                "local": iso_local(r.ts, ctx.tz),
                "actor": r.actor,
                "action": r.action,
                "action_label": ACTION_LABELS.get(r.action, r.action),
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "details": json.loads(r.details) if r.details else None,
            }
            for r in rows
        ],
        "total": total,
        "actions": [{"key": k, "label": v} for k, v in ACTION_LABELS.items()],
    }
