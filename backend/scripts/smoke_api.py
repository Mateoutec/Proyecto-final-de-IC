"""Prueba de humo por API con ambos motores reales (insightface y sface).

Levanta un servidor aislado (datos en una carpeta temporal, puerto 8765), crea un área y
personas, las enrola con rostros de la imagen de ejemplo 't1', reconoce a cada una, registra
entradas y salidas (incluye huella simulada alta y media) y exporta CSV/XLSX verificando horas.

Uso (desde backend/):  uv run python scripts/smoke_api.py
"""

from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet
from openpyxl import load_workbook

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.face.base import encode_jpeg  # noqa: E402
from app.face.manager import build_engine  # noqa: E402
from app.face.samples import face_frames, load_sample_image  # noqa: E402

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
PASSWORD = "humo-2026"
TZ = ZoneInfo("America/Lima")
results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}{(': ' + detail) if detail else ''}")
    if not cond:
        raise SystemExit(f"Falló: {name} {detail}")


def mark(client: httpx.Client, frame: bytes, max_frames: int = 12) -> dict:
    sid = client.post("/api/kiosk/sessions").json()["id"]
    view = {}
    for _ in range(max_frames):
        view = client.post(f"/api/kiosk/sessions/{sid}/frames", content=frame, headers={"Content-Type": "image/jpeg"}).json()
        if view["terminal"]:
            break
    return view


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    image = load_sample_image()
    if image is None:
        print("✗ Falta la imagen de ejemplo t1 (ejecuta scripts/setup.sh)")
        return 1
    reference = build_engine("insightface", BACKEND.parent / "models")
    enroll_sets = [face_frames(image, reference, scale_jitter=s, angle_jitter=a) for s, a in ((1.0, 0), (0.92, 3), (1.08, -3))]
    probes = face_frames(image, reference, scale_jitter=1.04, angle_jitter=1.5, brightness=-10)
    n = len(probes)
    print(f"Rostros de ejemplo utilizables: {n}")

    tmp = tempfile.mkdtemp(prefix="asistencia_humo_")
    env = {
        **os.environ,
        "DATA_DIR": tmp,
        "ADMIN_PASSWORD": PASSWORD,
        "SESSION_SECRET": "humo",
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "FACE_ENGINE": "insightface",
        "FINGERPRINT_PROVIDER": "simulated",
        "TIMEZONE": "America/Lima",
        "PORT": str(PORT),
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "app", "--port", str(PORT)],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        client = httpx.Client(base_url=BASE, timeout=60)
        for _ in range(120):
            try:
                if client.get("/api/health").status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.5)
        else:
            print("✗ El servidor no arrancó")
            return 1
        health = client.get("/api/health").json()
        print(f"Servidor de prueba en {BASE}, datos en {tmp}")
        check("/api/health responde e informa el motor", health["face_engine"] == "insightface", health["face_engine"])
        check("login del panel", client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200)
        r = client.put(
            "/api/admin/settings",
            json={"changes": {"liveness_enabled": False, "debounce_seconds": 0, "max_frontal_yaw": 0.45}},
        )
        check("configuración de prueba aplicada", r.status_code == 200)

        area = client.post("/api/admin/areas", json={"name": "Laboratorio de Cognitive Computing"}).json()
        people = []
        for i in range(n):
            p = client.post(
                "/api/admin/people",
                json={
                    "code": f"SMK{i + 1:03d}",
                    "first_name": f"Rostro{i + 1}",
                    "last_name": "Ejemplo",
                    "area_id": area["id"],
                    "consent_signed": True,
                },
            ).json()
            people.append(p)
            for frames, pose in zip(enroll_sets, ("frontal", "glasses", "frontal_2"), strict=True):
                r = client.post(
                    f"/api/admin/people/{p['id']}/templates",
                    files={"file": ("c.jpg", encode_jpeg(frames[i]), "image/jpeg")},
                    data={"pose": pose, "source": "camera"},
                )
                if r.status_code != 201:
                    check(f"enrolar {p['code']} ({pose})", False, r.text)
        check(f"área y {n} personas creadas y enroladas (3 capturas c/u)", True)

        entry_local = datetime.now(TZ) - timedelta(hours=8, minutes=15)
        r = client.post(
            "/api/admin/events/manual",
            json={
                "person_id": people[0]["id"],
                "event_type": "ENTRADA",
                "local_datetime": entry_local.strftime("%Y-%m-%dT%H:%M"),
                "reason": "Prueba de humo: entrada temprana",
            },
        )
        check("marcación manual de entrada (hace 8 h 15 min)", r.status_code == 201)

        print("\n[insightface] reconocimiento 1:N")
        for i, p in enumerate(people):
            view = mark(client, encode_jpeg(probes[i]))
            ok = view["state"] == "success" and view["result"]["person"]["code"] == p["code"]
            detail = f"{view['state']} {view.get('result', {}) and view['result'].get('event_type')} sim={view.get('result', {}) and view['result'].get('face_score')}"
            check(f"reconoce a {p['code']}", ok, detail)
            if i == 0:
                worked = view["result"]["worked_hours"]
                check("SALIDA de SMK001 con ~8.25 h trabajadas", view["result"]["event_type"] == "SALIDA" and abs(worked - 8.25) <= 0.03, f"{worked} h")

        print("\n[huella simulada]")
        fp = client.post(f"/api/admin/people/{people[1]['id']}/fingerprint", json={})
        check("huella simulada asignada a SMK002", fp.status_code == 200, f"posición {fp.json().get('slot')}")
        sid = client.post("/api/kiosk/sessions").json()["id"]
        client.post(f"/api/kiosk/sessions/{sid}/frames", content=encode_jpeg(probes[1]), headers={"Content-Type": "image/jpeg"})
        view = client.post(f"/api/kiosk/sessions/{sid}/fingerprint/simulate", json={"person_id": people[1]["id"], "level": "high"}).json()
        check("huella alta → marca por HUELLA", view["state"] == "success" and view["result"]["method"] == "HUELLA", view["result"]["event_type"])
        sid = client.post("/api/kiosk/sessions").json()["id"]
        view = client.post(f"/api/kiosk/sessions/{sid}/fingerprint/simulate", json={"person_id": people[2]["id"], "level": "medium"}).json()
        check("huella media → pide verificación 1:1", view["mode"] == "verify" and view["candidate"]["code"] == "SMK003")
        for _ in range(10):
            view = client.post(f"/api/kiosk/sessions/{sid}/frames", content=encode_jpeg(probes[2]), headers={"Content-Type": "image/jpeg"}).json()
            if view["terminal"]:
                break
        check("huella media + rostro 1:1 → HUELLA+ROSTRO", view["state"] == "success" and view["result"]["method"] == "HUELLA+ROSTRO")

        print("\n[sface] cambio de motor y re-indexado")
        r = client.put("/api/admin/settings", json={"changes": {"face_engine": "sface"}})
        check("motor cambiado a sface", r.json()["engine"]["active"] == "sface")
        reindex = client.post("/api/admin/reindex", json={}).json()
        check("re-indexado desde las fotos de enrolamiento", reindex["created"] == 3 * n, f"{reindex}")
        for i, p in enumerate(people):
            view = mark(client, encode_jpeg(probes[i]))
            ok = view["state"] == "success" and view["result"]["person"]["code"] == p["code"]
            check(f"[sface] reconoce a {p['code']}", ok, f"{view['state']} {view.get('result') and view['result'].get('event_type')}")

        print("\n[exportación]")
        d_from = (datetime.now(TZ) - timedelta(days=1)).date().isoformat()
        r = client.get("/api/admin/export", params={"kind": "shifts", "format": "csv", "date_from": d_from})
        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        header, body = rows[0], rows[1:]
        check("CSV de jornadas con BOM UTF-8", r.content.startswith(b"\xef\xbb\xbf"))
        idx = {h: k for k, h in enumerate(header)}
        smk1 = [row for row in body if row[idx["Código"]] == "SMK001" and row[idx["Estado"]] == "COMPLETA"]
        check(
            "jornada de SMK001 = 8.25 h (08:15)",
            bool(smk1) and abs(float(smk1[0][idx["Horas (decimal)"]]) - 8.25) <= 0.03 and smk1[0][idx["Horas (HH:MM)"]] in ("08:15", "08:14", "08:16"),
            smk1[0][idx["Horas (decimal)"]] if smk1 else "sin fila",
        )
        complete = [row for row in body if row[idx["Estado"]] == "COMPLETA"]
        open_ = [row for row in body if row[idx["Estado"]] == "EN CURSO"]
        check(f"{n} jornadas completas y 3 en curso", len(complete) == n and len(open_) == 3, f"{len(complete)} / {len(open_)}")
        methods = {row[idx["Método de salida"]] for row in complete}
        check("métodos registrados en jornadas", {"ROSTRO", "HUELLA", "HUELLA+ROSTRO"} <= methods, ", ".join(sorted(methods)))
        r = client.get("/api/admin/export", params={"kind": "shifts", "format": "xlsx", "date_from": d_from})
        ws = load_workbook(io.BytesIO(r.content)).active
        check("XLSX de jornadas con las mismas filas", ws.max_row - 1 == len(body), f"{ws.max_row - 1} filas")
        r = client.get("/api/admin/export", params={"kind": "events", "format": "xlsx", "date_from": d_from})
        check("XLSX de marcaciones", r.status_code == 200 and load_workbook(io.BytesIO(r.content)).active.max_row > 1)
        r = client.get("/api/admin/export", params={"kind": "events", "format": "zip", "date_from": d_from})
        check("ZIP de marcaciones con fotos", r.status_code == 200 and len(r.content) > 10_000, f"{len(r.content) // 1024} KB")
        audit = client.get("/api/admin/audit", params={"action": "exportacion"}).json()
        check("exportaciones registradas en auditoría", audit["total"] == 4)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\nPrueba de humo: {passed}/{len(results)} verificaciones correctas")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
