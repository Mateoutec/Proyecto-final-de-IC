"""Reglas de marcación: tipo automático, anti-rebote, registro y capturas."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.domain import ENTRADA, SALIDA
from app.errors import AppError
from app.models import AttendanceEvent, Person
from app.timeutil import hours_decimal, hours_hhmm, to_local

log = logging.getLogger("app.attendance")


def decide_event_type(last_type: str | None, last_ts: datetime | None, now: datetime, max_shift_hours: float) -> str:
    """SALIDA si la última marcación es una ENTRADA abierta dentro del máximo; si no, ENTRADA.

    Una ENTRADA abierta que superó `max_shift_hours` queda como jornada INCOMPLETA
    (lo resuelve el emparejamiento de jornadas) y la nueva marcación es ENTRADA.
    """
    if last_type == ENTRADA and last_ts is not None and now - last_ts <= timedelta(hours=max_shift_hours):
        return SALIDA
    return ENTRADA


def debounce_seconds_ago(last_ts: datetime | None, now: datetime, debounce_seconds: int) -> int | None:
    """Segundos desde la última marcación si cae dentro de la ventana anti-rebote."""
    if last_ts is None or debounce_seconds <= 0:
        return None
    elapsed = (now - last_ts).total_seconds()
    if 0 <= elapsed < debounce_seconds:
        return int(elapsed)
    return None


def already_message(last_type: str, seconds_ago: int) -> str:
    word = "entrada" if last_type == ENTRADA else "salida"
    return f"Ya registraste tu {word} hace {seconds_ago} s"


def last_valid_event(db: Session, person_id: int) -> AttendanceEvent | None:
    return db.scalars(
        select(AttendanceEvent)
        .where(AttendanceEvent.person_id == person_id, AttendanceEvent.voided.is_(False))
        .order_by(AttendanceEvent.ts.desc(), AttendanceEvent.id.desc())
        .limit(1)
    ).first()


class AlreadyRegistered(Exception):
    def __init__(self, last_type: str, seconds_ago: int):
        super().__init__(already_message(last_type, seconds_ago))
        self.last_type = last_type
        self.seconds_ago = seconds_ago


def save_capture(data_path: Path, jpeg: bytes, person_code: str, ts_local: datetime, event_type: str) -> str:
    rel_dir = Path("captures") / ts_local.strftime("%Y") / ts_local.strftime("%m") / ts_local.strftime("%d")
    target_dir = data_path / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_code = "".join(ch for ch in person_code if ch.isalnum() or ch in "-_") or "persona"
    name = f"{ts_local.strftime('%H%M%S')}_{safe_code}_{event_type.lower()}_{secrets.token_hex(3)}.jpg"
    path = target_dir / name
    path.write_bytes(jpeg)
    if os.name == "posix":
        os.chmod(path, 0o600)
    return (rel_dir / name).as_posix()


def save_failed_capture(data_path: Path, jpeg: bytes, ts_local: datetime, reason: str) -> str:
    rel_dir = Path("captures") / "fallidos" / ts_local.strftime("%Y") / ts_local.strftime("%m") / ts_local.strftime("%d")
    (data_path / rel_dir).mkdir(parents=True, exist_ok=True)
    name = f"{ts_local.strftime('%H%M%S')}_{reason}_{secrets.token_hex(3)}.jpg"
    (data_path / rel_dir / name).write_bytes(jpeg)
    return (rel_dir / name).as_posix()


@dataclass
class Registration:
    event: AttendanceEvent
    worked_seconds: float | None

    def worked(self) -> dict:
        if self.worked_seconds is None:
            return {"worked_hours": None, "worked_hhmm": None}
        return {"worked_hours": hours_decimal(self.worked_seconds), "worked_hhmm": hours_hhmm(self.worked_seconds)}


def register_event(
    db: Session,
    *,
    person: Person,
    method: str,
    now: datetime,
    tz,
    data_path: Path,
    max_shift_hours: float,
    debounce_seconds: int,
    photo: bytes | None,
    face_score: float | None = None,
    face_threshold: float | None = None,
    face_margin: float | None = None,
    fingerprint_score: float | None = None,
    liveness: str,
    liveness_challenge: str | None = None,
    engine: str | None = None,
    created_by: str = "kiosco",
) -> Registration:
    # A fresh transaction avoids upgrading a caller's old read snapshot in WAL.
    # SQLite serializes writers across connections/processes, not just sessions.
    person_id = person.id
    photo_path = None
    try:
        with Session(bind=db.get_bind(), expire_on_commit=False) as writer:
            writer.execute(text("BEGIN IMMEDIATE"))
            current = writer.get(Person, person_id)
            if current is None or not current.active:
                raise AppError("La persona está desactivada o ya no existe", status_code=409)
            last = last_valid_event(writer, person_id)
            seconds_ago = debounce_seconds_ago(last.ts if last else None, now, debounce_seconds)
            if last is not None:
                if seconds_ago is not None:
                    raise AlreadyRegistered(last.event_type, seconds_ago)
                # A request that waited for another writer may carry an older time.
                if now < last.ts:
                    raise AlreadyRegistered(last.event_type, 0)
            event_type = decide_event_type(last.event_type if last else None, last.ts if last else None, now, max_shift_hours)
            photo_path = save_capture(data_path, photo, current.code, to_local(now, tz), event_type) if photo else None
            event = AttendanceEvent(
                person_id=person_id,
                ts=now,
                event_type=event_type,
                method=method,
                face_score=round(face_score, 4) if face_score is not None else None,
                face_threshold=face_threshold,
                face_margin=round(face_margin, 4) if face_margin is not None else None,
                fingerprint_score=fingerprint_score,
                liveness=liveness,
                liveness_challenge=liveness_challenge,
                engine=engine,
                photo_path=photo_path,
                created_by=created_by,
            )
            writer.add(event)
            worked = (now - last.ts).total_seconds() if event_type == SALIDA and last is not None else None
            writer.commit()
    except Exception as exc:
        if photo_path:
            try:
                (data_path / photo_path).unlink(missing_ok=True)
            except OSError:
                log.exception("No se pudo retirar la captura de una marcación fallida")
        if isinstance(exc, OperationalError) and "locked" in str(exc).lower():
            raise AppError("La base está ocupada. Vuelve a intentar la marcación.", status_code=503, code="database_busy") from exc
        raise
    log.info("Marcación %s de persona %s (%s) método=%s", event_type, person_id, event.id, method)
    return Registration(event=event, worked_seconds=worked)
