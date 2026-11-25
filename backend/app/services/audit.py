"""Registro de auditoría."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

ACTION_LABELS = {
    "login": "Inicio de sesión",
    "login_fallido": "Intento de inicio de sesión fallido",
    "area_creada": "Área creada",
    "area_editada": "Área editada",
    "area_eliminada": "Área eliminada",
    "persona_creada": "Persona registrada",
    "persona_editada": "Persona editada",
    "persona_eliminada": "Persona eliminada",
    "enrolamiento": "Enrolamiento facial",
    "plantilla_eliminada": "Plantilla facial eliminada",
    "biometria_eliminada": "Datos biométricos eliminados",
    "huella_enrolada": "Huella enrolada",
    "huella_eliminada": "Huella eliminada",
    "marcacion_manual": "Marcación manual",
    "marcacion_anulada": "Marcación anulada",
    "exportacion": "Exportación",
    "configuracion": "Cambio de configuración",
    "reindexado": "Re-indexado de plantillas",
    "calibracion": "Calibración",
    "seed_demo": "Datos de demostración",
}


def audit(
    db: Session,
    actor: str,
    action: str,
    entity_type: str | None = None,
    entity_id: Any = None,
    **details: Any,
) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=json.dumps(details, ensure_ascii=False, default=str) if details else None,
        )
    )
