"""Enrolamiento facial, re-indexado y borrado de datos biométricos."""

from __future__ import annotations

import logging
import os
import secrets
import shutil
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.face.base import decode_image, encode_jpeg, resize_max_width
from app.face.quality import evaluate, pick_main_face
from app.models import FaceTemplate, FingerprintTemplate, Person
from app.services.audit import audit

if TYPE_CHECKING:
    from app.context import AppContext

log = logging.getLogger("app.enrollment")

POSES = {
    "frontal": {"label": "De frente", "frontal": True},
    "left": {"label": "Leve giro a tu izquierda", "frontal": False},
    "right": {"label": "Leve giro a tu derecha", "frontal": False},
    "glasses": {"label": "Con lentes (si usas) o con otra expresión", "frontal": True},
    "frontal_2": {"label": "De frente, sin lentes", "frontal": True},
    "upload": {"label": "Foto subida", "frontal": False},
}


def template_dict(t: FaceTemplate) -> dict:
    return {
        "id": t.id,
        "engine": t.engine,
        "pose": t.pose,
        "pose_label": POSES.get(t.pose, {}).get("label", t.pose),
        "quality": round(t.quality, 3),
        "photo_path": t.photo_path,
        "created_at": t.created_at.isoformat(),
    }


def enroll_photo(
    ctx: AppContext,
    db: Session,
    person: Person,
    data: bytes,
    pose: str,
    source: str,
    confirm_duplicate: bool,
    actor: str,
) -> dict:
    if pose not in POSES:
        raise AppError(f"Pose desconocida: {pose}")
    if not person.consent_signed:
        raise AppError(
            "No se puede enrolar sin el consentimiento firmado. Márcalo en la ficha de la persona.",
            status_code=409,
            code="no_consent",
        )
    if not person.active:
        raise AppError("La persona está desactivada", status_code=409)
    if not ctx.cipher.available:
        raise AppError(ctx.cipher.error or "Cifrado no disponible", status_code=500, code="no_encryption_key")
    engines = ctx.engines
    if engines.engine is None:
        raise AppError("El motor facial no está disponible", status_code=503)
    image = decode_image(data)
    if image is None:
        raise AppError("El archivo no es una imagen válida (usa JPG o PNG)")
    image = resize_max_width(image, 1280)
    faces = engines.detect(image)
    upload = source == "upload"
    report = evaluate(
        image,
        faces,
        ctx.quality_params(upload=upload),
        require_frontal=POSES[pose]["frontal"],
        max_yaw=0.45,
    )
    if not report.ok:
        log.info(
            "Enrolamiento rechazado (%s, %s, %dx%d): %s %s",
            person.code, pose, image.shape[1], image.shape[0], report.code, report.metrics,
        )
        raise AppError(
            f"Captura rechazada: {report.message}",
            status_code=422,
            code="quality",
            quality=report.code,
            metrics=report.metrics,
        )
    emb = engines.embed(image, report.face)
    engine_name = engines.active_name
    threshold = ctx.runtime.threshold_for(engine_name)
    dup = engines.index.identify(emb, threshold, 0.0, exclude=person.id)
    duplicate = None
    if dup.person_id is not None:
        other = db.get(Person, dup.person_id)
        duplicate = {
            "person_id": dup.person_id,
            "code": other.code if other else None,
            "full_name": other.full_name if other else None,
            "score": round(dup.score, 4),
            "threshold": threshold,
        }
        if not confirm_duplicate:
            raise AppError(
                f"Este rostro coincide con {duplicate['full_name']} ({duplicate['code']}): "
                f"similitud {dup.score:.3f} con umbral {threshold:.3f}. Confirma si es correcto.",
                status_code=409,
                code="duplicate",
                duplicate=duplicate,
            )
    rel_dir = f"enrollment/{person.id}"
    (ctx.data_path / rel_dir).mkdir(parents=True, exist_ok=True)
    rel_path = f"{rel_dir}/{pose}_{secrets.token_hex(4)}.jpg"
    (ctx.data_path / rel_path).write_bytes(encode_jpeg(image, 92))
    if os.name == "posix":
        os.chmod(ctx.data_path / rel_path, 0o600)
    template = FaceTemplate(
        person_id=person.id,
        engine=engine_name,
        embedding_enc=ctx.cipher.encrypt_embedding(emb),
        dim=int(emb.shape[0]),
        quality=report.score,
        pose=pose,
        photo_path=rel_path,
    )
    db.add(template)
    audit(
        db,
        actor,
        "enrolamiento",
        "person",
        person.id,
        code=person.code,
        pose=pose,
        engine=engine_name,
        source=source,
        quality=report.score,
        duplicate=duplicate,
    )
    db.commit()
    ctx.reload_templates()
    return {"template": template_dict(template), "metrics": report.metrics, "duplicate": duplicate}


