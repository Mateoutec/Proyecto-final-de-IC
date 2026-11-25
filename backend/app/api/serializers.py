"""Conversión de modelos a JSON para la API."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Area, AttendanceEvent, FaceTemplate, Person
from app.services.shifts import Shift
from app.timeutil import fmt_date, fmt_time, iso_local


def file_url(rel_path: str | None) -> str | None:
    return f"/api/admin/files/{rel_path}" if rel_path else None


def area_dict(area: Area, people_count: int | None = None) -> dict:
    return {
        "id": area.id,
        "name": area.name,
        "description": area.description,
        "people_count": people_count,
    }


def template_counts(db: Session, person_ids: list[int] | None = None) -> dict[int, dict[str, int]]:
    query = select(FaceTemplate.person_id, FaceTemplate.engine, func.count()).group_by(
        FaceTemplate.person_id, FaceTemplate.engine
    )
    if person_ids is not None:
        query = query.where(FaceTemplate.person_id.in_(person_ids))
    out: dict[int, dict[str, int]] = defaultdict(dict)
    for pid, engine, count in db.execute(query):
        out[pid][engine] = count
    return out


def person_dict(person: Person, counts: dict[str, int], active_engine: str | None, tz) -> dict:
    return {
        "id": person.id,
        "code": person.code,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": person.full_name,
        "area_id": person.area_id,
        "area": person.area.name if person.area else None,
        "position": person.position,
        "email": person.email,
        "active": person.active,
        "consent_signed": person.consent_signed,
        "consent_date": fmt_date(person.consent_date, tz) if person.consent_date else None,
        "fingerprint_slot": person.fingerprint_slot,
        "templates": counts,
        "templates_active": counts.get(active_engine or "", 0),
        "enrolled": counts.get(active_engine or "", 0) > 0,
        "needs_reindex": bool(counts) and counts.get(active_engine or "", 0) == 0,
        "is_demo": person.is_demo,
        "created_at": iso_local(person.created_at, tz),
    }


def event_dict(ev: AttendanceEvent, tz) -> dict:
    person = ev.person
    return {
        "id": ev.id,
        "person_id": ev.person_id,
        "person_code": person.code if person else None,
        "person_name": person.full_name if person else None,
        "area": person.area.name if person and person.area else None,
        "ts": ev.ts.isoformat(),
        "local": iso_local(ev.ts, tz),
        "local_date": fmt_date(ev.ts, tz),
        "local_time": fmt_time(ev.ts, tz),
        "event_type": ev.event_type,
        "method": ev.method,
        "face_score": ev.face_score,
        "face_threshold": ev.face_threshold,
        "face_margin": ev.face_margin,
        "fingerprint_score": ev.fingerprint_score,
        "liveness": ev.liveness,
        "liveness_challenge": ev.liveness_challenge,
        "engine": ev.engine,
        "photo_url": file_url(ev.photo_path),
        "photo_path": ev.photo_path,
        "manual_reason": ev.manual_reason,
        "voided": ev.voided,
        "void_reason": ev.void_reason,
        "voided_at": iso_local(ev.voided_at, tz),
        "created_by": ev.created_by,
    }


def shift_dict(s: Shift, tz) -> dict:
    person = (s.entry or s.exit).person
    return {
        "person_id": s.person_id,
        "person_code": person.code,
        "person_name": person.full_name,
        "area": person.area.name if person.area else None,
        "work_date": s.work_date.isoformat(),
        "entry": event_brief(s.entry, tz),
        "exit": event_brief(s.exit, tz),
        "hours": s.hours,
        "hhmm": s.hhmm,
        "status": s.status,
        "crosses_midnight": bool(s.entry and s.exit and fmt_date(s.entry.ts, tz) != fmt_date(s.exit.ts, tz)),
    }


def event_brief(ev: AttendanceEvent | None, tz) -> dict | None:
    if ev is None:
        return None
    return {
        "id": ev.id,
        "local_date": fmt_date(ev.ts, tz),
        "local_time": fmt_time(ev.ts, tz),
        "method": ev.method,
        "photo_url": file_url(ev.photo_path),
    }
