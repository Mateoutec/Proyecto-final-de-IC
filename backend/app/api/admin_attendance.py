"""Panel: resumen del día, marcaciones, jornadas, fotos y exportaciones."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_ctx, get_db, require_admin
from app.api.serializers import event_dict, shift_dict
from app.context import AppContext
from app.domain import ENTRADA, EVENT_TYPES, LIVENESS_NOT_APPLICABLE, METHOD_MANUAL, METHODS, SALIDA, SHIFT_INCOMPLETE, SHIFT_OPEN
from app.errors import AppError, NotFound
from app.models import Area, AttendanceEvent, Person
from app.services import exports
from app.services.audit import audit
from app.services.shifts import load_shifts, totals_by_person
from app.timeutil import day_bounds_utc, hours_decimal, hours_hhmm, parse_local_datetime

router = APIRouter(prefix="/api/admin", tags=["panel: asistencia"], dependencies=[Depends(require_admin)])


def _today(ctx: AppContext) -> date:
    return ctx.now().astimezone(ctx.tz).date()


def _range(ctx: AppContext, date_from: date | None, date_to: date | None, default_days: int = 0) -> tuple[date, date]:
    today = _today(ctx)
    end = date_to or today
    start = date_from or (end - timedelta(days=default_days))
    if start > end:
        raise AppError("La fecha inicial es posterior a la final")
    if (end - start).days > 366:
        raise AppError("El rango máximo es de un año")
    return start, end


# ------------------------------------------------------------------ resumen
@router.get("/summary")
def summary(db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)):
    today = _today(ctx)
    now = ctx.now()
    max_h = ctx.runtime.max_shift_hours
    shifts_today = load_shifts(db, date_from=today, date_to=today, tz=ctx.tz, now=now, max_shift_hours=max_h)
    week = load_shifts(db, date_from=today - timedelta(days=6), date_to=today, tz=ctx.tz, now=now, max_shift_hours=max_h)
    lo, hi = day_bounds_utc(today, today, ctx.tz)
    events = list(
        db.scalars(
            select(AttendanceEvent)
            .options(joinedload(AttendanceEvent.person).joinedload(Person.area))
            .where(AttendanceEvent.ts >= lo, AttendanceEvent.ts < hi, AttendanceEvent.voided.is_(False))
            .order_by(AttendanceEvent.ts.desc())
        ).unique()
    )
    open_shifts = [s for s in week if s.status == SHIFT_OPEN]
    present_ids = {s.person_id for s in open_shifts}
    by_area: dict[str, dict] = defaultdict(lambda: {"present": 0, "entries": 0, "exits": 0})
    for ev in events:
        name = ev.person.area.name if ev.person.area else "Sin área"
        by_area[name]["entries" if ev.event_type == ENTRADA else "exits"] += 1
    for s in open_shifts:
        person = s.entry.person
        by_area[person.area.name if person.area else "Sin área"]["present"] += 1
    worked_today = sum(s.seconds or 0 for s in shifts_today if s.seconds)
    active_people = db.scalar(select(func.count()).select_from(Person).where(Person.active.is_(True)))
    return {
        "date": today.isoformat(),
        "counts": {
            "present": len(present_ids),
            "entries": sum(1 for e in events if e.event_type == ENTRADA),
            "exits": sum(1 for e in events if e.event_type == SALIDA),
            "incomplete_today": sum(1 for s in shifts_today if s.status == SHIFT_INCOMPLETE),
            "incomplete_week": sum(1 for s in week if s.status == SHIFT_INCOMPLETE),
            "active_people": active_people,
            "enrolled_people": ctx.engines.index.person_count,
            "hours_today": hours_decimal(worked_today),
            "hhmm_today": hours_hhmm(worked_today),
        },
        "present": [
            {
                "person_id": s.person_id,
                "person_code": s.entry.person.code,
                "person_name": s.entry.person.full_name,
                "area": s.entry.person.area.name if s.entry.person.area else None,
                "since": s.entry.ts.astimezone(ctx.tz).strftime("%H:%M"),
                "since_date": s.work_date.isoformat(),
                "elapsed_hhmm": hours_hhmm((now - s.entry.ts).total_seconds()),
            }
            for s in sorted(open_shifts, key=lambda s: s.entry.ts)
        ],
        "by_area": [{"area": k, **v} for k, v in sorted(by_area.items())],
        "recent": [event_dict(e, ctx.tz) for e in events[:12]],
        "engine": ctx.engines.status(),
    }


# ------------------------------------------------------------------ marcaciones
@router.get("/events")
def list_events(
    date_from: date | None = None,
    date_to: date | None = None,
    area_id: int | None = None,
    person_id: int | None = None,
    event_type: str | None = None,
    method: str | None = None,
    include_voided: bool = True,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
):
    start, end = _range(ctx, date_from, date_to, default_days=6)
    lo, hi = day_bounds_utc(start, end, ctx.tz)
    query = select(AttendanceEvent).where(AttendanceEvent.ts >= lo, AttendanceEvent.ts < hi)
    if area_id is not None:
        query = query.join(Person, Person.id == AttendanceEvent.person_id).where(Person.area_id == area_id)
    if person_id is not None:
        query = query.where(AttendanceEvent.person_id == person_id)
    if event_type:
        if event_type not in EVENT_TYPES:
            raise AppError("Tipo de marcación inválido")
        query = query.where(AttendanceEvent.event_type == event_type)
    if method:
        if method not in METHODS:
            raise AppError("Método inválido")
        query = query.where(AttendanceEvent.method == method)
    if not include_voided:
        query = query.where(AttendanceEvent.voided.is_(False))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.options(joinedload(AttendanceEvent.person).joinedload(Person.area))
        .order_by(AttendanceEvent.ts.desc(), AttendanceEvent.id.desc())
        .limit(min(max(limit, 1), 1000))
        .offset(max(offset, 0))
    ).unique()
    return {
        "items": [event_dict(e, ctx.tz) for e in items],
        "total": total,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
    }


class ManualEventIn(BaseModel):
    person_id: int
    event_type: Literal["ENTRADA", "SALIDA"]
    local_datetime: str = Field(min_length=10, max_length=40)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("el motivo es obligatorio (mínimo 3 caracteres)")
        return v


@router.post("/events/manual", status_code=201)
def add_manual_event(
    body: ManualEventIn, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)
):
    person = db.get(Person, body.person_id)
    if person is None:
        raise NotFound("Persona no encontrada")
    ts = parse_local_datetime(body.local_datetime, ctx.tz)
    if ts > ctx.now() + timedelta(minutes=5):
        raise AppError("No se pueden registrar marcaciones en el futuro")
    event = AttendanceEvent(
        person_id=person.id,
        ts=ts,
        event_type=body.event_type,
        method=METHOD_MANUAL,
        liveness=LIVENESS_NOT_APPLICABLE,
        manual_reason=body.reason,
        created_by=actor,
    )
    db.add(event)
    db.flush()
    audit(
        db, actor, "marcacion_manual", "event", event.id, person=person.code, event_type=body.event_type,
        local=body.local_datetime, reason=body.reason,
    )
    db.commit()
    db.refresh(event)
    return event_dict(db.scalar(select(AttendanceEvent).options(joinedload(AttendanceEvent.person)).where(AttendanceEvent.id == event.id)), ctx.tz)


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/events/{event_id}/void")
def void_event(
    event_id: int, body: VoidIn, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)
):
    event = db.scalar(select(AttendanceEvent).options(joinedload(AttendanceEvent.person)).where(AttendanceEvent.id == event_id))
    if event is None:
        raise NotFound("Marcación no encontrada")
    if event.voided:
        raise AppError("La marcación ya estaba anulada", status_code=409)
    reason = body.reason.strip()
    if len(reason) < 3:
        raise AppError("El motivo de anulación es obligatorio")
    event.voided = True
    event.void_reason = reason
    event.voided_at = ctx.now()
    event.voided_by = actor
    audit(db, actor, "marcacion_anulada", "event", event.id, person=event.person.code, reason=reason)
    db.commit()
    return event_dict(event, ctx.tz)


# ------------------------------------------------------------------ jornadas
@router.get("/shifts")
def list_shifts(
    date_from: date | None = None,
    date_to: date | None = None,
    area_id: int | None = None,
    person_id: int | None = None,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
):
    start, end = _range(ctx, date_from, date_to, default_days=6)
    shifts = load_shifts(
        db, date_from=start, date_to=end, tz=ctx.tz, now=ctx.now(), max_shift_hours=ctx.runtime.max_shift_hours,
        area_id=area_id, person_id=person_id,
    )
    totals = totals_by_person(shifts)
    people = {p.id: p for p in db.scalars(select(Person).options(joinedload(Person.area)).where(Person.id.in_(list(totals)))).unique()}
    return {
        "items": [shift_dict(s, ctx.tz) for s in reversed(shifts)],
        "totals": sorted(
            [
                {
                    "person_id": pid,
                    "person_code": people[pid].code,
                    "person_name": people[pid].full_name,
                    "area": people[pid].area.name if people[pid].area else None,
                    "days": t.days,
                    "hours": t.hours,
                    "hhmm": t.hhmm,
                    "incomplete": t.incomplete,
                    "open": t.open,
                }
                for pid, t in totals.items()
                if pid in people
            ],
            key=lambda r: r["person_name"],
        ),
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
    }


# ------------------------------------------------------------------ fotos (solo con sesión)
ALLOWED_ROOTS = ("captures", "enrollment", "calibration")


@router.get("/files/{rel_path:path}")
def get_file(rel_path: str, ctx: AppContext = Depends(get_ctx)):
    parts = Path(rel_path).parts
    if not parts or parts[0] not in ALLOWED_ROOTS or ".." in parts:
        raise NotFound("Archivo no encontrado")
    base = ctx.data_path.resolve()
    file = (base / rel_path).resolve()
    if base not in file.parents or not file.is_file():
        raise NotFound("Archivo no encontrado")
    return FileResponse(file, headers={"Cache-Control": "private, max-age=3600"})


# ------------------------------------------------------------------ exportación
@router.get("/export")
def export(
    kind: Literal["shifts", "events", "summary"],
    format: Literal["csv", "xlsx", "zip"] = "csv",
    date_from: date | None = None,
    date_to: date | None = None,
    area_id: int | None = None,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
    actor: str = Depends(require_admin),
):
    start, end = _range(ctx, date_from, date_to, default_days=30)
    if area_id is not None and db.get(Area, area_id) is None:
        raise AppError("El área seleccionada no existe")
    filters = exports.ExportFilters(start, end, area_id)
    now = ctx.now()
    if kind == "shifts":
        table = exports.shifts_table(db, filters, ctx.tz, now, ctx.runtime.max_shift_hours)
    elif kind == "events":
        table = exports.events_table(db, filters, ctx.tz)
    else:
        table = exports.summary_table(db, filters, ctx.tz, now, ctx.runtime.max_shift_hours)
    base = f"{table.name}_{start.isoformat()}_{end.isoformat()}"
    photos = 0
    if format == "csv":
        content = exports.to_csv(table, ctx.runtime.csv_delimiter)
        media, filename = "text/csv; charset=utf-8", f"{base}.csv"
    elif format == "xlsx":
        content = exports.to_xlsx(table, f"Asistencia — {table.name}")
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{base}.xlsx"
    else:
        if not table.photo_columns:
            raise AppError("El resumen por persona no tiene fotos: expórtalo como CSV o XLSX")
        content, photos = exports.to_zip(table, exports.to_csv(table, ctx.runtime.csv_delimiter), ctx.data_path)
        media, filename = "application/zip", f"{base}.zip"
    audit(
        db, actor, "exportacion", "export", kind, format=format, date_from=start.isoformat(), date_to=end.isoformat(),
        area_id=area_id, rows=len(table.rows), photos=photos,
    )
    db.commit()
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Rows": str(len(table.rows))},
    )
