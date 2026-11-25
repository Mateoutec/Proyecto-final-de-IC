"""Datos de demostración (sin biometría) para ver los reportes poblados."""

from __future__ import annotations

import random
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import delete, select

from app.domain import (
    ENTRADA,
    LIVENESS_NOT_APPLICABLE,
    LIVENESS_PASSED,
    METHOD_CODE_FACE,
    METHOD_FACE,
    METHOD_MANUAL,
    SALIDA,
)
from app.models import Area, AttendanceEvent, Person
from app.services.audit import audit

AREAS = [
    ("Laboratorio de Cognitive Computing", "Prácticas del curso"),
    ("Ciencia de Datos", "Proyectos de analítica"),
    ("Desarrollo de Software", "Equipo de desarrollo"),
    ("Soporte TI", "Mesa de ayuda del laboratorio"),
]
FIRST = ["Valeria", "Diego", "Camila", "Mateo", "Lucía", "Santiago", "Ximena", "Joaquín", "Renata", "Gael",
         "Daniela", "Sebastián", "Fernanda", "Andrés", "Mariana", "Tomás", "Alessandra", "Nicolás", "Paula", "Adrián"]
LAST = ["Quispe", "Huamán", "Rojas", "Flores", "Mendoza", "Vargas", "Castillo", "Chávez", "Ramos", "Torres",
        "Salazar", "Paredes", "Gutiérrez", "Ríos", "Cárdenas", "Navarro", "Espinoza", "Soto", "Benites", "Aguilar"]


def seed_demo(ctx, days: int = 14) -> dict:
    rng = random.Random(2026)
    tz = ctx.tz
    with ctx.session() as db:
        if db.scalar(select(Person.id).where(Person.is_demo.is_(True)).limit(1)):
            return {"created": False, "message": "Los datos de demostración ya existen (usa --clear para borrarlos)"}
        areas = []
        for name, desc in AREAS:
            area = db.scalar(select(Area).where(Area.name == name))
            if area is None:
                area = Area(name=name, description=desc)
                db.add(area)
                db.flush()
            areas.append(area)
        people = []
        for i in range(20):
            person = Person(
                code=f"DEMO{i + 1:03d}",
                first_name=FIRST[i],
                last_name=f"{LAST[i]} {LAST[(i * 7 + 3) % 20]}",
                area_id=areas[i % len(areas)].id,
                position="Estudiante" if i % 5 else "Asistente de laboratorio",
                active=True,
                consent_signed=False,
                is_demo=True,
            )
            db.add(person)
            people.append(person)
        db.flush()
        today = datetime.now(tz).date()
        events = 0
        for d in range(days, -1, -1):
            day = today - timedelta(days=d)
            if day.weekday() == 6:
                continue
            for person in people:
                if rng.random() < 0.18:
                    continue
                start_h = rng.choice([7, 8, 8, 9, 14, 18])
                start = datetime.combine(day, time(start_h, rng.randint(0, 50)), tzinfo=tz)
                if d == 0 and start > datetime.now(tz):
                    continue
                method = rng.choice([METHOD_FACE] * 8 + [METHOD_CODE_FACE])
                db.add(_event(person.id, start, ENTRADA, method))
                events += 1
                duration = timedelta(hours=rng.uniform(3.5, 9.0)) if start_h < 18 else timedelta(hours=rng.uniform(5, 7))
                end = start + duration
                if d == 0 and end > datetime.now(tz):
                    continue
                if rng.random() < 0.06:
                    continue  # salida olvidada -> jornada incompleta
                end_method = METHOD_MANUAL if rng.random() < 0.04 else rng.choice([METHOD_FACE] * 8 + [METHOD_CODE_FACE])
                db.add(_event(person.id, end, SALIDA, end_method))
                events += 1
        audit(db, "sistema", "seed_demo", "seed", None, people=len(people), events=events)
        db.commit()
    return {"created": True, "people": 20, "events": events, "areas": len(AREAS)}


def _event(person_id: int, local_dt: datetime, event_type: str, method: str) -> AttendanceEvent:
    manual = method == METHOD_MANUAL
    return AttendanceEvent(
        person_id=person_id,
        ts=local_dt.astimezone(timezone.utc),
        event_type=event_type,
        method=method,
        liveness=LIVENESS_NOT_APPLICABLE if manual else LIVENESS_PASSED,
        manual_reason="Salida olvidada (demostración)" if manual else None,
        created_by="seed",
    )


def clear_demo(ctx) -> dict:
    with ctx.session() as db:
        ids = list(db.scalars(select(Person.id).where(Person.is_demo.is_(True))))
        if ids:
            db.execute(delete(AttendanceEvent).where(AttendanceEvent.person_id.in_(ids)))
            db.execute(delete(Person).where(Person.id.in_(ids)))
        audit(db, "sistema", "seed_demo", "seed", None, cleared=len(ids))
        db.commit()
    return {"cleared": len(ids)}
