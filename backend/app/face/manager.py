"""Carga del motor facial activo con respaldo automático a SFace."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

from app.face.base import DetectedFace, FaceEngine
from app.face.index import TemplateIndex

log = logging.getLogger("app.face.manager")


def build_engine(name: str, models_dir: Path) -> FaceEngine:
    if name == "insightface":
        from app.face.insightface_engine import InsightFaceEngine

        return InsightFaceEngine(models_dir / "buffalo_l")
    if name == "sface":
        from app.face.sface_engine import SFaceEngine

        return SFaceEngine(models_dir / "opencv")
    if name == "fake":
        from app.face.fake_engine import FakeEngine

        return FakeEngine()
    raise ValueError(f"Motor facial desconocido: {name}")


class EngineManager:
    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self.engine: FaceEngine | None = None
        self.requested: str | None = None
        self.fallback_reason: str | None = None
        self.error: str | None = None
        self.index = TemplateIndex()
        self._lock = threading.RLock()
        self._cache: dict[str, FaceEngine] = {}

    def _get_or_build(self, name: str) -> FaceEngine:
        if name not in self._cache:
            self._cache[name] = build_engine(name, self.models_dir)
        return self._cache[name]

    def load(self, requested: str) -> FaceEngine | None:
        with self._lock:
            self.requested = requested
            self.fallback_reason = None
            self.error = None
            try:
                self.engine = self._get_or_build(requested)
                log.info("Motor facial activo: %s", requested)
                return self.engine
            except Exception as exc:  # noqa: BLE001
                reason = f"No se pudo cargar '{requested}': {exc}"
                log.error(reason)
                if requested in ("sface", "fake"):
                    self.engine = None
                    self.error = reason
                    return None
                self.fallback_reason = reason
            try:
                self.engine = self._get_or_build("sface")
                log.warning("Se usa el motor de respaldo SFace. Motivo: %s", self.fallback_reason)
                return self.engine
            except Exception as exc:  # noqa: BLE001
                self.engine = None
                self.error = f"{self.fallback_reason}. Tampoco se pudo cargar SFace: {exc}"
                log.error(self.error)
                return None

    def engine_for(self, name: str) -> FaceEngine:
        """Motor por nombre (para re-indexar con un motor distinto al activo)."""
        with self._lock:
            return self._get_or_build(name)

    @property
    def active_name(self) -> str | None:
        return self.engine.name if self.engine else None

    def detect(self, image: np.ndarray) -> list[DetectedFace]:
        with self._lock:
            if self.engine is None:
                raise RuntimeError(self.error or "Motor facial no disponible")
            return self.engine.detect(image)

    def embed(self, image: np.ndarray, face: DetectedFace) -> np.ndarray:
        with self._lock:
            if self.engine is None:
                raise RuntimeError(self.error or "Motor facial no disponible")
            return self.engine.embed(image, face)

    def status(self) -> dict:
        return {
            "requested": self.requested,
            "active": self.active_name,
            "description": self.engine.description if self.engine else None,
            "embedding_dim": self.engine.embedding_dim if self.engine else None,
            "fallback": self.fallback_reason is not None,
            "fallback_reason": self.fallback_reason,
            "error": self.error,
            "ready": self.engine is not None,
            "enrolled_people": self.index.person_count,
            "templates_loaded": self.index.template_count,
        }
