"""Control de calidad por frame y mensajes de guía."""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.face.base import DetectedFace, Pose, pose_from_kps

MESSAGES = {
    "ok": "Perfecto, no te muevas",
    "no_face": "Colócate frente a la cámara",
    "multiple_faces": "Debe quedar una sola persona frente a la cámara",
    "too_small": "Acércate un poco",
    "too_large": "Aléjate un poco",
    "off_center": "Centra tu rostro en el óvalo",
    "too_dark": "Falta luz: busca un lugar más iluminado",
    "too_bright": "Hay demasiada luz sobre tu rostro",
    "blurry": "Quédate quieto un momento",
    "not_frontal": "Mira al frente",
    "tilted": "Endereza la cabeza",
}


@dataclass
class QualityParams:
    min_face_ratio: float = 0.14
    max_face_ratio: float = 0.80
    min_face_px: int = 0
    min_sharpness: float = 25.0
    min_brightness: float = 60.0
    max_brightness: float = 215.0
    max_frontal_yaw: float = 0.15
    max_roll_degrees: float = 20.0
    check_center: bool = True


@dataclass
class QualityReport:
    ok: bool
    code: str
    face: DetectedFace | None = None
    pose: Pose | None = None
    score: float = 0.0
    metrics: dict = field(default_factory=dict)

    @property
    def message(self) -> str:
        return MESSAGES.get(self.code, MESSAGES["no_face"])


def pick_main_face(faces: list[DetectedFace]) -> tuple[DetectedFace | None, int]:
    """Devuelve el rostro principal y cuántas personas 'relevantes' hay.

    Rostros mucho más pequeños que el principal (gente al fondo) no cuentan.
    """
    if not faces:
        return None, 0
    ordered = sorted(faces, key=lambda f: f.area, reverse=True)
    main = ordered[0]
    relevant = [f for f in ordered if f.area >= 0.35 * main.area]
    return main, len(relevant)


def face_crop(image: np.ndarray, face: DetectedFace) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = face.bbox
    x1, y1 = int(max(0, x1)), int(max(0, y1))
    x2, y2 = int(min(w, x2)), int(min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return image[0:1, 0:1]
    return image[y1:y2, x1:x2]


def sharpness_of(crop_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def evaluate(
    image: np.ndarray,
    faces: list[DetectedFace],
    params: QualityParams,
    require_frontal: bool = True,
    max_yaw: float | None = None,
) -> QualityReport:
    main, count = pick_main_face(faces)
    if main is None:
        return QualityReport(False, "no_face")
    pose = pose_from_kps(main.kps)
    h, w = image.shape[:2]
    ratio = main.width / max(w, 1)
    crop = face_crop(image, main)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    sharp = sharpness_of(crop)
    metrics = {
        "face_ratio": round(ratio, 3),
        "face_px": round(main.width, 1),
        "brightness": round(brightness, 1),
        "sharpness": round(sharp, 1),
        "yaw": round(pose.yaw, 3),
        "pitch": round(pose.pitch, 3),
        "roll": round(pose.roll, 1),
    }

    def report(ok: bool, code: str) -> QualityReport:
        frontal = max(0.0, 1.0 - abs(pose.yaw) / 0.5)
        score = frontal * min(1.0, sharp / 200.0) * min(1.0, ratio / 0.3 if params.min_face_px == 0 else 1.0)
        return QualityReport(ok, code, main, pose, round(score, 4), metrics)

    if count > 1:
        return report(False, "multiple_faces")
    if params.min_face_px:
        if main.width < params.min_face_px:
            return report(False, "too_small")
    else:
        if ratio < params.min_face_ratio:
            return report(False, "too_small")
        if ratio > params.max_face_ratio:
            return report(False, "too_large")
    if params.check_center:
        cx = (main.bbox[0] + main.bbox[2]) / 2 / w
        cy = (main.bbox[1] + main.bbox[3]) / 2 / h
        if not (0.2 <= cx <= 0.8 and 0.15 <= cy <= 0.85):
            return report(False, "off_center")
    if brightness < params.min_brightness:
        return report(False, "too_dark")
    if brightness > params.max_brightness:
        return report(False, "too_bright")
    if sharp < params.min_sharpness:
        return report(False, "blurry")
    if abs(pose.roll) > params.max_roll_degrees:
        return report(False, "tilted")
    yaw_limit = params.max_frontal_yaw if require_frontal else (max_yaw if max_yaw is not None else 0.45)
    # El pitch varía según el motor (SCRFD da ~0.9 a rostros algo inclinados que YuNet ve en ~0.6),
    # así que solo se descartan casos extremos; el yaw es el criterio principal de "de frente".
    if abs(pose.yaw) > yaw_limit or (require_frontal and not (0.1 <= pose.pitch <= 1.0)):
        return report(False, "not_frontal")
    return report(True, "ok")
