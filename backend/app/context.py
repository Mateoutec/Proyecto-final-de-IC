"""Contexto de la aplicación: base de datos, motores, huella, configuración y sesiones."""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.crypto import TemplateCipher
from app.db import create_db_engine, create_session_factory, init_db, utcnow
from app.errors import AppError
from app.face.liveness import NoPassiveLiveness, PassiveLivenessChecker
from app.face.manager import EngineManager
from app.face.quality import QualityParams
from app.fingerprint.base import create_provider
from app.logging_setup import setup_logging
from app.models import FaceTemplate, Person
from app.services import runtime_config
from app.services.audit import audit
from app.timeutil import get_tz

log = logging.getLogger("app.context")

DATA_SUBDIRS = ("captures", "enrollment", "logs", "calibration")


def prepare_data_dir(settings: Settings) -> None:
    data = settings.data_path
    data.mkdir(parents=True, exist_ok=True)
    for sub in DATA_SUBDIRS:
        (data / sub).mkdir(exist_ok=True)
    if os.name == "posix":
        os.chmod(data, 0o700)


class AppContext:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.data_path = settings.data_path
        prepare_data_dir(settings)
        setup_logging(self.data_path / "logs", settings.log_level)
        self.db_engine = create_db_engine(settings.database_path)
        init_db(self.db_engine)
        self.SessionLocal = create_session_factory(self.db_engine)
        self.cipher = TemplateCipher(settings.encryption_key)
        if not self.cipher.available:
            log.error(self.cipher.error)
        with self.session() as db:
            self.runtime = runtime_config.load_runtime(settings, db)
        self.tz = get_tz(settings.timezone)
        self.engines = EngineManager(settings.models_path)
        self.engines.load(self.runtime.face_engine)
        self.undecryptable_templates = 0
        self.reload_templates()
        self.fingerprint = create_provider(settings)
        self.passive_liveness: PassiveLivenessChecker = NoPassiveLiveness()
        from app.kiosk.session import SessionManager

        self.kiosk = SessionManager(self)
        self.started_at = utcnow()

    def session(self) -> Session:
        return self.SessionLocal()

    def now(self):
        return utcnow()

    def quality_params(self, upload: bool = False) -> QualityParams:
        s = self.settings
        return QualityParams(
            min_face_ratio=s.min_face_ratio,
            max_face_ratio=s.max_face_ratio,
            min_face_px=s.min_face_px_upload if upload else 0,
            min_sharpness=self.runtime.min_sharpness * (0.5 if upload else 1.0),
            min_brightness=s.min_brightness,
            max_brightness=s.max_brightness,
            max_frontal_yaw=self.runtime.max_frontal_yaw,
            max_roll_degrees=s.max_roll_degrees,
            check_center=not upload,
        )

    def reload_templates(self) -> None:
        name = self.engines.active_name
        if not name or not self.cipher.available:
            self.engines.index.load(name or "", [])
            return
        with self.session() as db:
            rows = db.execute(
                select(FaceTemplate.person_id, FaceTemplate.embedding_enc)
                .join(Person, Person.id == FaceTemplate.person_id)
                .where(FaceTemplate.engine == name, Person.active.is_(True))
            ).all()
        decoded, bad = [], 0
        for person_id, token in rows:
            try:
                decoded.append((person_id, self.cipher.decrypt_embedding(token)))
            except AppError:
                bad += 1
        if bad:
            log.error("%s plantillas no se pudieron descifrar (¿cambió ENCRYPTION_KEY?). Re-indexa.", bad)
        self.undecryptable_templates = bad
        self.engines.index.load(name, decoded)
        log.info("Índice facial (%s): %s plantillas de %s personas", name, len(decoded), self.engines.index.person_count)

    def update_runtime(self, changes: dict[str, Any], actor: str) -> runtime_config.RuntimeConfig:
        new, diff = runtime_config.apply_changes(self.runtime, changes)
        if not diff:
            return self.runtime
        with self.session() as db:
            runtime_config.persist(db, diff)
            audit(db, actor, "configuracion", "settings", None, changes=diff)
            db.commit()
        old_engine = self.runtime.face_engine
        self.runtime = new
        if "face_engine" in diff and new.face_engine != old_engine:
            self.engines.load(new.face_engine)
            self.reload_templates()
        log.info("Configuración actualizada por %s: %s", actor, diff)
        return self.runtime

    def fingerprint_status(self) -> dict:
        try:
            return self.fingerprint.status()
        except Exception as exc:  # noqa: BLE001
            return {"provider": self.fingerprint.name, "connected": False, "label": "Error", "detail": str(exc)}

    def close(self) -> None:
        self.fingerprint.close()
        self.db_engine.dispose()
