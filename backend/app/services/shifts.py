"""Emparejamiento ENTRADA→SALIDA en jornadas y totales de horas."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain import ENTRADA, SHIFT_COMPLETE, SHIFT_INCOMPLETE, SHIFT_OPEN
from app.models import AttendanceEvent, Person
from app.timeutil import day_bounds_utc, hours_decimal, hours_hhmm, local_date


@dataclass
class Shift:
    person_id: int
    entry: AttendanceEvent | None
    exit: AttendanceEvent | None
    status: str
    work_date: date

    @property
    def seconds(self) -> float | None:
        if self.entry is not None and self.exit is not None:
            return (self.exit.ts - self.entry.ts).total_seconds()
        return None

    @property
    def hours(self) -> float | None:
        return hours_decimal(self.seconds) if self.seconds is not None else None

    @property
    def hhmm(self) -> str | None:
        return hours_hhmm(self.seconds) if self.seconds is not None else None


def pair_events(events: list[AttendanceEvent], now: datetime, max_shift_hours: float, tz) -> list[Shift]:
    """Empareja marcaciones (no anuladas) de una o varias personas.

    - La jornada pertenece al día local de su ENTRADA (aunque cruce la medianoche).
    - ENTRADA seguida de otra ENTRADA, o sin SALIDA pasado el máximo: INCOMPLETA.
    - SALIDA sin ENTRADA abierta (p. ej., manual): INCOMPLETA.
    - ENTRADA abierta dentro del máximo: EN_CURSO.
    """
    max_shift = timedelta(hours=max_shift_hours)
    by_person: dict[int, list[AttendanceEvent]] = defaultdict(list)
    for ev in events:
        if not ev.voided:
            by_person[ev.person_id].append(ev)
    shifts: list[Shift] = []
    for person_id, evs in by_person.items():
        evs.sort(key=lambda e: (e.ts, e.id or 0))
        open_entry: AttendanceEvent | None = None
        for ev in evs:
            if ev.event_type == ENTRADA:
                if open_entry is not None:
                    shifts.append(Shift(person_id, open_entry, None, SHIFT_INCOMPLETE, local_date(open_entry.ts, tz)))
                open_entry = ev
                continue
            if open_entry is not None and ev.ts - open_entry.ts <= max_shift:
                shifts.append(Shift(person_id, open_entry, ev, SHIFT_COMPLETE, local_date(open_entry.ts, tz)))
                open_entry = None
                continue
            if open_entry is not None:
                shifts.append(Shift(person_id, open_entry, None, SHIFT_INCOMPLETE, local_date(open_entry.ts, tz)))
                open_entry = None
            shifts.append(Shift(person_id, None, ev, SHIFT_INCOMPLETE, local_date(ev.ts, tz)))
        if open_entry is not None:
            status = SHIFT_OPEN if now - open_entry.ts <= max_shift else SHIFT_INCOMPLETE
            shifts.append(Shift(person_id, open_entry, None, status, local_date(open_entry.ts, tz)))
    shifts.sort(key=lambda s: (s.work_date, (s.entry or s.exit).ts))
    return shifts


def load_shifts(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    tz,
    now: datetime,
    max_shift_hours: float,
    area_id: int | None = None,
    person_id: int | None = None,
) -> list[Shift]:
    """Jornadas cuyo día de entrada cae en [date_from, date_to]."""
    lo, hi = day_bounds_utc(date_from, date_to, tz)
    margin = timedelta(hours=max_shift_hours + 1)
    query = (
        select(AttendanceEvent)
        .options(joinedload(AttendanceEvent.person).joinedload(Person.area))
        .where(AttendanceEvent.ts >= lo - margin, AttendanceEvent.ts < hi + margin, AttendanceEvent.voided.is_(False))
    )
    if person_id is not None:
        query = query.where(AttendanceEvent.person_id == person_id)
    if area_id is not None:
        query = query.join(Person, Person.id == AttendanceEvent.person_id).where(Person.area_id == area_id)
    events = list(db.scalars(query).unique())
    return [s for s in pair_events(events, now, max_shift_hours, tz) if date_from <= s.work_date <= date_to]


@dataclass
class PersonTotals:
    person_id: int
    days: int
    seconds: float
    incomplete: int
    open: int

    @property
    def hours(self) -> float:
        return hours_decimal(self.seconds)

    @property
    def hhmm(self) -> str:
        return hours_hhmm(self.seconds)


def totals_by_person(shifts: list[Shift]) -> dict[int, PersonTotals]:
    days: dict[int, set[date]] = defaultdict(set)
    seconds: dict[int, float] = defaultdict(float)
    incomplete: dict[int, int] = defaultdict(int)
    open_count: dict[int, int] = defaultdict(int)
    for s in shifts:
        if s.entry is not None:
            days[s.person_id].add(s.work_date)
        if s.status == SHIFT_COMPLETE and s.seconds is not None:
            seconds[s.person_id] += s.seconds
        elif s.status == SHIFT_INCOMPLETE:
            incomplete[s.person_id] += 1
        elif s.status == SHIFT_OPEN:
            open_count[s.person_id] += 1
    ids = set(days) | set(seconds) | set(incomplete) | set(open_count)
    return {
        pid: PersonTotals(pid, len(days[pid]), seconds[pid], incomplete[pid], open_count[pid]) for pid in ids
    }


def daily_seconds(shifts: list[Shift]) -> dict[tuple[int, date], float]:
    """Suma de horas de jornadas completas por persona y día (varias jornadas se suman)."""
    out: dict[tuple[int, date], float] = defaultdict(float)
    for s in shifts:
        if s.status == SHIFT_COMPLETE and s.seconds is not None:
            out[(s.person_id, s.work_date)] += s.seconds
    return out
