from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.context import AppContext  # noqa: E402
from app.face.base import encode_jpeg  # noqa: E402
from app.face.fake_engine import make_fake_face  # noqa: E402
from app.main import create_app  # noqa: E402

ADMIN_PASSWORD = "clave-de-prueba"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        data_dir=str(tmp_path / "data"),
        models_dir=str(tmp_path / "models"),
        admin_password=ADMIN_PASSWORD,
        session_secret="secreto-de-prueba",
        encryption_key=Fernet.generate_key().decode(),
        timezone="America/Lima",
        face_engine="fake",
        fingerprint_provider="simulated",
        debounce_seconds=120,
        liveness_enabled=True,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def ctx(settings):
    context = AppContext(settings)
    yield context
    context.close()


@pytest.fixture
def client(ctx):
    app = create_app(ctx.settings)
    app.state.ctx = ctx
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/api/admin/login", json={"password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return client


def jpeg(identity: int, **kw) -> bytes:
    return encode_jpeg(make_fake_face(identity, **kw))


class FakeClock:
    def __init__(self, start: datetime | None = None):
        self.now = start or datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def create_person(admin_client, code: str, consent: bool = True, area_id=None) -> dict:
    r = admin_client.post(
        "/api/admin/people",
        json={"code": code, "first_name": f"Nombre{code}", "last_name": "Prueba", "consent_signed": consent, "area_id": area_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def enroll(admin_client, person_id: int, identity: int, n: int = 3) -> None:
    poses = ["frontal", "left", "right", "glasses", "frontal_2"]
    for i in range(n):
        r = admin_client.post(
            f"/api/admin/people/{person_id}/templates",
            files={"file": ("f.jpg", jpeg(identity), "image/jpeg")},
            data={"pose": poses[i], "source": "camera"},
        )
        assert r.status_code == 201, r.text


@pytest.fixture
def rng():
    return random.Random(7)
