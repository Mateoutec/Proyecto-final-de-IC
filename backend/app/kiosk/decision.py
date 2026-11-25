"""Tabla de decisión multimodal (huella + rostro). Función pura, testeada aparte."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain import METHOD_CODE_FACE, METHOD_FACE, METHOD_FINGERPRINT, METHOD_FINGERPRINT_FACE
from app.fingerprint.base import FingerprintResult, FingerprintStatus


class FingerprintLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    NONE = "none"


class RouteKind(str, Enum):
    FINGERPRINT_ONLY = "fingerprint_only"  # acceso por huella (la foto se guarda igual)
    FACE_VERIFY = "face_verify"  # candidato por huella -> rostro 1:1 + prueba de vida
    FACE_IDENTIFY = "face_identify"  # rostro 1:N + prueba de vida
    CODE_PLUS_FACE = "code_plus_face"  # código de estudiante + rostro 1:1


@dataclass(frozen=True)
class Route:
    kind: RouteKind
    method: str
    person_id: int | None = None


def classify(result: FingerprintResult | None, high: float, medium: float) -> FingerprintLevel:
    if result is None or result.status != FingerprintStatus.MATCH or result.person_id is None:
        return FingerprintLevel.NONE
    score = result.score or 0.0
    if score >= high:
        return FingerprintLevel.HIGH
    if score >= medium:
        return FingerprintLevel.MEDIUM
    return FingerprintLevel.NONE


def decide(
    fingerprint_configured: bool,
    result: FingerprintResult | None,
    high: float,
    medium: float,
    fallback_mode: str,
) -> Route:
    if not fingerprint_configured or result is None:
        return Route(RouteKind.FACE_IDENTIFY, METHOD_FACE)
    level = classify(result, high, medium)
    if level == FingerprintLevel.HIGH:
        return Route(RouteKind.FINGERPRINT_ONLY, METHOD_FINGERPRINT, result.person_id)
    if level == FingerprintLevel.MEDIUM:
        return Route(RouteKind.FACE_VERIFY, METHOD_FINGERPRINT_FACE, result.person_id)
    if fallback_mode == "code_plus_face":
        return Route(RouteKind.CODE_PLUS_FACE, METHOD_CODE_FACE)
    return Route(RouteKind.FACE_IDENTIFY, METHOD_FACE)
