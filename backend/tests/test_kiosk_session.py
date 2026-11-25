"""Máquina de estados del kiosco con el motor fake (identificación, prueba de vida, huella, código)."""

import random

from sqlalchemy import select

from app.domain import ENTRADA, METHOD_CODE_FACE, METHOD_FACE, METHOD_FINGERPRINT, METHOD_FINGERPRINT_FACE, SALIDA
from app.fingerprint.base import SimulatedProvider
from app.kiosk.session import KioskSession, State
from app.models import AttendanceEvent, Person
from tests.conftest import FakeClock, jpeg


def add_person(ctx, code: str, identity: int, enroll: int = 3, slot: int | None = None) -> int:
    from app.services.enrollment import enroll_photo

    with ctx.session() as db:
        person = Person(code=code, first_name=f"N{code}", last_name="Test", consent_signed=True, fingerprint_slot=slot)
        db.add(person)
        db.commit()
        for _ in range(enroll):
            enroll_photo(ctx, db, person, jpeg(identity), "frontal", "camera", False, "test")
        return person.id


def run_until(session, frames, max_frames: int = 30, clock: FakeClock | None = None, step: float = 0.2):
    view = session.view()
    for i in range(max_frames):
        frame = frames(i) if callable(frames) else frames
        view = session.handle_frame(frame)
        if clock:
            clock.advance(step)
        if view["terminal"] or view["state"] == State.CHALLENGE.value:
            break
    return view


def new_session(ctx, clock=None, seed=1):
    return KioskSession(ctx, clock=clock or FakeClock(), rng=random.Random(seed))


def finish_challenge(session, identity: int, clock: FakeClock):
    direction = session.challenge.direction
    yaw = 0.3 if direction == "left" else -0.3
    view = session.view()
    for _ in range(6):
        view = session.handle_frame(jpeg(identity, yaw=yaw))
        clock.advance(0.2)
        if view["terminal"]:
            break
    return view


def test_no_enrolled_state(ctx):
    session = new_session(ctx)
    view = session.handle_frame(jpeg(1))
    assert view["state"] == "no_enrolled"


def test_identify_with_liveness_registers_entry_then_exit(ctx):
    pid = add_person(ctx, "A1", identity=1)
    add_person(ctx, "B2", identity=2)
    clock = FakeClock()
    session = new_session(ctx, clock)
    view = run_until(session, jpeg(1), clock=clock)
    assert view["state"] == "challenge"
    assert view["challenge"]["direction"] in ("left", "right")
    view = finish_challenge(session, 1, clock)
    assert view["state"] == "success", view
    assert view["result"]["event_type"] == ENTRADA
    assert view["result"]["person"]["code"] == "A1"
    assert view["result"]["photo"].startswith("data:image/jpeg;base64,")
    assert view["result"]["face_score"] > 0.9

    # Dentro del anti-rebote: "ya registrado"
    clock.advance(30)
    again = new_session(ctx, clock)
    view = run_until(again, jpeg(1), clock=clock)
    assert view["state"] == "already_registered"
    assert view["hint"].startswith("Ya registraste tu entrada hace")

    # Pasado el anti-rebote: SALIDA con horas trabajadas
    clock.advance(3 * 3600)
    exit_session = new_session(ctx, clock, seed=5)
    run_until(exit_session, jpeg(1), clock=clock)
    view = finish_challenge(exit_session, 1, clock)
    assert view["result"]["event_type"] == SALIDA
    assert view["result"]["worked_hours"] is not None and view["result"]["worked_hours"] >= 3.0

    with ctx.session() as db:
        events = list(db.scalars(select(AttendanceEvent).where(AttendanceEvent.person_id == pid)))
    assert [e.event_type for e in events] == [ENTRADA, SALIDA]
    assert all(e.method == METHOD_FACE and e.liveness == "SUPERADA" and e.photo_path for e in events)
    assert (ctx.data_path / events[0].photo_path).exists()


