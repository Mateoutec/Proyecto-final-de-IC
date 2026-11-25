"""Configuración base leída de `.env` (Pydantic Settings).

Los valores editables desde el panel (umbrales, anti-rebote, etc.) se guardan como
overrides en la base de datos; ver `app.services.runtime_config`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EngineName = Literal["insightface", "sface", "fake"]
FallbackMode = Literal["face", "code_plus_face"]
FingerprintProviderName = Literal["disabled", "simulated", "as608"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Servidor (siempre 127.0.0.1; ver app/__main__.py)
    port: int = 8000
    log_level: str = "INFO"

    # Rutas (relativas a la raíz del proyecto)
    data_dir: str = "data"
    models_dir: str = "models"

    # Seguridad
    admin_password: str = ""
    session_secret: str = ""
    encryption_key: str = ""
    admin_session_hours: int = 12
    # Dominios extra aceptados (despliegue en la nube detrás de HTTPS), separados por coma
    allowed_hosts: str = ""

    # Zona horaria para mostrar fechas (vacío = la del sistema)
    timezone: str = ""

    # Motor facial
    face_engine: EngineName = "insightface"
    threshold_insightface: float = 0.45
    threshold_sface: float = 0.363
    threshold_fake: float = 0.80
    identify_margin: float = 0.06
    consensus_window: int = 5
    consensus_required: int = 3
    max_identify_frames: int = 15

    # Calidad por frame
    min_face_ratio: float = 0.14
    max_face_ratio: float = 0.80
    min_face_px_upload: int = 80
    min_sharpness: float = 25.0
    min_brightness: float = 60.0
    max_brightness: float = 215.0
    max_frontal_yaw: float = 0.15
    max_roll_degrees: float = 20.0

    # Prueba de vida
    liveness_enabled: bool = True
    liveness_timeout_seconds: float = 7.0
    liveness_yaw_threshold: float = 0.18
    liveness_identity_factor: float = 0.80
    liveness_required_frames: int = 2
    camera_frames_mirrored: bool = False

    # Asistencia
    debounce_seconds: int = 120
    max_shift_hours: float = 16.0
    save_failed_attempts: bool = False
    fallback_mode: FallbackMode = "face"

    # Huella
    fingerprint_provider: FingerprintProviderName = "disabled"
    fingerprint_port: str = "/dev/tty.usbserial-0001"
    fingerprint_baudrate: int = 57600
    fingerprint_high_score: float = 100.0
    fingerprint_medium_score: float = 40.0
    fingerprint_scan_timeout: float = 8.0

    # Exportación
    csv_delimiter: str = Field(default=",", max_length=1)

    # Kiosco
    kiosk_session_ttl_seconds: int = 90

    @property
    def data_path(self) -> Path:
        return _resolve(self.data_dir)

    @property
    def models_path(self) -> Path:
        return _resolve(self.models_dir)

    @property
    def database_path(self) -> Path:
        return self.data_path / "asistencia.db"


def _resolve(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()
