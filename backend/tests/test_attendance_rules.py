"""Tipo automático de marcación y anti-rebote."""

from datetime import datetime, timedelta, timezone

from app.domain import ENTRADA, SALIDA
from app.services.attendance import already_message, debounce_seconds_ago, decide_event_type

T0 = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)


def test_first_event_is_entry():
    assert decide_event_type(None, None, T0, 16) == ENTRADA


def test_open_entry_within_limit_becomes_exit():
    assert decide_event_type(ENTRADA, T0, T0 + timedelta(hours=8), 16) == SALIDA


def test_open_entry_exactly_at_limit_is_still_exit():
    assert decide_event_type(ENTRADA, T0, T0 + timedelta(hours=16), 16) == SALIDA


def test_open_entry_beyond_limit_starts_new_entry():
    assert decide_event_type(ENTRADA, T0, T0 + timedelta(hours=16, seconds=1), 16) == ENTRADA


def test_after_exit_next_is_entry():
    assert decide_event_type(SALIDA, T0, T0 + timedelta(minutes=30), 16) == ENTRADA


def test_debounce_inside_window():
    assert debounce_seconds_ago(T0, T0 + timedelta(seconds=35), 120) == 35


def test_debounce_outside_window():
    assert debounce_seconds_ago(T0, T0 + timedelta(seconds=120), 120) is None


def test_debounce_disabled():
    assert debounce_seconds_ago(T0, T0 + timedelta(seconds=5), 0) is None


def test_already_message_text():
    assert already_message(ENTRADA, 35) == "Ya registraste tu entrada hace 35 s"
    assert already_message(SALIDA, 7) == "Ya registraste tu salida hace 7 s"