def test_liveness_timeout_fails(ctx):
    add_person(ctx, "A1", identity=1)
    clock = FakeClock()
    session = new_session(ctx, clock)
    run_until(session, jpeg(1), clock=clock)
    assert session.state == State.CHALLENGE
    clock.advance(ctx.runtime.liveness_timeout_seconds + 1)
    view = session.handle_frame(jpeg(1))
    assert view["state"] == "liveness_failed"


def test_liveness_wrong_direction_does_not_pass(ctx):
    add_person(ctx, "A1", identity=1)
    clock = FakeClock()
    session = new_session(ctx, clock)
    run_until(session, jpeg(1), clock=clock)
    wrong = -0.3 if session.challenge.direction == "left" else 0.3
    for _ in range(5):
        view = session.handle_frame(jpeg(1, yaw=wrong))
    assert view["state"] == "challenge"
    assert view["hint"].startswith("Hacia el otro lado")


def test_liveness_identity_swap_fails(ctx):
    add_person(ctx, "A1", identity=1)
    add_person(ctx, "B2", identity=2)
    clock = FakeClock()
    session = new_session(ctx, clock)
    run_until(session, jpeg(1), clock=clock)
    yaw = 0.3 if session.challenge.direction == "left" else -0.3
    for _ in range(4):
        view = session.handle_frame(jpeg(2, yaw=yaw))
    assert view["state"] == "liveness_failed"
    assert "cambió" in view["hint"]


def test_unknown_face_not_recognized(ctx):
    add_person(ctx, "A1", identity=1)
    session = new_session(ctx)
    view = run_until(session, jpeg(42), max_frames=40)
    assert view["state"] == "not_recognized"


def test_quality_guidance_messages(ctx):
    add_person(ctx, "A1", identity=1)
    session = new_session(ctx)
    assert session.handle_frame(jpeg(1, face_size=60))["hint"] == "Acércate un poco"
    assert session.handle_frame(jpeg(1, brightness=25))["hint"].startswith("Falta luz")
    assert session.handle_frame(jpeg(1, faces=2, face_size=150))["hint"].startswith("Debe quedar una sola persona")
    assert session.handle_frame(jpeg(1, yaw=0.35))["hint"] == "Mira al frente"
    assert session.handle_frame(jpeg(1, blur=True))["hint"] == "Quédate quieto un momento"


def test_liveness_disabled_registers_directly(ctx):
    ctx.update_runtime({"liveness_enabled": False}, "test")
    add_person(ctx, "A1", identity=1)
    view = run_until(new_session(ctx), jpeg(1))
    assert view["state"] == "success"
    with ctx.session() as db:
        assert db.scalar(select(AttendanceEvent.liveness)) == "DESACTIVADA"


def test_fingerprint_high_registers_by_fingerprint(ctx):
    pid = add_person(ctx, "A1", identity=1, slot=5)
    session = new_session(ctx)
    session.handle_frame(jpeg(1))  # frame para la foto de auditoría
    result = SimulatedProvider().simulate(pid, 5, "high")
    view = session.handle_fingerprint(result)
    assert view["state"] == "success"
    assert view["result"]["method"] == METHOD_FINGERPRINT
    with ctx.session() as db:
        event = db.scalar(select(AttendanceEvent))
    assert event.fingerprint_score == 200.0 and event.photo_path and event.liveness == "NO_APLICA"


def test_fingerprint_medium_requires_face_verification(ctx):
    pid = add_person(ctx, "A1", identity=1, slot=5)
    add_person(ctx, "B2", identity=2)
    clock = FakeClock()
    session = new_session(ctx, clock)
    view = session.handle_fingerprint(SimulatedProvider().simulate(pid, 5, "medium"))
    assert view["state"] == "detecting" and view["mode"] == "verify"
    # Otro rostro no sirve para la verificación 1:1
    view = run_until(session, jpeg(2), max_frames=40, clock=clock)
    assert view["state"] == "not_recognized"
    # Con el rostro correcto sí
    session = new_session(ctx, clock)
    session.handle_fingerprint(SimulatedProvider().simulate(pid, 5, "medium"))
    run_until(session, jpeg(1), clock=clock)
    view = finish_challenge(session, 1, clock)
    assert view["state"] == "success"
    assert view["result"]["method"] == METHOD_FINGERPRINT_FACE


