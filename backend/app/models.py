"""Modelos ORM (SQLAlchemy 2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime, utcnow


class Area(Base):
    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    people: Mapped[list[Person]] = relationship(back_populates="area")


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id", ondelete="SET NULL"))
    position: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_date: Mapped[datetime | None] = mapped_column(UTCDateTime)
    fingerprint_slot: Mapped[int | None] = mapped_column(Integer, unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    area: Mapped[Area | None] = relationship(back_populates="people")
    templates: Mapped[list[FaceTemplate]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class FaceTemplate(Base):
    __tablename__ = "face_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    engine: Mapped[str] = mapped_column(String(30), index=True)
    embedding_enc: Mapped[bytes] = mapped_column(LargeBinary)
    dim: Mapped[int] = mapped_column(Integer)
    quality: Mapped[float] = mapped_column(Float, default=0.0)
    pose: Mapped[str] = mapped_column(String(40), default="frontal")
    photo_path: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    person: Mapped[Person] = relationship(back_populates="templates")


class FingerprintTemplate(Base):
    """Respaldo cifrado de la plantilla descargada del sensor AS608."""

    __tablename__ = "fingerprint_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    slot: Mapped[int] = mapped_column(Integer)
    template_enc: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AttendanceEvent(Base):
    """Marcación inmutable: solo se puede anular (voided) con motivo."""

    __tablename__ = "attendance_events"
    __table_args__ = (Index("ix_events_person_ts", "person_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="RESTRICT"))
    ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    event_type: Mapped[str] = mapped_column(String(10))
    method: Mapped[str] = mapped_column(String(20))
    face_score: Mapped[float | None] = mapped_column(Float)
    face_threshold: Mapped[float | None] = mapped_column(Float)
    face_margin: Mapped[float | None] = mapped_column(Float)
    fingerprint_score: Mapped[float | None] = mapped_column(Float)
    liveness: Mapped[str] = mapped_column(String(20))
    liveness_challenge: Mapped[str | None] = mapped_column(String(10))
    engine: Mapped[str | None] = mapped_column(String(30))
    photo_path: Mapped[str | None] = mapped_column(String(300))
    manual_reason: Mapped[str | None] = mapped_column(Text)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    void_reason: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    voided_by: Mapped[str | None] = mapped_column(String(60))
    created_by: Mapped[str] = mapped_column(String(30), default="kiosco")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    person: Mapped[Person] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(60))
    details: Mapped[str | None] = mapped_column(Text)


class AppSetting(Base):
    """Overrides de configuración hechos desde el panel."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
