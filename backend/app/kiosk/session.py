"""Máquina de estados del kiosco: sesión de reconocimiento, reto de vida y decisión.

El frontend solo envía frames / huella / código y muestra la vista que devuelve
`KioskSession.view()`. Toda la lógica vive aquí y se prueba con el motor `fake`.
"""

from __future__ import annotations

import base64
import logging
import random
import secrets
import threading
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.db import utcnow
from app.domain import (
    LIVENESS_DISABLED,
    LIVENESS_NOT_APPLICABLE,
    LIVENESS_PASSED,
    METHOD_CODE_FACE,
    METHOD_FACE,
    METHOD_FINGERPRINT,
    METHOD_FINGERPRINT_FACE,
    SALIDA,
)
from app.errors import AppError
from app.face.base import decode_image, pose_from_kps
from app.face.liveness import DIRECTION_TEXT, DIRECTIONS, evaluate_turn, user_yaw
from app.face.quality import evaluate, pick_main_face
from app.fingerprint.base import FingerprintResult
from app.kiosk.decision import RouteKind, classify, decide
from app.models import Person
from app.services.attendance import (
    AlreadyRegistered,
    already_message,
    debounce_seconds_ago,
    last_valid_event,
    register_event,
    save_failed_capture,
)
from app.services.personal_summary import personal_summary
from app.timeutil import fmt_date, fmt_time, to_local

if TYPE_CHECKING:
    from app.context import AppContext

log = logging.getLogger("app.kiosk")


class State(str, Enum):
    WAITING = "waiting"
    DETECTING = "detecting"
    CHALLENGE = "challenge"
    NEED_CODE = "need_code"
    SUCCESS = "success"
    ALREADY = "already_registered"
    NOT_RECOGNIZED = "not_recognized"
    LIVENESS_FAILED = "liveness_failed"
    NO_ENROLLED = "no_enrolled"
    ERROR = "error"
    CANCELLED = "cancelled"


TERMINAL = {State.SUCCESS, State.ALREADY, State.NOT_RECOGNIZED, State.LIVENESS_FAILED, State.ERROR, State.CANCELLED}

TITLES = {
    State.WAITING: "Acércate para marcar",
    State.DETECTING: "Identificando",
    State.CHALLENGE: "Prueba de vida",
    State.NEED_CODE: "Ingresa tu código",
    State.SUCCESS: "Marcación registrada",
    State.ALREADY: "Ya registrado",
    State.NOT_RECOGNIZED: "No te reconocimos",
    State.LIVENESS_FAILED: "Prueba de vida no superada",
    State.NO_ENROLLED: "Sin personas enroladas",
    State.ERROR: "No se pudo marcar",
    State.CANCELLED: "Cancelado",
}


@dataclass
class Vote:
    person_id: int | None
    score: float
    margin: float | None
    photo: bytes | None = None
    quality: float = 0.0


@dataclass
class Challenge:
    direction: str
    deadline: datetime
    hits: int = 0
    mismatches: int = 0
    progress: float = 0.0
    min_identity: float = 1.0


def person_public(person: Person) -> dict:
    return {
        "id": person.id,
        "code": person.code,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": person.full_name,
        "area": person.area.name if person.area else None,
        "position": person.position,
    }


