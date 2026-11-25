"""Integración con los motores reales usando los rostros de la imagen 't1' de InsightFace.

Se salta sola si los modelos no están descargados o el motor no carga.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from app.config import PROJECT_ROOT
from app.face.base import encode_jpeg
from app.face.index import TemplateIndex
from app.face.manager import build_engine
from app.face.samples import face_frames, load_sample_image
from app.kiosk.session import KioskSession
from app.models import Person
from app.services.enrollment import enroll_photo
from tests.conftest import FakeClock, make_settings

pytestmark = pytest.mark.integration

DEFAULT_THRESHOLDS = {"insightface": 0.45, "sface": 0.363}


@pytest.fixture(scope="module")
def sample():
    image = load_sample_image()
    if image is None:
        pytest.skip("No está la imagen de ejemplo t1 (ejecuta scripts/setup.sh)")
    return image


@pytest.fixture(scope="module", params=["insightface", "sface"])
def engine(request):
    try:
        return build_engine(request.param, PROJECT_ROOT / "models")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Motor {request.param} no disponible: {exc}")


def test_detects_all_faces_with_landmarks(engine, sample):
    faces = engine.detect(sample)
    assert len(faces) == 6
    for f in faces:
        assert f.kps.shape == (5, 2)
        assert f.kps[0, 0] < f.kps[1, 0]  # ojos ordenados por x


def test_identification_1_to_n(engine, sample):
    enroll_sets = [face_frames(sample, engine, scale_jitter=s, angle_jitter=a) for s, a in ((1.0, 0), (0.9, 3), (1.1, -3))]
    probe = face_frames(sample, engine, scale_jitter=1.05, angle_jitter=2, brightness=-12)
    index = TemplateIndex()
    rows = []
    for frames in enroll_sets:
        for person_id, frame in enumerate(frames):
            face = max(engine.detect(frame), key=lambda f: f.area)
            rows.append((person_id, engine.embed(frame, face)))
    index.load(engine.name, rows)
    threshold = DEFAULT_THRESHOLDS[engine.name]
    for person_id, frame in enumerate(probe):
        face = max(engine.detect(frame), key=lambda f: f.area)
        result = index.identify(engine.embed(frame, face), threshold, 0.06)
        assert result.accepted, (engine.name, person_id, result)
        assert result.person_id == person_id


def test_impostor_scores_below_threshold(engine, sample):
    frames = face_frames(sample, engine, max_abs_yaw=None)
    embs = []
    for frame in frames:
        face = max(engine.detect(frame), key=lambda f: f.area)
        embs.append(engine.embed(frame, face))
    sims = np.array(embs) @ np.array(embs).T
    np.fill_diagonal(sims, -1)
    assert sims.max() < DEFAULT_THRESHOLDS[engine.name]


def test_kiosk_session_with_real_engine(engine, sample, tmp_path):
    from app.context import AppContext

    settings = make_settings(
        tmp_path,
        face_engine=engine.name,
        models_dir=str(PROJECT_ROOT / "models"),
        liveness_enabled=False,
        max_frontal_yaw=0.6,
    )
    ctx = AppContext(settings)
    try:
        assert ctx.engines.active_name == engine.name
        frames = face_frames(sample, ctx.engines.engine)
        with ctx.session() as db:
            for i in range(len(frames)):
                person = Person(code=f"T{i}", first_name=f"Rostro{i}", last_name="Ejemplo", consent_signed=True)
                db.add(person)
                db.commit()
                for s in (1.0, 0.92, 1.08):
                    variant = face_frames(sample, ctx.engines.engine, scale_jitter=s)[i]
                    enroll_photo(ctx, db, person, encode_jpeg(variant), "upload", "upload", False, "test")
        probe = face_frames(sample, ctx.engines.engine, scale_jitter=1.04, brightness=-10)
        for i, frame in enumerate(probe):
            session = KioskSession(ctx, clock=FakeClock(), rng=random.Random(i))
            view = None
            for _ in range(8):
                view = session.handle_frame(encode_jpeg(frame))
                if view["terminal"]:
                    break
            assert view["state"] == "success", (engine.name, i, view["hint"])
            assert view["result"]["person"]["code"] == f"T{i}"
    finally:
        ctx.close()
