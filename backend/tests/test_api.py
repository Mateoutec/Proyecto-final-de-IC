"""Endpoints principales y exportaciones CSV/XLSX/ZIP."""

import csv
import io
import zipfile
from datetime import datetime, timedelta

from openpyxl import load_workbook

from tests.conftest import create_person, enroll, jpeg


def test_health_reports_engine(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["face_engine"] == "fake"
    assert body["fingerprint"]["provider"] == "simulated"


def test_admin_requires_login(client):
    r = client.get("/api/admin/people")
    assert r.status_code == 401
    assert r.json()["detail"] == "Debes iniciar sesión en el panel"


def test_bad_password(client):
    r = client.post("/api/admin/login", json={"password": "nope"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Contraseña incorrecta"


def test_login_sets_httponly_cookie(client):
    r = client.post("/api/admin/login", json={"password": "clave-de-prueba"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_people_crud_and_search(admin):
    area = admin.post("/api/admin/areas", json={"name": "Laboratorio"}).json()
    person = create_person(admin, "U2026001", area_id=area["id"])
    assert person["area"] == "Laboratorio"
    dup = admin.post("/api/admin/people", json={"code": "u2026001", "first_name": "X", "last_name": "Y"})
    assert dup.status_code == 409
    found = admin.get("/api/admin/people", params={"search": "2026001"}).json()
    assert len(found) == 1
    upd = admin.put(
        f"/api/admin/people/{person['id']}",
        json={"code": "U2026001", "first_name": "Ana", "last_name": "Pérez", "active": False, "consent_signed": True},
    )
    assert upd.status_code == 200 and upd.json()["active"] is False
    assert admin.get("/api/admin/people", params={"status": "active"}).json() == []
    assert admin.delete(f"/api/admin/people/{person['id']}").status_code == 200


def test_validation_message_in_spanish(admin):
    r = admin.post("/api/admin/people", json={"code": "", "first_name": "A"})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Datos inválidos")


def test_enrollment_requires_consent(admin):
    person = create_person(admin, "NC1", consent=False)
    r = admin.post(
        f"/api/admin/people/{person['id']}/templates",
        files={"file": ("f.jpg", jpeg(1), "image/jpeg")},
        data={"pose": "frontal"},
    )
    assert r.status_code == 409 and r.json()["code"] == "no_consent"


def test_enrollment_quality_rejection(admin):
    person = create_person(admin, "Q1")
    r = admin.post(
        f"/api/admin/people/{person['id']}/templates",
        files={"file": ("f.jpg", jpeg(1, brightness=20), "image/jpeg")},
        data={"pose": "frontal"},
    )
    assert r.status_code == 422 and r.json()["quality"] == "too_dark"


def test_enrollment_duplicate_warning(admin):
    a = create_person(admin, "D1")
    b = create_person(admin, "D2")
    enroll(admin, a["id"], identity=3, n=1)
    r = admin.post(
        f"/api/admin/people/{b['id']}/templates",
        files={"file": ("f.jpg", jpeg(3), "image/jpeg")},
        data={"pose": "frontal"},
    )
    assert r.status_code == 409 and r.json()["code"] == "duplicate"
    assert r.json()["duplicate"]["code"] == "D1"
    forced = admin.post(
        f"/api/admin/people/{b['id']}/templates",
        files={"file": ("f.jpg", jpeg(3), "image/jpeg")},
        data={"pose": "frontal", "confirm_duplicate": "true"},
    )
    assert forced.status_code == 201


def test_delete_biometrics_removes_templates_and_photos(admin, ctx):
    person = create_person(admin, "B1")
    enroll(admin, person["id"], identity=4, n=2)
    detail = admin.get(f"/api/admin/people/{person['id']}").json()
    assert len(detail["face_templates"]) == 2
    photo = ctx.data_path / detail["face_templates"][0]["photo_path"]
    assert photo.exists()
    r = admin.delete(f"/api/admin/people/{person['id']}/biometrics")
    assert r.json()["templates_deleted"] == 2
    assert not photo.exists()
    assert admin.get(f"/api/admin/people/{person['id']}").json()["face_templates"] == []


def _kiosk_mark(client, identity):
    sid = client.post("/api/kiosk/sessions").json()["id"]
    view = None
    for _ in range(12):
        view = client.post(f"/api/kiosk/sessions/{sid}/frames", content=jpeg(identity), headers={"Content-Type": "image/jpeg"}).json()
        if view["terminal"]:
            break
    return view


def test_kiosk_flow_and_exports(admin, ctx):
    ctx.update_runtime({"liveness_enabled": False, "debounce_seconds": 0}, "test")
    area = admin.post("/api/admin/areas", json={"name": "Ciencia de Datos"}).json()
    person = create_person(admin, "K1", area_id=area["id"])
    enroll(admin, person["id"], identity=5)
    status = admin.get("/api/kiosk/status").json()
    assert status["enrolled_people"] == 1 and status["fingerprint"]["simulated"] is True

    # Entrada manual hace 8 h (salida olvidada / prueba) y salida por rostro ahora.
    local_entry = (datetime.now(ctx.tz) - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M")
    r = admin.post(
        "/api/admin/events/manual",
        json={"person_id": person["id"], "event_type": "ENTRADA", "local_datetime": local_entry, "reason": "Prueba"},
    )
    assert r.status_code == 201, r.text
    view = _kiosk_mark(admin, 5)
    assert view["state"] == "success" and view["result"]["event_type"] == "SALIDA"
    assert 7.9 <= view["result"]["worked_hours"] <= 8.1

    shifts = admin.get("/api/admin/shifts", params={"date_from": (datetime.now(ctx.tz) - timedelta(days=1)).date().isoformat()}).json()
    assert shifts["items"][0]["status"] == "COMPLETA"

    d_from = (datetime.now(ctx.tz) - timedelta(days=2)).date().isoformat()
    r = admin.get("/api/admin/export", params={"kind": "shifts", "format": "csv", "date_from": d_from})
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf"), "CSV debe llevar BOM UTF-8"
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0] == "Fecha" and rows[0][6] == "Horas (decimal)"
    assert rows[1][1] == "K1" and rows[1][3] == "Ciencia de Datos"
    assert 7.9 <= float(rows[1][6]) <= 8.1 and rows[1][8] == "COMPLETA"
    assert rows[1][9] == "MANUAL" and rows[1][10] == "ROSTRO"

    r = admin.get("/api/admin/export", params={"kind": "shifts", "format": "xlsx", "date_from": d_from})
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws["B2"].value == "K1" and 7.9 <= ws["G2"].value <= 8.1

    r = admin.get("/api/admin/export", params={"kind": "events", "format": "zip", "date_from": d_from})
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    event_rows = list(csv.reader(io.StringIO(zf.read("marcaciones.csv").decode("utf-8-sig"))))
    photo_paths = [row[13] for row in event_rows[1:] if row[13]]
    assert photo_paths and all(p in names for p in photo_paths)

    r = admin.get("/api/admin/export", params={"kind": "summary", "format": "csv", "date_from": d_from})
    summary = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert summary[1][0] == "K1" and summary[1][3] == "1"

    audit = admin.get("/api/admin/audit", params={"action": "exportacion"}).json()
    assert audit["total"] == 4


def test_csv_delimiter_configurable(admin, ctx):
    ctx.update_runtime({"csv_delimiter": ";"}, "test")
    r = admin.get("/api/admin/export", params={"kind": "summary", "format": "csv"})
    assert r.content.decode("utf-8-sig").splitlines()[0].count(";") >= 5


def test_void_and_manual_require_reason(admin, ctx):
    person = create_person(admin, "V1")
    local = datetime.now(ctx.tz).strftime("%Y-%m-%dT%H:%M")
    r = admin.post("/api/admin/events/manual", json={"person_id": person["id"], "event_type": "ENTRADA", "local_datetime": local, "reason": ""})
    assert r.status_code == 422
    ev = admin.post(
        "/api/admin/events/manual",
        json={"person_id": person["id"], "event_type": "ENTRADA", "local_datetime": local, "reason": "Olvidó marcar"},
    ).json()
    assert admin.post(f"/api/admin/events/{ev['id']}/void", json={"reason": ""}).status_code == 422
    voided = admin.post(f"/api/admin/events/{ev['id']}/void", json={"reason": "Error de registro"}).json()
    assert voided["voided"] is True
    actions = [a["action"] for a in admin.get("/api/admin/audit").json()["items"]]
    assert "marcacion_anulada" in actions and "marcacion_manual" in actions


def test_files_require_auth(admin, client, ctx):
    person = create_person(admin, "F1")
    enroll(admin, person["id"], identity=6, n=1)
    url = admin.get(f"/api/admin/people/{person['id']}").json()["face_templates"][0]["photo_url"]
    assert admin.get(url).status_code == 200
    admin.post("/api/admin/logout")
    admin.cookies.clear()
    assert admin.get(url).status_code == 401
    assert admin.get("/api/admin/files/../.env").status_code in (401, 404)


def test_settings_update_and_audit(admin):
    r = admin.put("/api/admin/settings", json={"changes": {"debounce_seconds": 60, "threshold_insightface": 0.5}})
    assert r.status_code == 200
    assert r.json()["values"]["debounce_seconds"] == 60
    bad = admin.put("/api/admin/settings", json={"changes": {"debounce_seconds": -5}})
    assert bad.status_code == 400
    audit = admin.get("/api/admin/audit", params={"action": "configuracion"}).json()
    assert audit["total"] == 1


def test_simulated_fingerprint_endpoint(admin, ctx):
    person = create_person(admin, "H1")
    enroll(admin, person["id"], identity=7, n=2)
    assert admin.post(f"/api/admin/people/{person['id']}/fingerprint", json={}).json()["slot"] == 1
    sid = admin.post("/api/kiosk/sessions").json()["id"]
    admin.post(f"/api/kiosk/sessions/{sid}/frames", content=jpeg(7), headers={"Content-Type": "image/jpeg"})
    view = admin.post(f"/api/kiosk/sessions/{sid}/fingerprint/simulate", json={"person_id": person["id"], "level": "high"}).json()
    assert view["state"] == "success" and view["result"]["method"] == "HUELLA"


def test_calibration_and_reindex(admin, ctx):
    for i, code in enumerate(["C1", "C2", "C3"]):
        p = create_person(admin, code)
        enroll(admin, p["id"], identity=10 + i, n=2)
    result = admin.post("/api/admin/calibration").json()
    assert result["genuine_pairs"] == 3 and result["impostor_pairs"] == 12
    assert (ctx.data_path / result["files"]["chart"]).exists()
    assert admin.get(result["urls"]["csv"]).status_code == 200
    reindexed = admin.post("/api/admin/reindex", json={}).json()
    assert reindexed["created"] == 6 and reindexed["skipped"] == 0
    assert ctx.engines.index.person_count == 3


def test_summary_today(admin, ctx):
    ctx.update_runtime({"liveness_enabled": False}, "test")
    person = create_person(admin, "S1")
    enroll(admin, person["id"], identity=8)
    assert _kiosk_mark(admin, 8)["state"] == "success"
    summary = admin.get("/api/admin/summary").json()
    assert summary["counts"]["present"] == 1 and summary["counts"]["entries"] == 1
    assert summary["recent"][0]["photo_url"].startswith("/api/admin/files/captures/")


def test_spa_fallback_and_api_404(client):
    assert client.get("/api/no-existe").status_code == 404
    r = client.get("/admin/personas")
    assert r.status_code in (200, 503)
