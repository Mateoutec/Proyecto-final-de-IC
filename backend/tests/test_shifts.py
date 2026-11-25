"""Cálculo de horas: cruce de medianoche, varias jornadas por día e incompletas."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain import ENTRADA, SALIDA, SHIFT_COMPLETE, SHIFT_INCOMPLETE, SHIFT_OPEN
from app.models import AttendanceEvent
from app.services.shifts import daily_seconds, pair_events, totals_by_person
from app.timeutil import hours_hhmm

LIMA = ZoneInfo("America/Lima")  # UTC-5, sin horario de verano
_ids = iter(range(1, 10_000))


def ev(person_id: int, local: datetime, kind: str, voided: bool = False) -> AttendanceEvent:
    return AttendanceEvent(
        id=next(_ids),
        person_id=person_id,
        ts=local.replace(tzinfo=LIMA).astimezone(timezone.utc),
        event_type=kind,
        method="ROSTRO",
        liveness="SUPERADA",
        voided=voided,
    )


NOW = datetime(2026, 10, 25, 12, 0, tzinfo=LIMA).astimezone(timezone.utc)


def test_simple_shift_hours_decimal_and_hhmm():
    shifts = pair_events(
        [ev(1, datetime(2026, 10, 20, 8, 0), ENTRADA), ev(1, datetime(2026, 10, 20, 16, 15), SALIDA)], NOW, 16, LIMA
    )
    assert len(shifts) == 1
    assert shifts[0].status == SHIFT_COMPLETE
    assert shifts[0].hours == 8.25
    assert shifts[0].hhmm == "08:15"


def test_shift_crossing_midnight_belongs_to_entry_day():
    shifts = pair_events(
        [ev(1, datetime(2026, 10, 20, 22, 0), ENTRADA), ev(1, datetime(2026, 10, 21, 6, 30), SALIDA)], NOW, 16, LIMA
    )
    assert shifts[0].work_date == date(2026, 10, 20)
    assert shifts[0].hours == 8.5


def test_midnight_in_local_tz_not_utc():
    # 19:30 en Lima ya es el día siguiente en UTC; la jornada debe quedar en el día local.
    shifts = pair_events(
        [ev(1, datetime(2026, 10, 20, 19, 30), ENTRADA), ev(1, datetime(2026, 10, 20, 23, 0), SALIDA)], NOW, 16, LIMA
    )
    assert shifts[0].work_date == date(2026, 10, 20)


def test_multiple_shifts_same_day_are_summed():
    events = [
        ev(1, datetime(2026, 10, 20, 8, 0), ENTRADA),
        ev(1, datetime(2026, 10, 20, 12, 0), SALIDA),
        ev(1, datetime(2026, 10, 20, 14, 0), ENTRADA),
        ev(1, datetime(2026, 10, 20, 17, 30), SALIDA),
    ]
    shifts = pair_events(events, NOW, 16, LIMA)
    assert [s.status for s in shifts] == [SHIFT_COMPLETE, SHIFT_COMPLETE]
    total = daily_seconds(shifts)[(1, date(2026, 10, 20))]
    assert hours_hhmm(total) == "07:30"
    totals = totals_by_person(shifts)[1]
    assert totals.days == 1
    assert totals.hours == 7.5


def test_two_entries_in_a_row_leave_first_incomplete():
    events = [
        ev(1, datetime(2026, 10, 20, 8, 0), ENTRADA),
        ev(1, datetime(2026, 10, 21, 8, 0), ENTRADA),
        ev(1, datetime(2026, 10, 21, 13, 0), SALIDA),
    ]
    shifts = pair_events(events, NOW, 16, LIMA)
    assert [s.status for s in shifts] == [SHIFT_INCOMPLETE, SHIFT_COMPLETE]
    assert shifts[0].hours is None
    assert totals_by_person(shifts)[1].incomplete == 1


def test_exit_beyond_max_shift_does_not_pair():
    events = [ev(1, datetime(2026, 10, 20, 8, 0), ENTRADA), ev(1, datetime(2026, 10, 21, 9, 0), SALIDA)]
    shifts = pair_events(events, NOW, 16, LIMA)
    assert [s.status for s in shifts] == [SHIFT_INCOMPLETE, SHIFT_INCOMPLETE]
    assert shifts[1].entry is None


def test_open_entry_recent_is_in_progress_and_old_is_incomplete():
    recent = NOW - timedelta(hours=2)
    old = NOW - timedelta(hours=30)
    shifts = pair_events(
        [
            AttendanceEvent(id=900, person_id=1, ts=recent, event_type=ENTRADA, method="ROSTRO", liveness="SUPERADA", voided=False),
            AttendanceEvent(id=901, person_id=2, ts=old, event_type=ENTRADA, method="ROSTRO", liveness="SUPERADA", voided=False),
        ],
        NOW,
        16,
        LIMA,
    )
    status = {s.person_id: s.status for s in shifts}
    assert status == {1: SHIFT_OPEN, 2: SHIFT_INCOMPLETE}


def test_voided_events_are_ignored():
    events = [
        ev(1, datetime(2026, 10, 20, 8, 0), ENTRADA),
        ev(1, datetime(2026, 10, 20, 9, 0), SALIDA, voided=True),
        ev(1, datetime(2026, 10, 20, 17, 0), SALIDA),
    ]
    shifts = pair_events(events, NOW, 16, LIMA)
    assert len(shifts) == 1 and shifts[0].hours == 9.0


def test_people_are_paired_independently():
    events = [
        ev(1, datetime(2026, 10, 20, 8, 0), ENTRADA),
        ev(2, datetime(2026, 10, 20, 9, 0), ENTRADA),
        ev(1, datetime(2026, 10, 20, 12, 0), SALIDA),
        ev(2, datetime(2026, 10, 20, 10, 0), SALIDA),
    ]
    totals = totals_by_person(pair_events(events, NOW, 16, LIMA))
    assert totals[1].hours == 4.0 and totals[2].hours == 1.0
