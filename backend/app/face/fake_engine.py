"""Motor `fake` para tests: determinista y sin modelos.

Las imágenes de prueba se generan con `make_fake_face`. En la franja superior se
codifican (en bloques grandes que resisten JPEG) la cantidad de rostros, el giro y el
tamaño; la identidad es una textura de ruido sembrada que se convierte en embedding.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.face.base import DetectedFace, FaceEngine, l2_normalize

_MAGIC = 200
_BLOCK = 32


def make_fake_face(
    identity: int,
    yaw: float = 0.0,
    faces: int = 1,
    face_size: int = 220,
    brightness: int = 128,
    blur: bool = False,
    width: int = 640,
    height: int = 480,
) -> np.ndarray:
    img = np.full((height, width, 3), 90, dtype=np.uint8)
    img[:_BLOCK, :_BLOCK] = _MAGIC
    img[:_BLOCK, _BLOCK : 2 * _BLOCK] = min(faces, 5) * 40
    img[:_BLOCK, 2 * _BLOCK : 3 * _BLOCK] = int(np.clip(128 + yaw * 250, 0, 255))
    img[:_BLOCK, 3 * _BLOCK : 4 * _BLOCK] = int(np.clip(face_size // 4, 0, 255))
    rng = np.random.default_rng(identity + 1)
    coarse = rng.integers(0, 256, size=(16, 16), dtype=np.uint8).astype(np.float32)
    texture = cv2.resize(coarse, (face_size, face_size), interpolation=cv2.INTER_NEAREST)
    texture = (texture - texture.mean()) * 0.45 + brightness
    texture = np.clip(texture, 0, 255).astype(np.uint8)
    if blur:
        texture = cv2.GaussianBlur(texture, (0, 0), 9)
    x1 = (width - face_size) // 2
    y1 = (height - face_size) // 2 + 10
    img[y1 : y1 + face_size, x1 : x1 + face_size] = texture[..., None]
    return img


def _block_value(img: np.ndarray, index: int) -> float:
    block = img[4 : _BLOCK - 4, index * _BLOCK + 4 : (index + 1) * _BLOCK - 4]
    return float(block.mean())


class FakeEngine(FaceEngine):
    name = "fake"
    embedding_dim = 256
    description = "Motor falso para pruebas"

    def detect(self, image_bgr: np.ndarray) -> list[DetectedFace]:
        if image_bgr.shape[0] < _BLOCK or image_bgr.shape[1] < 4 * _BLOCK:
            return []
        if abs(_block_value(image_bgr, 0) - _MAGIC) > 20:
            return []
        count = int(round(_block_value(image_bgr, 1) / 40))
        yaw = (_block_value(image_bgr, 2) - 128) / 250
        size = int(round(_block_value(image_bgr, 3))) * 4
        h, w = image_bgr.shape[:2]
        x1 = (w - size) / 2
        y1 = (h - size) / 2 + 10
        faces = []
        for i in range(count):
            dx = i * (size + 10) * (1 if i % 2 else -1) if i else 0
            bx1 = x1 + dx
            box = np.array([bx1, y1, bx1 + size, y1 + size], dtype=np.float32)
            eye_y = y1 + 0.40 * size
            left_eye = (bx1 + 0.32 * size, eye_y)
            right_eye = (bx1 + 0.68 * size, eye_y)
            eye_dist = right_eye[0] - left_eye[0]
            nose = (bx1 + 0.5 * size + yaw * eye_dist, y1 + 0.58 * size)
            kps = np.array(
                [left_eye, right_eye, nose, (bx1 + 0.36 * size, y1 + 0.76 * size), (bx1 + 0.64 * size, y1 + 0.76 * size)],
                dtype=np.float32,
            )
            faces.append(DetectedFace(bbox=box, kps=kps, det_score=0.99))
        return faces

    def embed(self, image_bgr: np.ndarray, face: DetectedFace) -> np.ndarray:
        x1, y1, x2, y2 = (int(round(v)) for v in face.bbox)
        crop = image_bgr[max(y1, 0) : y2, max(x1, 0) : x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
        small = cv2.resize(gray, (16, 16), interpolation=cv2.INTER_AREA).reshape(-1)
        return l2_normalize(small - small.mean())
