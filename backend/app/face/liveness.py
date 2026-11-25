"""Prueba de vida activa (giro de cabeza) e interfaz para anti-spoofing pasivo futuro."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.face.base import DetectedFace

DIRECTIONS = ("left", "right")
DIRECTION_TEXT = {"left": "izquierda", "right": "derecha"}


def user_yaw(raw_yaw: float, frames_mirrored: bool) -> float:
    """Convierte el yaw de la imagen a la perspectiva de la persona.

    Los frames llegan sin espejar: si la persona gira a SU izquierda, la nariz se
    desplaza hacia la derecha de la imagen (yaw > 0). La vista del kiosco está
    espejada, así que "izquierda" en pantalla coincide con la izquierda de la persona.
    """
    return -raw_yaw if frames_mirrored else raw_yaw


@dataclass
class ChallengeStep:
    done: bool
    wrong_way: bool
    progress: float


def evaluate_turn(direction: str, yaw_user: float, threshold: float) -> ChallengeStep:
    target = 1.0 if direction == "left" else -1.0
    signed = yaw_user * target
    progress = float(np.clip(signed / threshold, 0.0, 1.0)) if threshold > 0 else 1.0
    return ChallengeStep(done=signed >= threshold, wrong_way=signed <= -0.8 * threshold, progress=progress)


@dataclass
class PassiveResult:
    live: bool
    score: float | None
    detail: str


class PassiveLivenessChecker(Protocol):
    """Punto de extensión para anti-spoofing pasivo (p. ej., un modelo MiniFASNet en v2)."""

    name: str

    def check(self, image_bgr: np.ndarray, face: DetectedFace) -> PassiveResult: ...


class NoPassiveLiveness:
    name = "ninguno"

    def check(self, image_bgr: np.ndarray, face: DetectedFace) -> PassiveResult:
        return PassiveResult(live=True, score=None, detail="anti-spoofing pasivo no configurado")
