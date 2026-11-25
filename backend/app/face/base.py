"""Interfaz común de los motores faciales y geometría de los 5 landmarks."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np


@dataclass
class DetectedFace:
    """Rostro detectado en coordenadas de la imagen recibida (sin espejar).

    `kps` tiene 5 puntos en este orden: ojo izquierdo de la imagen, ojo derecho de la
    imagen, nariz, comisura izquierda y comisura derecha (izquierda/derecha de la imagen).
    """

    bbox: np.ndarray  # x1, y1, x2, y2
    kps: np.ndarray  # (5, 2)
    det_score: float
    raw: Any = field(default=None, repr=False)

    @property
    def width(self) -> float:
        return float(self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return float(self.bbox[3] - self.bbox[1])

    @property
    def area(self) -> float:
        return max(self.width, 0.0) * max(self.height, 0.0)


class FaceEngine(ABC):
    name: str = "base"
    embedding_dim: int = 0
    description: str = ""

    @abstractmethod
    def detect(self, image_bgr: np.ndarray) -> list[DetectedFace]:
        """Detecta rostros con 5 landmarks."""

    @abstractmethod
    def embed(self, image_bgr: np.ndarray, face: DetectedFace) -> np.ndarray:
        """Embedding normalizado (L2) del rostro."""

    @staticmethod
    def similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Similitud coseno entre embeddings normalizados."""
        return float(np.dot(a, b))


def normalize_kps(points: np.ndarray) -> np.ndarray:
    """Ordena ojos y comisuras por x para que el orden no dependa del motor."""
    pts = np.asarray(points, dtype=np.float32).reshape(5, 2).copy()
    if pts[0, 0] > pts[1, 0]:
        pts[[0, 1]] = pts[[1, 0]]
    if pts[3, 0] > pts[4, 0]:
        pts[[3, 4]] = pts[[4, 3]]
    return pts


def l2_normalize(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


@dataclass
class Pose:
    yaw: float  # >0: la nariz va hacia la derecha de la imagen (la persona gira a SU izquierda)
    pitch: float  # ~0.5 de frente
    roll: float  # grados


def pose_from_kps(kps: np.ndarray) -> Pose:
    left_eye, right_eye, nose, mouth_l, mouth_r = kps
    eye_vec = right_eye - left_eye
    eye_dist = float(np.linalg.norm(eye_vec)) or 1.0
    unit = eye_vec / eye_dist
    eye_mid = (left_eye + right_eye) / 2
    yaw = float(np.dot(nose - eye_mid, unit) / eye_dist)
    mouth_mid = (mouth_l + mouth_r) / 2
    normal = np.array([-unit[1], unit[0]])
    vertical = float(np.dot(mouth_mid - eye_mid, normal)) or 1.0
    pitch = float(np.dot(nose - eye_mid, normal) / vertical)
    roll = math.degrees(math.atan2(float(eye_vec[1]), float(eye_vec[0])))
    return Pose(yaw=yaw, pitch=pitch, roll=roll)


# Plantilla ArcFace de 5 puntos para el recorte alineado de 112x112.
ARCFACE_DST = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)


def _umeyama(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Transformación de similitud (igual que skimage SimilarityTransform.estimate)."""
    num, dim = src.shape
    src_mean, dst_mean = src.mean(axis=0), dst.mean(axis=0)
    src_d, dst_d = src - src_mean, dst - dst_mean
    a = dst_d.T @ src_d / num
    d = np.ones((dim,), dtype=np.float64)
    if np.linalg.det(a) < 0:
        d[dim - 1] = -1
    t = np.eye(dim + 1, dtype=np.float64)
    u, s, v = np.linalg.svd(a)
    rank = np.linalg.matrix_rank(a)
    if rank == 0:
        return np.full_like(t, np.nan)
    if rank == dim - 1:
        if np.linalg.det(u) * np.linalg.det(v) > 0:
            t[:dim, :dim] = u @ v
        else:
            saved = d[dim - 1]
            d[dim - 1] = -1
            t[:dim, :dim] = u @ np.diag(d) @ v
            d[dim - 1] = saved
    else:
        t[:dim, :dim] = u @ np.diag(d) @ v
    scale = 1.0 / src_d.var(axis=0).sum() * (s @ d)
    t[:dim, dim] = dst_mean - scale * (t[:dim, :dim] @ src_mean.T)
    t[:dim, :dim] *= scale
    return t


def norm_crop(image_bgr: np.ndarray, kps: np.ndarray, size: int = 112) -> np.ndarray:
    matrix = _umeyama(np.asarray(kps, dtype=np.float64), ARCFACE_DST.astype(np.float64) * (size / 112.0))[:2]
    return cv2.warpAffine(image_bgr, matrix, (size, size), borderValue=0.0)


def decode_image(data: bytes) -> np.ndarray | None:
    if not data:
        return None
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def encode_jpeg(image_bgr: np.ndarray, quality: int = 88) -> bytes:
    ok, buf = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("No se pudo codificar la imagen")
    return buf.tobytes()


def resize_max_width(image_bgr: np.ndarray, max_width: int = 640) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    if w <= max_width:
        return image_bgr
    scale = max_width / w
    return cv2.resize(image_bgr, (max_width, int(round(h * scale))), interpolation=cv2.INTER_AREA)
