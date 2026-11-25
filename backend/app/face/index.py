"""Índice en memoria de plantillas (matriz numpy) para identificación 1:N y verificación 1:1."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np


@dataclass
class IdentifyResult:
    person_id: int | None
    score: float
    second_score: float
    margin: float
    accepted: bool
    reason: str  # ok | below_threshold | low_margin | empty


class TemplateIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.engine_name: str | None = None
        self._matrix = np.zeros((0, 1), dtype=np.float32)
        self._person_ids = np.zeros((0,), dtype=np.int64)
        self._groups: dict[int, np.ndarray] = {}

    def load(self, engine_name: str, rows: list[tuple[int, np.ndarray]]) -> None:
        if rows:
            matrix = np.vstack([np.asarray(emb, dtype=np.float32).reshape(1, -1) for _, emb in rows])
            person_ids = np.array([pid for pid, _ in rows], dtype=np.int64)
        else:
            matrix = np.zeros((0, 1), dtype=np.float32)
            person_ids = np.zeros((0,), dtype=np.int64)
        groups = {int(pid): np.where(person_ids == pid)[0] for pid in np.unique(person_ids)}
        with self._lock:
            self.engine_name = engine_name
            self._matrix = matrix
            self._person_ids = person_ids
            self._groups = groups

    @property
    def person_count(self) -> int:
        return len(self._groups)

    @property
    def template_count(self) -> int:
        return int(self._matrix.shape[0])

    def has_person(self, person_id: int) -> bool:
        return person_id in self._groups

    def _per_person(self, emb: np.ndarray) -> dict[int, float]:
        with self._lock:
            matrix, groups = self._matrix, self._groups
        if matrix.shape[0] == 0 or matrix.shape[1] != emb.shape[0]:
            return {}
        sims = matrix @ emb.astype(np.float32)
        return {pid: float(sims[idx].max()) for pid, idx in groups.items()}

    def identify(self, emb: np.ndarray, threshold: float, margin: float, exclude: int | None = None) -> IdentifyResult:
        scores = self._per_person(emb)
        if exclude is not None:
            scores.pop(exclude, None)
        if not scores:
            return IdentifyResult(None, 0.0, 0.0, 0.0, False, "empty")
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best_id, best = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else -1.0
        gap = best - second if len(ranked) > 1 else 1.0
        if best < threshold:
            return IdentifyResult(None, best, second, gap, False, "below_threshold")
        if gap < margin:
            return IdentifyResult(None, best, second, gap, False, "low_margin")
        return IdentifyResult(best_id, best, second, gap, True, "ok")

    def verify(self, emb: np.ndarray, person_id: int, threshold: float) -> tuple[bool, float]:
        with self._lock:
            matrix, groups = self._matrix, self._groups
        idx = groups.get(person_id)
        if idx is None or matrix.shape[1] != emb.shape[0]:
            return False, 0.0
        score = float((matrix[idx] @ emb.astype(np.float32)).max())
        return score >= threshold, score