def delete_template(ctx: AppContext, db: Session, template: FaceTemplate, actor: str) -> None:
    path = template.photo_path
    person_id = template.person_id
    db.delete(template)
    db.flush()
    still_used = db.scalar(select(FaceTemplate.id).where(FaceTemplate.photo_path == path).limit(1))
    if still_used is None:
        (ctx.data_path / path).unlink(missing_ok=True)
    audit(db, actor, "plantilla_eliminada", "person", person_id, template_id=template.id, photo=path)
    db.commit()
    ctx.reload_templates()


def delete_biometrics(ctx: AppContext, db: Session, person: Person, actor: str) -> dict:
    templates = list(db.scalars(select(FaceTemplate).where(FaceTemplate.person_id == person.id)))
    count = len(templates)
    db.execute(delete(FaceTemplate).where(FaceTemplate.person_id == person.id))
    db.execute(delete(FingerprintTemplate).where(FingerprintTemplate.person_id == person.id))
    slot = person.fingerprint_slot
    if slot is not None:
        try:
            ctx.fingerprint.delete(slot)
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo borrar la huella %s del sensor: %s", slot, exc)
        person.fingerprint_slot = None
    folder = ctx.data_path / "enrollment" / str(person.id)
    shutil.rmtree(folder, ignore_errors=True)
    audit(db, actor, "biometria_eliminada", "person", person.id, code=person.code, templates=count, fingerprint_slot=slot)
    db.commit()
    ctx.reload_templates()
    return {"templates_deleted": count, "fingerprint_slot_cleared": slot}


def reindex(ctx: AppContext, engine_name: str | None, actor: str) -> dict:
    target = engine_name or ctx.engines.active_name
    if target is None:
        raise AppError("No hay motor facial activo", status_code=503)
    if not ctx.cipher.available:
        raise AppError(ctx.cipher.error or "Cifrado no disponible", status_code=500)
    try:
        engine = ctx.engines.engine_for(target)
    except Exception as exc:  # noqa: BLE001
        raise AppError(f"No se pudo cargar el motor '{target}': {exc}", status_code=503) from exc
    params = ctx.quality_params(upload=True)
    created = skipped = missing = 0
    with ctx.session() as db:
        photos: dict[str, tuple[int, str]] = {}
        for t in db.scalars(select(FaceTemplate).order_by(FaceTemplate.id)):
            photos.setdefault(t.photo_path, (t.person_id, t.pose))
        db.execute(delete(FaceTemplate).where(FaceTemplate.engine == target))
        for rel_path, (person_id, pose) in photos.items():
            file = ctx.data_path / rel_path
            if not file.exists():
                missing += 1
                continue
            image = decode_image(file.read_bytes())
            if image is None:
                skipped += 1
                continue
            faces = engine.detect(image)
            main, _ = pick_main_face(faces)
            if main is None:
                skipped += 1
                continue
            report = evaluate(image, [main], params, require_frontal=False, max_yaw=0.6)
            emb = engine.embed(image, main)
            db.add(
                FaceTemplate(
                    person_id=person_id,
                    engine=target,
                    embedding_enc=ctx.cipher.encrypt_embedding(emb),
                    dim=int(emb.shape[0]),
                    quality=report.score,
                    pose=pose,
                    photo_path=rel_path,
                )
            )
            created += 1
        audit(db, actor, "reindexado", "engine", target, photos=len(photos), created=created, skipped=skipped, missing=missing)
        db.commit()
    if target == ctx.engines.active_name:
        ctx.reload_templates()
    log.info("Re-indexado %s: %s plantillas creadas, %s omitidas, %s fotos faltantes", target, created, skipped, missing)
    return {"engine": target, "photos": len(photos), "created": created, "skipped": skipped, "missing": missing}
