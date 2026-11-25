"""Configuración editable desde el panel: `.env` como base + overrides en `app_settings`."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError
from app.models import AppSetting


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    face_engine: Literal["insightface", "sface", "fake"]
    threshold_insightface: float = Field(ge=0.05, le=0.99)
    threshold_sface: float = Field(ge=0.05, le=0.99)
    threshold_fake: float = Field(ge=0.05, le=0.99)
    identify_margin: float = Field(ge=0.0, le=0.5)
    debounce_seconds: int = Field(ge=0, le=3600)
    max_shift_hours: float = Field(ge=1, le=48)
    liveness_enabled: bool
    liveness_timeout_seconds: float = Field(ge=2, le=30)
    liveness_yaw_threshold: float = Field(ge=0.05, le=0.6)
    fallback_mode: Literal["face", "code_plus_face"]
    save_failed_attempts: bool
    csv_delimiter: Literal[",", ";", "\t", "|"]
    min_sharpness: float = Field(ge=0, le=1000)
    max_frontal_yaw: float = Field(ge=0.05, le=0.8)

    def threshold_for(self, engine: str | None) -> float:
        return {
            "insightface": self.threshold_insightface,
            "sface": self.threshold_sface,
            "fake": self.threshold_fake,
        }.get(engine or "", self.threshold_insightface)


EDITABLE_KEYS = tuple(RuntimeConfig.model_fields)

LABELS = {
    "face_engine": "Motor facial",
    "threshold_insightface": "Umbral InsightFace",
    "threshold_sface": "Umbral SFace",
    "threshold_fake": "Umbral motor de pruebas",
    "identify_margin": "Margen entre 1.º y 2.º candidato",
    "debounce_seconds": "Anti-rebote (s)",
    "max_shift_hours": "Duración máxima de jornada (h)",
    "liveness_enabled": "Prueba de vida",
    "liveness_timeout_seconds": "Tiempo límite de la prueba de vida (s)",
    "liveness_yaw_threshold": "Giro mínimo requerido",
    "fallback_mode": "Modo de respaldo",
    "save_failed_attempts": "Guardar foto de intentos fallidos",
    "csv_delimiter": "Separador CSV",
    "min_sharpness": "Nitidez mínima",
    "max_frontal_yaw": "Giro máximo para considerar 'de frente'",
}


def defaults_from_settings(settings: Settings) -> dict[str, Any]:
    return {key: getattr(settings, key) for key in EDITABLE_KEYS}


def load_runtime(settings: Settings, db: Session) -> RuntimeConfig:
    values = defaults_from_settings(settings)
    for row in db.scalars(select(AppSetting)):
        if row.key in values:
            try:
                values[row.key] = json.loads(row.value)
            except json.JSONDecodeError:
                continue
    try:
        return RuntimeConfig.model_validate(values)
    except ValidationError:
        # Un override inválido no debe impedir el arranque: se vuelve a .env.
        return RuntimeConfig.model_validate(defaults_from_settings(settings))


def apply_changes(current: RuntimeConfig, changes: dict[str, Any]) -> tuple[RuntimeConfig, dict[str, Any]]:
    unknown = [k for k in changes if k not in EDITABLE_KEYS]
    if unknown:
        raise AppError(f"Parámetros no editables: {', '.join(unknown)}")
    merged = {**current.model_dump(), **changes}
    try:
        new = RuntimeConfig.model_validate(merged)
    except ValidationError as exc:
        err = exc.errors()[0]
        field = str(err["loc"][0]) if err.get("loc") else "valor"
        raise AppError(f"Valor inválido para '{LABELS.get(field, field)}': {err['msg']}") from exc
    diff = {k: v for k, v in new.model_dump().items() if current.model_dump()[k] != v}
    return new, diff


def persist(db: Session, diff: dict[str, Any]) -> None:
    for key, value in diff.items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=json.dumps(value)))
        else:
            row.value = json.dumps(value)
