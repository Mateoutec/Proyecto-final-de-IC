"""Motor `sface` (respaldo, Apache-2.0): OpenCV YuNet + SFace del OpenCV Zoo."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from app.face.base import DetectedFace, FaceEngine, l2_normalize, normalize_kps

log = logging.getLogger("app.face.sface")

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"


class SFaceEngine(FaceEngine):
    name = "sface"
    embedding_dim = 128
    description = "OpenCV YuNet + SFace (128-d)"

    def __init__(self, model_dir: Path, score_threshold: float = 0.7):
        det_path = model_dir / YUNET_FILE
        rec_path = model_dir / SFACE_FILE
        for path in (det_path, rec_path):
            if not path.exists():
                raise FileNotFoundError(f"Falta el modelo {path}. Ejecuta: uv run python -m app.cli download-models")
        if not hasattr(cv2, "FaceDetectorYN"):
            raise RuntimeError("Esta versión de OpenCV no incluye FaceDetectorYN (se requiere >= 4.8)")
        self._detector = cv2.FaceDetectorYN.create(str(det_path), "", (320, 320), score_threshold, 0.3, 50)
        self._recognizer = cv2.FaceRecognizerSF.create(str(rec_path), "")
        log.info("SFace cargado desde %s", model_dir)

    def detect(self, image_bgr: np.ndarray) -> list[DetectedFace]:
        h, w = image_bgr.shape[:2]
        self._detector.setInputSize((w, h))
        _, rows = self._detector.detect(image_bgr)
        if rows is None:
            return []
        faces = []
        for row in rows:
            x, y, bw, bh = (float(v) for v in row[:4])
            kps = normalize_kps(row[4:14].reshape(5, 2))
            faces.append(
                DetectedFace(
                    bbox=np.array([x, y, x + bw, y + bh], dtype=np.float32),
                    kps=kps,
                    det_score=float(row[14]),
                    raw=row.reshape(1, -1).astype(np.float32),
                )
            )
        faces.sort(key=lambda f: f.det_score, reverse=True)
        return faces

    def embed(self, image_bgr: np.ndarray, face: DetectedFace) -> np.ndarray:
        raw = face.raw
        if raw is None:
            # Rostro que no vino de YuNet: se reconstruye la fila con bbox + landmarks.
            x1, y1, x2, y2 = face.bbox
            raw = np.array(
                [[x1, y1, x2 - x1, y2 - y1, *np.asarray(face.kps).reshape(-1).tolist(), face.det_score]],
                dtype=np.float32,
            )
        aligned = self._recognizer.alignCrop(image_bgr, raw)
        feat = self._recognizer.feature(aligned)
        return l2_normalize(feat)
