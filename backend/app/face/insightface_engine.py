"""Motor `insightface`: pack buffalo_l (SCRFD det_10g + ArcFace w600k_r50) sobre onnxruntime.

Carga solo los modelos de detección y reconocimiento del pack. El pre y post-procesado
replica el de la librería InsightFace (decodificación SCRFD por strides 8/16/32 y
alineación `norm_crop` a 112x112), así no hace falta compilar el paquete `insightface`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from app.face.base import DetectedFace, FaceEngine, l2_normalize, norm_crop, normalize_kps

log = logging.getLogger("app.face.insightface")

DET_FILE = "det_10g.onnx"
REC_FILE = "w600k_r50.onnx"


def _distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance2kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    preds = []
    for i in range(0, distance.shape[1], 2):
        preds.append(points[:, i % 2] + distance[:, i])
        preds.append(points[:, i % 2 + 1] + distance[:, i + 1])
    return np.stack(preds, axis=-1)


def _nms(dets: np.ndarray, thresh: float) -> list[int]:
    x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(ovr <= thresh)[0] + 1]
    return keep


class InsightFaceEngine(FaceEngine):
    name = "insightface"
    embedding_dim = 512
    description = "InsightFace buffalo_l (SCRFD + ArcFace R50, 512-d)"

    def __init__(self, model_dir: Path, det_size: int = 640, det_thresh: float = 0.5):
        import onnxruntime as ort

        det_path = model_dir / DET_FILE
        rec_path = model_dir / REC_FILE
        for path in (det_path, rec_path):
            if not path.exists():
                raise FileNotFoundError(f"Falta el modelo {path}. Ejecuta: uv run python -m app.cli download-models")
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        providers = ["CPUExecutionProvider"]
        self._det = ort.InferenceSession(str(det_path), sess_options=opts, providers=providers)
        self._rec = ort.InferenceSession(str(rec_path), sess_options=opts, providers=providers)
        self._det_input = self._det.get_inputs()[0].name
        self._det_outputs = [o.name for o in self._det.get_outputs()]
        self._rec_input = self._rec.get_inputs()[0].name
        n_out = len(self._det_outputs)
        if n_out not in (6, 9):
            raise RuntimeError(f"Modelo SCRFD inesperado ({n_out} salidas)")
        self._use_kps = n_out == 9
        if not self._use_kps:
            raise RuntimeError("El modelo de detección no entrega landmarks")
        self._fmc = 3
        self._strides = (8, 16, 32)
        self._num_anchors = 2
        self._det_size = det_size
        self._det_thresh = det_thresh
        self._nms_thresh = 0.4
        self._centers: dict[tuple[int, int, int], np.ndarray] = {}
        log.info("InsightFace buffalo_l cargado desde %s (solo detección + reconocimiento)", model_dir)

    def _forward(self, det_img: np.ndarray):
        blob = cv2.dnn.blobFromImage(
            det_img, 1.0 / 128.0, (det_img.shape[1], det_img.shape[0]), (127.5, 127.5, 127.5), swapRB=True
        )
        outs = self._det.run(self._det_outputs, {self._det_input: blob})
        height, width = blob.shape[2], blob.shape[3]
        scores_list, bboxes_list, kpss_list = [], [], []
        for idx, stride in enumerate(self._strides):
            scores = outs[idx]
            bbox_preds = outs[idx + self._fmc]
            kps_preds = outs[idx + self._fmc * 2]
            if scores.ndim == 3:
                scores, bbox_preds, kps_preds = scores[0], bbox_preds[0], kps_preds[0]
            bbox_preds = bbox_preds * stride
            kps_preds = kps_preds * stride
            fh, fw = height // stride, width // stride
            key = (fh, fw, stride)
            centers = self._centers.get(key)
            if centers is None:
                centers = np.stack(np.mgrid[:fh, :fw][::-1], axis=-1).astype(np.float32)
                centers = (centers * stride).reshape((-1, 2))
                centers = np.stack([centers] * self._num_anchors, axis=1).reshape((-1, 2))
                self._centers[key] = centers
            pos = np.where(scores.reshape(-1) >= self._det_thresh)[0]
            bboxes = _distance2bbox(centers, bbox_preds)
            kpss = _distance2kps(centers, kps_preds).reshape((-1, 5, 2))
            scores_list.append(scores.reshape(-1)[pos])
            bboxes_list.append(bboxes[pos])
            kpss_list.append(kpss[pos])
        return scores_list, bboxes_list, kpss_list

    def detect(self, image_bgr: np.ndarray) -> list[DetectedFace]:
        size = self._det_size
        im_ratio = image_bgr.shape[0] / image_bgr.shape[1]
        if im_ratio > 1.0:
            new_h, new_w = size, int(size / im_ratio)
        else:
            new_w, new_h = size, int(size * im_ratio)
        scale = new_h / image_bgr.shape[0]
        det_img = np.zeros((size, size, 3), dtype=np.uint8)
        det_img[:new_h, :new_w, :] = cv2.resize(image_bgr, (new_w, new_h))
        scores_list, bboxes_list, kpss_list = self._forward(det_img)
        scores = np.concatenate(scores_list)
        if scores.size == 0:
            return []
        bboxes = np.vstack(bboxes_list) / scale
        kpss = np.vstack(kpss_list) / scale
        order = scores.argsort()[::-1]
        pre = np.hstack((bboxes, scores[:, None])).astype(np.float32)[order]
        kpss = kpss[order]
        keep = _nms(pre, self._nms_thresh)
        faces = []
        for i in keep:
            faces.append(DetectedFace(bbox=pre[i, :4].copy(), kps=normalize_kps(kpss[i]), det_score=float(pre[i, 4])))
        return faces

    def embed(self, image_bgr: np.ndarray, face: DetectedFace) -> np.ndarray:
        aligned = norm_crop(image_bgr, face.kps, 112)
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        out = self._rec.run(None, {self._rec_input: blob})[0]
        return l2_normalize(out)