class KioskSession:
    def __init__(self, ctx: AppContext, *, clock=None, rng: random.Random | None = None):
        self.ctx = ctx
        self.id = secrets.token_urlsafe(12)
        self.clock = clock or utcnow
        self.rng = rng or random.Random()
        self.created_at = self.updated_at = self.clock()
        self.lock = threading.Lock()
        self.state = State.WAITING
        self.mode = "identify"
        self.method = METHOD_FACE
        self.candidate: dict | None = None
        self.votes: deque[Vote] = deque(maxlen=ctx.settings.consensus_window)
        self.quality_frames = 0
        self.no_face_streak = 0
        self.best_frame: bytes | None = None
        self.best_score = -1.0
        self.last_frame: bytes | None = None
        self.identified: dict | None = None
        self.person: dict | None = None
        self.challenge: Challenge | None = None
        self.fingerprint: dict | None = None
        self.hint = "Colócate frente a la cámara"
        self.quality_code: str | None = None
        self.face_box: list[float] | None = None
        self.result: dict | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL

    def _threshold(self) -> float:
        return self.ctx.runtime.threshold_for(self.ctx.engines.active_name)

    def _reset_votes(self) -> None:
        self.votes.clear()
        self.quality_frames = 0
        self.best_frame = None
        self.best_score = -1.0

    def _set_box(self, face, image) -> None:
        if face is None:
            self.face_box = None
            return
        h, w = image.shape[:2]
        x1, y1, x2, y2 = (float(v) for v in face.bbox)
        self.face_box = [round(max(x1, 0) / w, 4), round(max(y1, 0) / h, 4), round((x2 - x1) / w, 4), round((y2 - y1) / h, 4)]

    def _consensus(self) -> int | None:
        counts = Counter(v.person_id for v in self.votes if v.person_id is not None)
        if not counts:
            return None
        person_id, count = counts.most_common(1)[0]
        return person_id if count >= self.ctx.settings.consensus_required else None

    def _vote_progress(self) -> float:
        counts = Counter(v.person_id for v in self.votes if v.person_id is not None)
        best = counts.most_common(1)[0][1] if counts else 0
        return round(min(1.0, best / max(self.ctx.settings.consensus_required, 1)), 2)

    def _fail(self, state: State, hint: str, reason: str) -> None:
        self.state = state
        self.hint = hint
        self.result = {"reason": reason}
        log.info("Kiosco: intento fallido (%s)", reason)
        if self.ctx.runtime.save_failed_attempts and (self.best_frame or self.last_frame):
            try:
                save_failed_capture(
                    self.ctx.data_path, self.best_frame or self.last_frame, to_local(self.clock(), self.ctx.tz), reason
                )
            except OSError:
                log.exception("No se pudo guardar la foto del intento fallido")

    def _waiting_hint(self) -> str:
        if self.candidate:
            return f"Hola, {self.candidate['first_name']}: mira a la cámara"
        return "Colócate frente a la cámara"

    # ------------------------------------------------------------------ frames
    def handle_frame(self, jpeg: bytes) -> dict:
        with self.lock:
            now = self.updated_at = self.clock()
            if self.terminal or self.state == State.NEED_CODE:
                if self.state == State.NEED_CODE:
                    self.last_frame = jpeg
                return self.view()
            image = decode_image(jpeg)
            if image is None:
                self.hint = "No se pudo leer la imagen de la cámara"
                return self.view()
            self.last_frame = jpeg
            engines = self.ctx.engines
            if engines.engine is None:
                self.state = State.ERROR
                self.hint = "El motor facial no está disponible. Avisa a RR.HH."
                return self.view()
            index = engines.index
            if self.mode == "identify" and index.person_count == 0:
                self.state = State.NO_ENROLLED
                self.hint = "Pide a RR.HH. que registre y enrole tu rostro"
                self.face_box = None
                return self.view()
            if self.state == State.NO_ENROLLED:
                self.state = State.WAITING
            faces = engines.detect(image)
            if self.state == State.CHALLENGE:
                return self._challenge_frame(image, faces, now)
            return self._identify_frame(jpeg, image, faces, now)

    def _identify_frame(self, jpeg: bytes, image, faces, now: datetime) -> dict:
        settings = self.ctx.settings
        report = evaluate(image, faces, self.ctx.quality_params())
        self._set_box(report.face, image)
        self.quality_code = report.code
        if not report.ok:
            if report.code == "no_face":
                self.no_face_streak += 1
                if self.no_face_streak >= 8 and self.state == State.DETECTING:
                    self._reset_votes()
                    self.state = State.WAITING
                if self.state == State.WAITING:
                    self.hint = self._waiting_hint()
            else:
                self.no_face_streak = 0
                self.state = State.DETECTING
                self.hint = report.message
            return self.view()

        self.no_face_streak = 0
        self.state = State.DETECTING
        emb = self.ctx.engines.embed(image, report.face)
        threshold = self._threshold()
        index = self.ctx.engines.index
        if self.mode == "identify":
            res = index.identify(emb, threshold, self.ctx.runtime.identify_margin)
            vote = Vote(res.person_id if res.accepted else None, res.score, res.margin)
        else:
            ok, score = index.verify(emb, self.candidate["id"], threshold)
            vote = Vote(self.candidate["id"] if ok else None, score, None)
        # Keep evidence in the same bounded window as the identity votes.
        if vote.person_id is not None:
            vote.photo = jpeg
            vote.quality = report.score
        self.votes.append(vote)
        self.quality_frames += 1
        winner = self._consensus()
        if winner is not None:
            return self._on_identified(winner, now)
        if self.quality_frames >= settings.max_identify_frames:
            if self.mode == "verify":
                hint = "Tu rostro no coincide con el registrado. Intenta de nuevo o pide ayuda a RR.HH."
            else:
                hint = "No encontramos coincidencia. Intenta de nuevo o pide ayuda a RR.HH."
            self._fail(State.NOT_RECOGNIZED, hint, "sin_coincidencia")
            return self.view()
        self.hint = "Mantén la mirada al frente"
        return self.view()

    def _on_identified(self, person_id: int, now: datetime) -> dict:
        winning = [v for v in self.votes if v.person_id == person_id]
        best = max(winning, key=lambda v: v.quality)
        self.best_frame = best.photo
        self.best_score = best.quality
        score = sum(v.score for v in winning) / len(winning)
        margins = [v.margin for v in winning if v.margin is not None]
        with self.ctx.session() as db:
            person = db.get(Person, person_id)
            if person is None or not person.active:
                self._fail(State.NOT_RECOGNIZED, "Persona no habilitada. Pide ayuda a RR.HH.", "persona_inactiva")
                return self.view()
            self.person = person_public(person)
            last = last_valid_event(db, person_id)
        self.identified = {
            "person_id": person_id,
            "score": round(score, 4),
            "margin": round(sum(margins) / len(margins), 4) if margins else None,
        }
        if last is not None:
            ago = debounce_seconds_ago(last.ts, now, self.ctx.runtime.debounce_seconds)
            if ago is not None:
                return self._already(last.event_type, ago)
        if self.ctx.runtime.liveness_enabled:
            direction = self.rng.choice(DIRECTIONS)
            self.challenge = Challenge(
                direction=direction, deadline=now + timedelta(seconds=self.ctx.runtime.liveness_timeout_seconds)
            )
            self.state = State.CHALLENGE
            self.hint = f"Gira la cabeza a tu {DIRECTION_TEXT[direction]}"
            return self.view()
        return self._finalize(now, LIVENESS_DISABLED)

    def _challenge_frame(self, image, faces, now: datetime) -> dict:
        ch = self.challenge
        assert ch is not None and self.identified is not None
        if now > ch.deadline:
            self._fail(State.LIVENESS_FAILED, "No detectamos el giro a tiempo. Vuelve a intentarlo.", "tiempo_agotado")
            return self.view()
        main, count = pick_main_face(faces)
        self._set_box(main, image)
        text = DIRECTION_TEXT[ch.direction]
        if main is None:
            self.hint = "No te vemos: vuelve frente a la cámara"
            return self.view()
        if count > 1:
            self.hint = "Debe quedar una sola persona frente a la cámara"
            return self.view()
        emb = self.ctx.engines.embed(image, main)
        factor = self.ctx.settings.liveness_identity_factor
        ok, score = self.ctx.engines.index.verify(emb, self.identified["person_id"], self._threshold() * factor)
        if not ok:
            ch.mismatches += 1
            ch.hits = 0
            if ch.mismatches >= 3:
                self._fail(State.LIVENESS_FAILED, "La persona cambió durante la prueba de vida", "identidad_cambio")
                return self.view()
            self.hint = "Mantén tu rostro dentro del óvalo"
            return self.view()
        ch.min_identity = min(ch.min_identity, score)
        pose = pose_from_kps(main.kps)
        step = evaluate_turn(
            ch.direction,
            user_yaw(pose.yaw, self.ctx.settings.camera_frames_mirrored),
            self.ctx.runtime.liveness_yaw_threshold,
        )
        ch.progress = max(ch.progress, step.progress)
        if step.done:
            ch.hits += 1
            if ch.hits >= self.ctx.settings.liveness_required_frames:
                return self._finalize(now, LIVENESS_PASSED)
            self.hint = "Bien, mantén el giro"
        elif step.wrong_way:
            ch.hits = 0
            self.hint = f"Hacia el otro lado: gira a tu {text}"
        else:
            ch.hits = 0
            self.hint = f"Gira la cabeza a tu {text}"
        return self.view()

    def _already(self, last_type: str, seconds_ago: int) -> dict:
        self.state = State.ALREADY
        self.hint = already_message(last_type, seconds_ago)
        self.result = {
            "person": self.person,
            "last_type": last_type,
            "seconds_ago": seconds_ago,
            "message": self.hint,
            "summary": self._summary(),
        }
        return self.view()

    def _summary(self) -> dict | None:
        """Resumen personal (semana + últimas marcaciones) para la persona ya identificada."""
        if not self.identified:
            return None
        try:
            # Sesión nueva: la marcación recién confirmada debe ser visible.
            with self.ctx.session() as db:
                return personal_summary(
                    db,
                    person_id=self.identified["person_id"],
                    now=self.clock(),
                    tz=self.ctx.tz,
                    max_shift_hours=self.ctx.runtime.max_shift_hours,
                )
        except Exception:  # noqa: BLE001 - el resumen nunca debe impedir la marcación
            log.exception("No se pudo calcular el resumen personal")
            return None

    def _finalize(self, now: datetime, liveness: str) -> dict:
        assert self.identified is not None
        runtime = self.ctx.runtime
        # Fingerprint-only captures are contextual evidence, not face verification.
        photo = self.last_frame if self.method == METHOD_FINGERPRINT else self.best_frame
        engine_name = self.ctx.engines.active_name
        with self.ctx.session() as db:
            person = db.get(Person, self.identified["person_id"])
            try:
                reg = register_event(
                    db,
                    person=person,
                    method=self.method,
                    now=now,
                    tz=self.ctx.tz,
                    data_path=self.ctx.data_path,
                    max_shift_hours=runtime.max_shift_hours,
                    debounce_seconds=runtime.debounce_seconds,
                    photo=photo,
                    face_score=self.identified.get("score"),
                    face_threshold=self._threshold() if self.identified.get("score") is not None else None,
                    face_margin=self.identified.get("margin"),
                    fingerprint_score=self.fingerprint.get("score") if self.fingerprint else None,
                    liveness=liveness,
                    liveness_challenge=self.challenge.direction if self.challenge else None,
                    engine=engine_name if self.identified.get("score") is not None else None,
                )
            except AlreadyRegistered as exc:
                return self._already(exc.last_type, exc.seconds_ago)
            self.person = person_public(person)
        event = reg.event
        self.state = State.SUCCESS
        local_hhmm = fmt_time(event.ts, self.ctx.tz, seconds=False)
        if event.event_type == SALIDA and reg.worked_seconds is not None:
            self.hint = f"{person.first_name}, salida a las {local_hhmm}. Jornada de {reg.worked()['worked_hhmm']} h"
        else:
            self.hint = f"{person.first_name}, entrada a las {local_hhmm}"
        self.result = {
            "event_id": event.id,
            "event_type": event.event_type,
            "local_date": fmt_date(event.ts, self.ctx.tz),
            "local_time": fmt_time(event.ts, self.ctx.tz, seconds=False),
            "person": self.person,
            "method": event.method,
            "face_score": event.face_score,
            "face_threshold": event.face_threshold,
            "fingerprint_score": event.fingerprint_score,
            "liveness": event.liveness,
            "photo": ("data:image/jpeg;base64," + base64.b64encode(photo).decode()) if photo else None,
            **(reg.worked() if event.event_type == SALIDA else {"worked_hours": None, "worked_hhmm": None}),
            "summary": self._summary(),
        }
        return self.view()

    # ------------------------------------------------------------------ huella / código
    def handle_fingerprint(self, result: FingerprintResult) -> dict:
        with self.lock:
            now = self.updated_at = self.clock()
            if self.terminal or self.state == State.CHALLENGE:
                return self.view()
            if result.person_id is None and result.slot is not None:
                with self.ctx.session() as db:
                    result.person_id = db.scalar(
                        select(Person.id).where(Person.fingerprint_slot == result.slot, Person.active.is_(True))
                    )
            settings = self.ctx.settings
            runtime = self.ctx.runtime
            level = classify(result, settings.fingerprint_high_score, settings.fingerprint_medium_score)
            route = decide(
                True, result, settings.fingerprint_high_score, settings.fingerprint_medium_score, runtime.fallback_mode
            )
            self.fingerprint = {"status": result.status.value, "score": result.score, "level": level.value}
            if route.kind == RouteKind.FINGERPRINT_ONLY:
                with self.ctx.session() as db:
                    person = db.get(Person, route.person_id)
                    if person is None or not person.active:
                        self._fail(State.NOT_RECOGNIZED, "Huella de una persona no habilitada", "persona_inactiva")
                        return self.view()
                    self.person = person_public(person)
                    last = last_valid_event(db, person.id)
                self.method = route.method
                self.identified = {"person_id": route.person_id, "score": None, "margin": None}
                if last is not None:
                    ago = debounce_seconds_ago(last.ts, now, runtime.debounce_seconds)
                    if ago is not None:
                        return self._already(last.event_type, ago)
                return self._finalize(now, LIVENESS_NOT_APPLICABLE)
            if route.kind == RouteKind.FACE_VERIFY:
                with self.ctx.session() as db:
                    person = db.get(Person, route.person_id)
                    info = person_public(person) if person is not None and person.active else None
                if info is None or not self.ctx.engines.index.has_person(route.person_id):
                    self._fail(
                        State.NOT_RECOGNIZED,
                        "Tu huella coincide en parte, pero no tienes rostro enrolado. Pide ayuda a RR.HH.",
                        "sin_rostro_enrolado",
                    )
                    return self.view()
                self.mode = "verify"
                self.method = METHOD_FINGERPRINT_FACE
                self.candidate = info
                self._reset_votes()
                self.state = State.DETECTING
                self.hint = "Huella reconocida en parte: mira a la cámara"
                return self.view()
            if route.kind == RouteKind.CODE_PLUS_FACE:
                self.state = State.NEED_CODE
                self.method = METHOD_CODE_FACE
                self.hint = "No reconocimos tu huella. Ingresa tu código de estudiante"
                return self.view()
            self.mode = "identify"
            self.method = METHOD_FACE
            self.candidate = None
            self._reset_votes()
            self.state = State.WAITING
            self.hint = "No reconocimos tu huella: mira a la cámara"
            return self.view()

    def handle_code(self, code: str) -> dict:
        with self.lock:
            self.updated_at = self.clock()
            if self.terminal or self.state == State.CHALLENGE:
                return self.view()
            clean = (code or "").strip()
            if not clean:
                raise AppError("Escribe tu código de estudiante")
            with self.ctx.session() as db:
                person = db.scalar(select(Person).where(func.lower(Person.code) == clean.lower(), Person.active.is_(True)))
                info = person_public(person) if person else None
            if info is None:
                raise AppError("No hay una persona activa con ese código", status_code=404, code="code_not_found")
            if not self.ctx.engines.index.has_person(info["id"]):
                raise AppError(
                    "Esta persona no tiene rostro enrolado con el motor activo. Pide ayuda a RR.HH.",
                    status_code=409,
                    code="not_enrolled",
                )
            self.mode = "verify"
            self.method = METHOD_CODE_FACE
            self.candidate = info
            self._reset_votes()
            self.state = State.WAITING
            self.hint = self._waiting_hint()
            return self.view()

    def cancel(self) -> dict:
        with self.lock:
            if not self.terminal:
                self.state = State.CANCELLED
                self.hint = "Sesión cancelada"
            return self.view()

    # ------------------------------------------------------------------ vista
    def view(self) -> dict:
        title = TITLES[self.state]
        if self.state == State.SUCCESS and self.result:
            title = f"{self.result['event_type']} registrada"
        challenge = None
        progress = self._vote_progress()
        if self.state == State.CHALLENGE and self.challenge is not None:
            remaining = max(0.0, (self.challenge.deadline - self.clock()).total_seconds())
            challenge = {
                "direction": self.challenge.direction,
                "text": DIRECTION_TEXT[self.challenge.direction],
                "remaining_seconds": round(remaining, 1),
                "timeout_seconds": self.ctx.runtime.liveness_timeout_seconds,
                "progress": round(self.challenge.progress, 2),
            }
            progress = round(self.challenge.progress, 2)
        return {
            "id": self.id,
            "state": self.state.value,
            "terminal": self.terminal,
            "title": title,
            "hint": self.hint,
            "quality": self.quality_code,
            "face_box": self.face_box,
            "mode": self.mode,
            "method": self.method,
            "progress": progress,
            "challenge": challenge,
            "candidate": {"first_name": self.candidate["first_name"], "code": self.candidate["code"]}
            if self.candidate
            else None,
            "fingerprint": self.fingerprint,
            "result": self.result,
        }


class SessionManager:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self._sessions: dict[str, KioskSession] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        ttl = timedelta(seconds=self.ctx.settings.kiosk_session_ttl_seconds)
        now = utcnow()
        for sid in [sid for sid, s in self._sessions.items() if now - s.updated_at > ttl]:
            self._sessions.pop(sid, None)
        if len(self._sessions) > 20:
            for sid, _ in sorted(self._sessions.items(), key=lambda kv: kv[1].updated_at)[: len(self._sessions) - 20]:
                self._sessions.pop(sid, None)

    def create(self) -> KioskSession:
        with self._lock:
            self._purge()
            session = KioskSession(self.ctx)
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> KioskSession:
        with self._lock:
            self._purge()
            session = self._sessions.get(session_id)
        if session is None:
            raise AppError("La sesión del kiosco expiró; se reinicia sola.", status_code=404, code="session_expired")
        return session

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
