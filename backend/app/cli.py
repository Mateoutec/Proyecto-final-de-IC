"""Comandos de mantenimiento: `uv run python -m app.cli <comando>` (desde backend/)."""

from __future__ import annotations

import argparse
import json
import secrets
import string
import sys
from pathlib import Path

from app.config import PROJECT_ROOT, Settings

ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _ctx():
    from app.context import AppContext

    return AppContext(Settings())


def cmd_env_init(_args) -> int:
    """Crea .env desde .env.example sin sobrescribir claves existentes."""
    from app.crypto import generate_key

    if not ENV_EXAMPLE.exists():
        print("✗ Falta .env.example")
        return 1
    existing: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                existing[key.strip()] = value.strip()
    alphabet = string.ascii_letters + string.digits
    generated = {
        "ADMIN_PASSWORD": "".join(secrets.choice(alphabet) for _ in range(14)),
        "SESSION_SECRET": secrets.token_hex(32),
        "ENCRYPTION_KEY": generate_key(),
    }
    lines, created = [], []
    seen = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, default = (part.strip() for part in line.split("=", 1))
            seen.add(key)
            if existing.get(key):
                lines.append(f"{key}={existing[key]}")
            elif key in generated:
                lines.append(f"{key}={generated[key]}")
                created.append(key)
            else:
                lines.append(f"{key}={existing.get(key, default)}")
        else:
            lines.append(line)
    extra = [f"{k}={v}" for k, v in existing.items() if k not in seen]
    if extra:
        lines += ["", "# Variables propias conservadas", *extra]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if sys.platform != "win32":
        ENV_FILE.chmod(0o600)
    print(f"✓ .env listo ({'claves generadas: ' + ', '.join(created) if created else 'sin cambios en las claves'})")
    return 0


def cmd_init_db(_args) -> int:
    ctx = _ctx()
    print(f"✓ Base de datos lista en {ctx.settings.database_path}")
    return 0


def cmd_download_models(_args) -> int:
    from app.models_download import ensure_models

    errors = ensure_models(Settings().models_path)
    return 1 if errors else 0


def cmd_check_engine(_args) -> int:
    ctx = _ctx()
    status = ctx.engines.status()
    _print(status)
    return 0 if status["ready"] else 1


def cmd_seed_demo(args) -> int:
    from app.seed import clear_demo, seed_demo

    ctx = _ctx()
    _print(clear_demo(ctx) if args.clear else seed_demo(ctx))
    return 0


def cmd_reindex(args) -> int:
    from app.services.enrollment import reindex

    ctx = _ctx()
    _print(reindex(ctx, args.engine, "cli"))
    return 0


def cmd_calibrate(_args) -> int:
    from app.errors import AppError
    from app.services.calibration import run_calibration

    ctx = _ctx()
    try:
        result = run_calibration(ctx, "cli")
    except AppError as exc:
        print(f"✗ {exc.message}")
        return 1
    _print(result)
    print(f"\nArchivos en {ctx.data_path / Path(result['files']['csv']).parent}")
    return 0


def cmd_fingerprint_diagnose(_args) -> int:
    from app.fingerprint.as608 import AS608Provider, list_serial_ports

    settings = Settings()
    print("Puertos serie detectados:")
    ports = list_serial_ports()
    for p in ports:
        print(f"  {p['device']}  ({p['description']})")
    if not ports:
        print("  (ninguno) — revisa el cable USB-TTL y el driver (CH340/CP2102)")
    print(f"\nProbando AS608 en {settings.fingerprint_port} a {settings.fingerprint_baudrate} baudios…")
    provider = AS608Provider(settings.fingerprint_port, settings.fingerprint_baudrate)
    status = provider.status()
    _print(status)
    provider.close()
    return 0 if status.get("connected") else 1


def cmd_fingerprint_enroll(args) -> int:
    from sqlalchemy import select

    from app.models import FingerprintTemplate, Person
    from app.services.audit import audit

    ctx = _ctx()
    if ctx.fingerprint.name != "as608":
        print("✗ Configura FINGERPRINT_PROVIDER=as608 en .env")
        return 1
    with ctx.session() as db:
        person = db.scalar(select(Person).where(Person.code == args.code))
        if person is None:
            print(f"✗ No existe la persona {args.code}")
            return 1
        if not person.consent_signed:
            print("✗ La persona no tiene el consentimiento firmado")
            return 1
        used = set(db.scalars(select(Person.fingerprint_slot).where(Person.fingerprint_slot.is_not(None))))
        slot = args.slot or person.fingerprint_slot or next(i for i in range(1, 1001) if i not in used)
        print(f"Enrolando a {person.full_name} en la posición {slot}. Coloca el dedo, retíralo y vuelve a colocarlo.")
        template = ctx.fingerprint.enroll(slot)
        person.fingerprint_slot = slot
        if template:
            db.add(FingerprintTemplate(person_id=person.id, slot=slot, template_enc=ctx.cipher.encrypt_bytes(template)))
        audit(db, "cli", "huella_enrolada", "person", person.id, slot=slot, backup=bool(template))
        db.commit()
    print(f"✓ Huella guardada en la posición {slot}{' con respaldo en la base' if template else ''}")
    return 0


def cmd_fingerprint_restore(_args) -> int:
    from sqlalchemy import select

    from app.models import FingerprintTemplate

    ctx = _ctx()
    if ctx.fingerprint.name != "as608":
        print("✗ Configura FINGERPRINT_PROVIDER=as608 en .env")
        return 1
    with ctx.session() as db:
        rows = list(db.scalars(select(FingerprintTemplate)))
        for row in rows:
            ctx.fingerprint.restore(row.slot, ctx.cipher.decrypt_bytes(row.template_enc))
            print(f"✓ posición {row.slot} restaurada")
    print(f"{len(rows)} huellas restauradas en el sensor")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Asistencia biométrica — mantenimiento")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("env-init", help="crea/completa .env sin sobrescribir claves").set_defaults(fn=cmd_env_init)
    sub.add_parser("init-db", help="crea las tablas").set_defaults(fn=cmd_init_db)
    sub.add_parser("download-models", help="descarga buffalo_l, YuNet/SFace y la imagen t1").set_defaults(
        fn=cmd_download_models
    )
    sub.add_parser("check-engine", help="carga el motor facial e informa su estado").set_defaults(fn=cmd_check_engine)
    p = sub.add_parser("seed-demo", help="crea áreas, personas y marcaciones de demostración (sin biometría)")
    p.add_argument("--clear", action="store_true", help="borra los datos de demostración")
    p.set_defaults(fn=cmd_seed_demo)
    p = sub.add_parser("reindex", help="regenera plantillas desde las fotos de enrolamiento")
    p.add_argument("--engine", choices=["insightface", "sface", "fake"], default=None)
    p.set_defaults(fn=cmd_reindex)
    sub.add_parser("calibrate", help="FAR/FRR, umbral sugerido, CSV y gráfico").set_defaults(fn=cmd_calibrate)
    sub.add_parser("fingerprint-diagnose", help="diagnóstico del sensor AS608").set_defaults(fn=cmd_fingerprint_diagnose)
    p = sub.add_parser("fingerprint-enroll", help="enrola una huella en el AS608")
    p.add_argument("--code", required=True, help="código de la persona")
    p.add_argument("--slot", type=int, default=None)
    p.set_defaults(fn=cmd_fingerprint_enroll)
    sub.add_parser("fingerprint-restore", help="restaura en el sensor las huellas respaldadas").set_defaults(
        fn=cmd_fingerprint_restore
    )
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
