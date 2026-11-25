"""Resumen personal del perfil Usuario.

Se muestra en el kiosco solo después de que la persona se identifica (rostro + prueba de vida,
huella o código + rostro). No requiere contraseña: la biometría es la autenticación, y el
resumen nunca se entrega a quien no superó la identificación.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttendanceEvent
from app.services.shifts import load_shifts, totals_by_person
from app.timeutil import fmt_time, hours_decimal, hours_hhmm, local_date

WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def personal_summary(
    db: Session,
    *,
    person_id: int,
    now: datetime,
    tz,
    max_shift_hours: float,
    recent: int = 4,
) -> dict:
    """Semana en curso (lunes a hoy) y últimas marcaciones válidas de una persona."""
    today = local_date(now, tz)
    week_start = today - timedelta(days=today.weekday())
    shifts = load_shifts(
        db,
        date_from=week_start,
        date_to=today,
        tz=tz,
        now=now,
        max_shift_hours=max_shift_hours,
        person_id=person_id,
    )
    totals = totals_by_person(shifts).get(person_id)
    seconds = totals.seconds if totals else 0.0
    events = db.scalars(
        select(AttendanceEvent)
        .where(AttendanceEvent.person_id == person_id, AttendanceEvent.voided.is_(False))
        .order_by(AttendanceEvent.ts.desc(), AttendanceEvent.id.desc())
        .limit(recent)
    ).all()
    items = []
    for ev in events:
        day = local_date(ev.ts, tz)
        items.append(
            {
                "day": f"{WEEKDAYS[day.weekday()]} {day:%d/%m}",
                "time": fmt_time(ev.ts, tz, seconds=False),
                "type": ev.event_type,
                "method": ev.method,
            }
        )
    return {
        "week_from": week_start.isoformat(),
        "week_days": totals.days if totals else 0,
        "week_hours": hours_decimal(seconds),
        "week_hhmm": hours_hhmm(seconds),
        "week_incomplete": totals.incomplete if totals else 0,
        "recent": items,
    }
