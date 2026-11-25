"""Servidor aislado para las pruebas E2E de Playwright (puerto 8766, datos temporales).

Carga datos de demostración y enrola un rostro de la imagen de ejemplo para que el
kiosco quede en estado "esperando". Uso: uv run python scripts/e2e_server.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from cryptography.fernet import Fernet

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import Settings  # noqa: E402
from app.context import AppContext  # noqa: E402
from app.face.base import encode_jpeg  # noqa: E402
from app.face.samples import face_frames, load_sample_image  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Person  # noqa: E402
from app.seed import seed_demo  # noqa: E402
from app.services.enrollment import enroll_photo  # noqa: E402

PORT = 8766
PASSWORD = "e2e-clave-2026"
Y4M_PATH = BACKEND.parent / "frontend" / "e2e" / "fixtures" / "rostro.y4m"


def write_y4m(frame_bgr: np.ndarray, path: Path, frames: int = 20) -> None:
    """Video Y4M (I420) para --use-file-for-fake-video-capture de Chromium."""
    h, w = frame_bgr.shape[:2]
    yuv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YUV_I420)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(f"YUV4MPEG2 W{w} H{h} F10:1 Ip A1:1 C420jpeg\n".encode())
        for _ in range(frames):
            fh.write(b"FRAME\n")
            fh.write(yuv.tobytes())


def main() -> None:
    data = tempfile.mkdtemp(prefix="asistencia_e2e_")
    settings = Settings(
        _env_file=None,
        data_dir=data,
        admin_password=PASSWORD,
        session_secret="e2e",
        encryption_key=Fernet.generate_key().decode(),
        face_engine="sface",
        fingerprint_provider="disabled",
        timezone="America/Lima",
        max_frontal_yaw=0.45,
    )
    ctx = AppContext(settings)
    seed_demo(ctx)
    image = load_sample_image()
    if image is not None and ctx.engines.engine is not None:
        frame = face_frames(image, ctx.engines.engine)[0]
        probe = face_frames(image, ctx.engines.engine, scale_jitter=1.04, brightness=-8)[0]
        write_y4m(probe, Y4M_PATH)
        with ctx.session() as db:
            person = Person(code="U2026001", first_name="Valentina", last_name="Ejemplo", consent_signed=True)
            db.add(person)
            db.commit()
            enroll_photo(ctx, db, person, encode_jpeg(frame), "frontal", "camera", False, "e2e")
    app = create_app(settings)
    app.state.ctx = ctx
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
