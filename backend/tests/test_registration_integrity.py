"""Identity-bound photographs and concurrent SQLite registrations."""
import base64
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.kiosk import session as kiosk_module
from app.models import AttendanceEvent, Person
from app.services import attendance
from tests.conftest import FakeClock, jpeg
from tests.test_kiosk_session import add_person, finish_challenge, new_session, run_until


@pytest.mark.parametrize("liveness", [True, False])
@pytest.mark.parametrize("previous_identity", [1, 999])
def test_photo_belongs_to_winner_even_when_previous_face_is_sharper(ctx, monkeypatch, liveness, previous_identity):
    add_person(ctx, "A", 1)
    add_person(ctx, "B", 2)
    ctx.update_runtime({"liveness_enabled": liveness}, "test")
    original = kiosk_module.evaluate
    calls = 0

    def ranked_quality(*args, **kwargs):
        nonlocal calls
        calls += 1
        return replace(original(*args, **kwargs), score=1.0 if calls == 1 else 0.5)

    monkeypatch.setattr(kiosk_module, "evaluate", ranked_quality)
    clock = FakeClock()
    session = new_session(ctx, clock)
    session.handle_frame(jpeg(previous_identity))
    view = run_until(session, jpeg(2), clock=clock)
    if liveness:
        view = finish_challenge(session, 2, clock)
    assert view["state"] == "success"
    assert view["result"]["person"]["code"] == "B"
    assert base64.b64decode(view["result"]["photo"].split(",")[1]) == jpeg(2)
    with ctx.session() as db:
        record = db.get(AttendanceEvent, view["result"]["event_id"])
        assert (ctx.data_path / record.photo_path).read_bytes() == jpeg(2)


def register(ctx, pid, now):
    with ctx.session() as db:
        return attendance.register_event(
            db, person=db.get(Person, pid), method="ROSTRO", now=now,
            tz=ctx.tz, data_path=ctx.data_path, max_shift_hours=16,
            debounce_seconds=120, photo=jpeg(1), liveness="SUPERADA",
        )


@pytest.mark.parametrize("existing_entry", [False, True])
def test_simultaneous_requests_create_only_one_event(ctx, monkeypatch, existing_entry):
    pid = add_person(ctx, "A", 1)
    now = FakeClock()()
    if existing_entry:
        register(ctx, pid, now - timedelta(minutes=3))
    barrier = threading.Barrier(2)
    original = attendance.last_valid_event

    def delayed_read(db, person_id):
        result = original(db, person_id)
        # Expose the old read/write race without blocking the serialized writer.
        time.sleep(0.15)
        return result

    monkeypatch.setattr(attendance, "last_valid_event", delayed_read)

    def attempt():
        barrier.wait(timeout=5)
        try:
            return register(ctx, pid, now).event.event_type
        except attendance.AlreadyRegistered:
            return "already_registered"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt) for _ in range(2)]
        outcomes = [f.result(timeout=10) for f in futures]
    assert sorted(outcomes) == sorted(["SALIDA" if existing_entry else "ENTRADA", "already_registered"])
    with ctx.session() as db:
        events = list(db.scalars(select(AttendanceEvent).where(AttendanceEvent.ts == now)))
    assert len(events) == 1
    assert len(list(ctx.data_path.glob("captures/**/*.jpg"))) == (2 if existing_entry else 1)


def test_delayed_request_with_older_timestamp_is_rejected(ctx):
    pid = add_person(ctx, "A", 1)
    now = FakeClock()()
    register(ctx, pid, now)
    with pytest.raises(attendance.AlreadyRegistered):
        register(ctx, pid, now - timedelta(milliseconds=100))


def test_active_status_is_rechecked_inside_writer_transaction(ctx):
    pid = add_person(ctx, "A", 1)
    with ctx.session() as reader:
        stale_person = reader.get(Person, pid)
        with ctx.session() as writer:
            writer.get(Person, pid).active = False
            writer.commit()
        from app.errors import AppError
        with pytest.raises(AppError, match="desactivada"):
            attendance.register_event(
                reader, person=stale_person, method="ROSTRO", now=FakeClock()(),
                tz=ctx.tz, data_path=ctx.data_path, max_shift_hours=16,
                debounce_seconds=120, photo=None, liveness="SUPERADA",
            )


def test_commit_failure_rolls_back_and_removes_capture(ctx, monkeypatch):
    from sqlalchemy.orm import Session

    pid = add_person(ctx, "A", 1)
    original = Session.commit

    def fail_commit(self):
        self.flush()
        raise RuntimeError("fallo de escritura simulado")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="fallo de escritura"):
        register(ctx, pid, FakeClock()())
    with ctx.session() as db:
        assert list(db.scalars(select(AttendanceEvent))) == []
    assert list(ctx.data_path.glob("captures/**/*.jpg")) == []
    monkeypatch.setattr(Session, "commit", original)
    assert register(ctx, pid, FakeClock()()).event.event_type == "ENTRADA"