def test_fingerprint_no_match_with_code_fallback(ctx):
    ctx.update_runtime({"fallback_mode": "code_plus_face"}, "test")
    add_person(ctx, "A1", identity=1)
    clock = FakeClock()
    session = new_session(ctx, clock)
    view = session.handle_fingerprint(SimulatedProvider().simulate(None, None, "none"))
    assert view["state"] == "need_code"
    view = session.handle_code("a1")
    assert view["mode"] == "verify" and view["candidate"]["code"] == "A1"
    run_until(session, jpeg(1), clock=clock)
    view = finish_challenge(session, 1, clock)
    assert view["result"]["method"] == METHOD_CODE_FACE


def test_fingerprint_no_match_face_fallback(ctx):
    add_person(ctx, "A1", identity=1)
    clock = FakeClock()
    session = new_session(ctx, clock)
    view = session.handle_fingerprint(SimulatedProvider().simulate(None, None, "bad_image"))
    assert view["state"] == "waiting" and view["mode"] == "identify"
    run_until(session, jpeg(1), clock=clock)
    assert finish_challenge(session, 1, clock)["result"]["method"] == METHOD_FACE


def test_unknown_code_raises(ctx):
    add_person(ctx, "A1", identity=1)
    session = new_session(ctx)
    try:
        session.handle_code("ZZZ")
    except Exception as exc:  # noqa: BLE001
        assert "código" in str(exc)
    else:
        raise AssertionError("debía fallar")


def test_low_margin_between_candidates_is_rejected(ctx):
    # Dos personas con la misma "cara" => margen 0, nunca debe aceptar a ninguna.
    ctx.update_runtime({"liveness_enabled": False}, "test")
    from app.services.enrollment import enroll_photo

    add_person(ctx, "A1", identity=1)
    with ctx.session() as db:
        twin = Person(code="T1", first_name="Gemelo", last_name="Test", consent_signed=True)
        db.add(twin)
        db.commit()
        enroll_photo(ctx, db, twin, jpeg(1), "frontal", "camera", True, "test")
    view = run_until(new_session(ctx), jpeg(1), max_frames=40)
    assert view["state"] == "not_recognized"


def test_success_and_already_include_personal_summary(ctx):
    """Perfil Usuario: tras identificarse ve su semana y sus últimas marcaciones."""
    add_person(ctx, "A1", identity=1)
    add_person(ctx, "B2", identity=2)
    clock = FakeClock()  # martes 20/10/2026 13:00 UTC
    session = new_session(ctx, clock)
    run_until(session, jpeg(1), clock=clock)
    view = finish_challenge(session, 1, clock)
    summary = view["result"]["summary"]
    assert summary["week_from"] == "2026-10-19"  # lunes de esa semana
    assert summary["week_days"] == 1
    assert summary["week_hhmm"] == "00:00"  # jornada aún en curso
    assert [r["type"] for r in summary["recent"]] == [ENTRADA]

    clock.advance(30)
    again = new_session(ctx, clock)
    view = run_until(again, jpeg(1), clock=clock)
    assert view["state"] == "already_registered"
    assert view["result"]["summary"]["recent"][0]["type"] == ENTRADA

    clock.advance(2 * 3600)
    exit_session = new_session(ctx, clock, seed=5)
    run_until(exit_session, jpeg(1), clock=clock)
    view = finish_challenge(exit_session, 1, clock)
    summary = view["result"]["summary"]
    assert view["result"]["event_type"] == SALIDA
    assert summary["week_days"] == 1
    assert summary["week_hours"] >= 2.0
    assert [r["type"] for r in summary["recent"]] == [SALIDA, ENTRADA]
    assert summary["recent"][0]["day"].startswith("mar ")

    # Nunca se mezclan marcaciones de otra persona.
    other = new_session(ctx, clock, seed=7)
    run_until(other, jpeg(2), clock=clock)
    view = finish_challenge(other, 2, clock)
    assert [r["type"] for r in view["result"]["summary"]["recent"]] == [ENTRADA]
