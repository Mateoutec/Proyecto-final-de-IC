"""Tabla de decisión multimodal con huella simulada."""

import pytest

from app.domain import METHOD_CODE_FACE, METHOD_FACE, METHOD_FINGERPRINT, METHOD_FINGERPRINT_FACE
from app.fingerprint.base import FingerprintResult, FingerprintStatus, SimulatedProvider
from app.kiosk.decision import FingerprintLevel, RouteKind, classify, decide

HIGH, MEDIUM = 100.0, 40.0
sim = SimulatedProvider()


@pytest.mark.parametrize(
    "result, fallback, kind, method, person",
    [
        (sim.simulate(7, 3, "high"), "face", RouteKind.FINGERPRINT_ONLY, METHOD_FINGERPRINT, 7),
        (sim.simulate(7, 3, "medium"), "face", RouteKind.FACE_VERIFY, METHOD_FINGERPRINT_FACE, 7),
        (sim.simulate(None, None, "none"), "face", RouteKind.FACE_IDENTIFY, METHOD_FACE, None),
        (sim.simulate(None, None, "none"), "code_plus_face", RouteKind.CODE_PLUS_FACE, METHOD_CODE_FACE, None),
        (sim.simulate(None, None, "bad_image"), "face", RouteKind.FACE_IDENTIFY, METHOD_FACE, None),
        (sim.simulate(None, None, "bad_image"), "code_plus_face", RouteKind.CODE_PLUS_FACE, METHOD_CODE_FACE, None),
    ],
)
def test_decision_table(result, fallback, kind, method, person):
    route = decide(True, result, HIGH, MEDIUM, fallback)
    assert route.kind == kind
    assert route.method == method
    assert route.person_id == person


def test_no_fingerprint_configured_uses_face_identify():
    route = decide(False, None, HIGH, MEDIUM, "code_plus_face")
    assert route.kind == RouteKind.FACE_IDENTIFY and route.method == METHOD_FACE


def test_low_score_match_counts_as_no_match():
    low = FingerprintResult(FingerprintStatus.MATCH, slot=1, score=10.0, person_id=3)
    assert classify(low, HIGH, MEDIUM) == FingerprintLevel.NONE
    assert decide(True, low, HIGH, MEDIUM, "face").kind == RouteKind.FACE_IDENTIFY


def test_match_without_person_is_none():
    orphan = FingerprintResult(FingerprintStatus.MATCH, slot=99, score=250.0, person_id=None)
    assert classify(orphan, HIGH, MEDIUM) == FingerprintLevel.NONE


def test_score_boundaries():
    at_high = FingerprintResult(FingerprintStatus.MATCH, slot=1, score=HIGH, person_id=1)
    at_medium = FingerprintResult(FingerprintStatus.MATCH, slot=1, score=MEDIUM, person_id=1)
    assert classify(at_high, HIGH, MEDIUM) == FingerprintLevel.HIGH
    assert classify(at_medium, HIGH, MEDIUM) == FingerprintLevel.MEDIUM
