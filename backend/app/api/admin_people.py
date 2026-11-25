"""Panel: áreas, personas, plantillas faciales y huella."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_ctx, get_db, require_admin
from app.api.serializers import area_dict, file_url, person_dict, template_counts
from app.context import AppContext
from app.errors import AppError, NotFound
from app.fingerprint.base import SimulatedProvider
from app.models import Area, AttendanceEvent, FaceTemplate, FingerprintTemplate, Person
from app.services.audit import audit
from app.services.enrollment import POSES, delete_biometrics, delete_template, enroll_photo, template_dict

router = APIRouter(prefix="/api/admin", tags=["panel: personas"], dependencies=[Depends(require_admin)])

MAX_UPLOAD = 12_000_000


# ------------------------------------------------------------------ áreas
class AreaIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("el nombre no puede estar vacío")
        return v


@router.get("/areas")
def list_areas(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Person.area_id, func.count()).where(Person.active.is_(True)).group_by(Person.area_id)).all())
    return [area_dict(a, counts.get(a.id, 0)) for a in db.scalars(select(Area).order_by(Area.name))]


@router.post("/areas", status_code=201)
def create_area(body: AreaIn, db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    if db.scalar(select(Area).where(func.lower(Area.name) == body.name.lower())):
        raise AppError(f"Ya existe un área llamada '{body.name}'", status_code=409)
    area = Area(name=body.name, description=body.description)
    db.add(area)
    db.flush()
    audit(db, actor, "area_creada", "area", area.id, name=area.name)
    db.commit()
    return area_dict(area, 0)


@router.put("/areas/{area_id}")
def update_area(area_id: int, body: AreaIn, db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    area = db.get(Area, area_id) or _raise(NotFound("Área no encontrada"))
    clash = db.scalar(select(Area).where(func.lower(Area.name) == body.name.lower(), Area.id != area_id))
    if clash:
        raise AppError(f"Ya existe un área llamada '{body.name}'", status_code=409)
    area.name, area.description = body.name, body.description
    audit(db, actor, "area_editada", "area", area.id, name=area.name)
    db.commit()
    return area_dict(area)


@router.delete("/areas/{area_id}")
def delete_area(area_id: int, db: Session = Depends(get_db), actor: str = Depends(require_admin)):
    area = db.get(Area, area_id) or _raise(NotFound("Área no encontrada"))
    in_use = db.scalar(select(func.count()).select_from(Person).where(Person.area_id == area_id))
    if in_use:
        raise AppError(f"El área tiene {in_use} persona(s). Reasígnalas antes de eliminarla.", status_code=409)
    db.delete(area)
    audit(db, actor, "area_eliminada", "area", area_id, name=area.name)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ personas
class PersonIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    area_id: int | None = None
    position: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    active: bool = True
    consent_signed: bool = False
    consent_date: date | None = None

    @field_validator("code", "first_name", "last_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("no puede estar vacío")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("no es un correo válido")
        return v


def _raise(exc: Exception):
    raise exc


def _get_person(db: Session, person_id: int) -> Person:
    person = db.scalar(select(Person).options(joinedload(Person.area)).where(Person.id == person_id))
    if person is None:
        raise NotFound("Persona no encontrada")
    return person


def _apply(person: Person, body: PersonIn, ctx: AppContext) -> None:
    person.code = body.code
    person.first_name = body.first_name
    person.last_name = body.last_name
    person.area_id = body.area_id
    person.position = body.position or None
    person.email = body.email
    person.active = body.active
    if body.consent_signed and not person.consent_signed:
        consent_day = body.consent_date or ctx.now().astimezone(ctx.tz).date()
        person.consent_date = datetime.combine(consent_day, time(12, 0), tzinfo=ctx.tz).astimezone(timezone.utc)
    elif body.consent_signed and body.consent_date:
        person.consent_date = datetime.combine(body.consent_date, time(12, 0), tzinfo=ctx.tz).astimezone(timezone.utc)
    elif not body.consent_signed:
        person.consent_date = None
    person.consent_signed = body.consent_signed


def _person_out(db: Session, ctx: AppContext, person: Person) -> dict:
    counts = template_counts(db, [person.id]).get(person.id, {})
    return person_dict(person, counts, ctx.engines.active_name, ctx.tz)


@router.get("/people")
def list_people(
    search: str | None = None,
    area_id: int | None = None,
    status: str = "all",
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
):
    query = select(Person).options(joinedload(Person.area)).order_by(Person.last_name, Person.first_name)
    if search:
        like = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Person.code).like(like),
                func.lower(Person.first_name).like(like),
                func.lower(Person.last_name).like(like),
                func.lower(Person.first_name + " " + Person.last_name).like(like),
            )
        )
    if area_id is not None:
        query = query.where(Person.area_id == area_id)
    if status == "active":
        query = query.where(Person.active.is_(True))
    elif status == "inactive":
        query = query.where(Person.active.is_(False))
    people = list(db.scalars(query).unique())
    counts = template_counts(db, [p.id for p in people])
    last_events = {}
    if people:
        sub = (
            select(AttendanceEvent.person_id, func.max(AttendanceEvent.ts).label("ts"))
            .where(AttendanceEvent.voided.is_(False))
            .group_by(AttendanceEvent.person_id)
            .subquery()
        )
        for ev in db.scalars(
            select(AttendanceEvent).join(sub, (sub.c.person_id == AttendanceEvent.person_id) & (sub.c.ts == AttendanceEvent.ts))
        ):
            last_events[ev.person_id] = ev
    out = []
    for p in people:
        item = person_dict(p, counts.get(p.id, {}), ctx.engines.active_name, ctx.tz)
        ev = last_events.get(p.id)
        item["last_event"] = (
            {"event_type": ev.event_type, "local": ev.ts.astimezone(ctx.tz).strftime("%Y-%m-%d %H:%M")} if ev else None
        )
        out.append(item)
    return out


@router.post("/people", status_code=201)
def create_person(
    body: PersonIn, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)
):
    if db.scalar(select(Person).where(func.lower(Person.code) == body.code.lower())):
        raise AppError(f"Ya existe una persona con el código {body.code}", status_code=409, code="duplicate_code")
    if body.area_id is not None and db.get(Area, body.area_id) is None:
        raise AppError("El área seleccionada no existe")
    person = Person()
    _apply(person, body, ctx)
    db.add(person)
    db.flush()
    audit(db, actor, "persona_creada", "person", person.id, code=person.code, name=person.full_name)
    db.commit()
    return _person_out(db, ctx, _get_person(db, person.id))


@router.get("/people/{person_id}")
def get_person(person_id: int, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx)):
    person = _get_person(db, person_id)
    out = _person_out(db, ctx, person)
    out["face_templates"] = [
        {**template_dict(t), "photo_url": file_url(t.photo_path), "active_engine": t.engine == ctx.engines.active_name}
        for t in db.scalars(select(FaceTemplate).where(FaceTemplate.person_id == person_id).order_by(FaceTemplate.id))
    ]
    out["fingerprint_backup"] = (
        db.scalar(select(func.count()).select_from(FingerprintTemplate).where(FingerprintTemplate.person_id == person_id)) or 0
    )
    out["events_count"] = db.scalar(
        select(func.count()).select_from(AttendanceEvent).where(AttendanceEvent.person_id == person_id)
    )
    out["poses"] = [{"key": k, **v} for k, v in POSES.items() if k != "upload"]
    return out


@router.put("/people/{person_id}")
def update_person(
    person_id: int,
    body: PersonIn,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
    actor: str = Depends(require_admin),
):
    person = _get_person(db, person_id)
    clash = db.scalar(select(Person).where(func.lower(Person.code) == body.code.lower(), Person.id != person_id))
    if clash:
        raise AppError(f"Ya existe una persona con el código {body.code}", status_code=409, code="duplicate_code")
    if body.area_id is not None and db.get(Area, body.area_id) is None:
        raise AppError("El área seleccionada no existe")
    before = {"code": person.code, "active": person.active, "consent": person.consent_signed}
    was_active = person.active
    _apply(person, body, ctx)
    audit(db, actor, "persona_editada", "person", person.id, before=before, after=body.model_dump(mode="json"))
    db.commit()
    if was_active != person.active:
        ctx.reload_templates()
    return _person_out(db, ctx, _get_person(db, person_id))


@router.delete("/people/{person_id}")
def delete_person(
    person_id: int, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)
):
    person = _get_person(db, person_id)
    events = db.scalar(select(func.count()).select_from(AttendanceEvent).where(AttendanceEvent.person_id == person_id))
    if events:
        raise AppError(
            f"{person.full_name} tiene {events} marcaciones. Desactívala en lugar de eliminarla.", status_code=409
        )
    delete_biometrics(ctx, db, person, actor)
    db.delete(person)
    audit(db, actor, "persona_eliminada", "person", person_id, code=person.code)
    try:
        db.commit()
    except IntegrityError as exc:
        raise AppError("No se pudo eliminar la persona", status_code=409) from exc
    ctx.reload_templates()
    return {"ok": True}


@router.delete("/people/{person_id}/biometrics")
def remove_biometrics(
    person_id: int, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)
):
    return delete_biometrics(ctx, db, _get_person(db, person_id), actor)


# ------------------------------------------------------------------ plantillas
@router.post("/people/{person_id}/templates", status_code=201)
async def add_template(
    person_id: int,
    file: UploadFile = File(...),
    pose: str = Form("frontal"),
    source: str = Form("camera"),
    confirm_duplicate: bool = Form(False),
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
    actor: str = Depends(require_admin),
):
    data = await file.read()
    if not data:
        raise AppError("No se recibió ninguna imagen")
    if len(data) > MAX_UPLOAD:
        raise AppError("La imagen supera 12 MB", status_code=413)
    person = _get_person(db, person_id)
    return await run_in_threadpool(
        enroll_photo, ctx, db, person, data, pose, "upload" if source == "upload" else "camera", confirm_duplicate, actor
    )


@router.delete("/templates/{template_id}")
def remove_template(
    template_id: int, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)
):
    template = db.get(FaceTemplate, template_id) or _raise(NotFound("Plantilla no encontrada"))
    delete_template(ctx, db, template, actor)
    return {"ok": True}


# ------------------------------------------------------------------ huella
class FingerprintIn(BaseModel):
    slot: int | None = Field(default=None, ge=1, le=1000)


@router.post("/people/{person_id}/fingerprint")
async def enroll_fingerprint(
    person_id: int,
    body: FingerprintIn | None = None,
    db: Session = Depends(get_db),
    ctx: AppContext = Depends(get_ctx),
    actor: str = Depends(require_admin),
):
    person = _get_person(db, person_id)
    provider = ctx.fingerprint
    if provider.name == "disabled":
        raise AppError("La huella no está configurada (FINGERPRINT_PROVIDER=disabled)", status_code=409)
    if not person.consent_signed:
        raise AppError("No se puede enrolar sin el consentimiento firmado", status_code=409, code="no_consent")
    used = set(db.scalars(select(Person.fingerprint_slot).where(Person.fingerprint_slot.is_not(None), Person.id != person_id)))
    slot = (body.slot if body else None) or person.fingerprint_slot or next(i for i in range(1, 1001) if i not in used)
    if slot in used:
        raise AppError(f"La posición {slot} del sensor ya está asignada", status_code=409)
    template = None
    if not isinstance(provider, SimulatedProvider):
        template = await run_in_threadpool(provider.enroll, slot)
    person.fingerprint_slot = slot
    if template:
        db.add(FingerprintTemplate(person_id=person.id, slot=slot, template_enc=ctx.cipher.encrypt_bytes(template)))
    audit(db, actor, "huella_enrolada", "person", person.id, slot=slot, provider=provider.name, backup=bool(template))
    db.commit()
    return {"slot": slot, "backup": bool(template), "provider": provider.name}


@router.delete("/people/{person_id}/fingerprint")
def remove_fingerprint(
    person_id: int, db: Session = Depends(get_db), ctx: AppContext = Depends(get_ctx), actor: str = Depends(require_admin)
):
    person = _get_person(db, person_id)
    slot = person.fingerprint_slot
    if slot is None:
        raise AppError("La persona no tiene huella registrada", status_code=409)
    try:
        ctx.fingerprint.delete(slot)
    except AppError:
        pass
    person.fingerprint_slot = None
    for t in db.scalars(select(FingerprintTemplate).where(FingerprintTemplate.person_id == person_id)):
        db.delete(t)
    audit(db, actor, "huella_eliminada", "person", person.id, slot=slot)
    db.commit()
    return {"ok": True}
