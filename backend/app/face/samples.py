"""Rostros de ejemplo para pruebas con motores reales (imagen 't1' de InsightFace)."""

from __future__ import annotations

import cv2
import numpy as np

from app.config import PROJECT_ROOT
from app.face.base import FaceEngine, pose_from_kps

SAMPLE_PATH = PROJECT_ROOT / "models" / "samples" / "t1.jpg"


def load_sample_image() -> np.ndarray | None:
    """`insightface.data.get_image('t1')` si el paquete está instalado; si no, la copia descargada en el setup."""
    try:
        from insightface.data import get_image  # type: ignore[import-not-found]

        return get_image("t1")
    except Exception:  # noqa: BLE001
        pass
    if SAMPLE_PATH.exists():
        return cv2.imread(str(SAMPLE_PATH))
    return None


def face_frames(
    image: np.ndarray,
    engine: FaceEngine,
    face_px: int = 200,
    scale_jitter: float = 1.0,
    angle_jitter: float = 0.0,
    brightness: int = 0,
    width: int = 640,
    height: int = 480,
    max_abs_yaw: float | None = 0.4,
) -> list[np.ndarray]:
    """Un frame 640x480 por rostro detectado, centrado, enderezado y aislado del resto.

    Con `max_abs_yaw` se descartan los rostros de perfil (no servirían para enrolar).
    """
    faces = sorted(engine.detect(image), key=lambda f: float(f.bbox[0]))
    if max_abs_yaw is not None:
        faces = [f for f in faces if abs(pose_from_kps(f.kps).yaw) <= max_abs_yaw]
    frames = []
    for face in faces:
        cx = float(face.bbox[0] + face.bbox[2]) / 2
        cy = float(face.bbox[1] + face.bbox[3]) / 2
        roll = pose_from_kps(face.kps).roll
        scale = face_px / max(face.width, 1.0) * scale_jitter
        matrix = cv2.getRotationMatrix2D((cx, cy), roll + angle_jitter, scale)
        matrix[0, 2] += width / 2 - cx
        matrix[1, 2] += height / 2 - cy
        frame = cv2.warpAffine(image, matrix, (width, height), borderValue=(110, 110, 110))
        mask = np.zeros((height, width), dtype=np.uint8)
        axes = (int(face_px * scale_jitter * 0.95), int(face_px * scale_jitter * 1.25))
        cv2.ellipse(mask, (width // 2, height // 2), axes, 0, 0, 360, 255, -1)
        background = np.full_like(frame, 110)
        frame = np.where(mask[..., None] > 0, frame, background)
        if brightness:
            frame = np.clip(frame.astype(np.int16) + brightness, 0, 255).astype(np.uint8)
        frames.append(frame)
    return frames
