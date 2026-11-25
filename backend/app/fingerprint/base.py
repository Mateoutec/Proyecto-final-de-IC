"""Interfaz `FingerprintProvider` y proveedores `disabled` / `simulated`."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from app.errors import AppError

log = logging.getLogger("app.fingerprint")


class FingerprintStatus(str, Enum):
    MATCH = "match"
    NO_MATCH = "no_match"
    BAD_IMAGE = "bad_image"
    NO_FINGER = "no_finger"
    ERROR = "error"


@dataclass
class FingerprintResult:
    status: FingerprintStatus
    slot: int | None = None
    score: float | None = None
    person_id: int | None = None
    detail: str = ""


class FingerprintProvider(ABC):
    name = "base"
    experimental = False

    @abstractmethod
    def status(self) -> dict:
        """Estado para el panel y el kiosco."""

    def scan(self, timeout_s: float) -> FingerprintResult:
        raise AppError("Este proveedor de huella no puede leer el sensor", status_code=409)

    def enroll(self, slot: int, timeout_s: float = 20.0) -> bytes | None:
        raise AppError("Este proveedor de huella no permite enrolar", status_code=409)

    def delete(self, slot: int) -> None:
        return None

    def restore(self, slot: int, template: bytes) -> None:
        raise AppError("Este proveedor de huella no permite restaurar plantillas", status_code=409)

    def close(self) -> None:
        return None


class DisabledProvider(FingerprintProvider):
    name = "disabled"

    def status(self) -> dict:
        return {
            "provider": self.name,
            "connected": False,
            "configured": False,
            "label": "No conectada (opcional)",
            "detail": "FINGERPRINT_PROVIDER=disabled. La huella llega en la v2.",
            "experimental": False,
        }

    def scan(self, timeout_s: float) -> FingerprintResult:
        raise AppError("La huella no está configurada (FINGERPRINT_PROVIDER=disabled)", status_code=409)


SIMULATED_SCORES = {"high": 200.0, "medium": 60.0}


class SimulatedProvider(FingerprintProvider):
    """Simula lecturas para probar la lógica multimodal sin hardware."""

    name = "simulated"

    def status(self) -> dict:
        return {
            "provider": self.name,
            "connected": True,
            "configured": True,
            "label": "Simulada (pruebas)",
            "detail": "Panel de pruebas visible en el kiosco.",
            "experimental": False,
        }

    def simulate(self, person_id: int | None, slot: int | None, level: str) -> FingerprintResult:
        if level == "bad_image":
            return FingerprintResult(FingerprintStatus.BAD_IMAGE, detail="Imagen de huella deficiente (simulada)")
        if level not in SIMULATED_SCORES or person_id is None:
            return FingerprintResult(FingerprintStatus.NO_MATCH, score=0.0, detail="Sin coincidencia (simulada)")
        return FingerprintResult(
            FingerprintStatus.MATCH,
            slot=slot,
            score=SIMULATED_SCORES[level],
            person_id=person_id,
            detail=f"Coincidencia {level} (simulada)",
        )

    def enroll(self, slot: int, timeout_s: float = 20.0) -> bytes | None:
        return None


def create_provider(settings) -> FingerprintProvider:
    name = settings.fingerprint_provider
    if name == "simulated":
        return SimulatedProvider()
    if name == "as608":
        from app.fingerprint.as608 import AS608Provider

        return AS608Provider(settings.fingerprint_port, settings.fingerprint_baudrate)
    return DisabledProvider()
