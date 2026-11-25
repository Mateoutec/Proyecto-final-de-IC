"""Exportaciones para RR.HH.: jornadas, marcaciones y resumen por persona (CSV / XLSX / ZIP)."""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AttendanceEvent, Person
from app.services.shifts import Shift, load_shifts, totals_by_person
from app.timeutil import day_bounds_utc, fmt_date, fmt_time

SHIFT_HEADERS = [
    "Fecha",
    "Código",
    "Nombre",
    "Área",
    "Hora de entrada",
    "Hora de salida",
    "Horas (decimal)",
    "Horas (HH:MM)",
    "Estado",
    "Método de entrada",
    "Método de salida",
    "Foto de entrada",
    "Foto de salida",
]
EVENT_HEADERS = [
    "Fecha",
    "Hora",
    "Código",
    "Nombre",
    "Área",
    "Tipo",
    "Método",
    "Similitud rostro",
    "Umbral rostro",
    "Puntaje huella",
    "Prueba de vida",
    "Anulada",
    "Motivo de anulación",
    "Foto",
]
SUMMARY_HEADERS = [
    "Código",
    "Nombre",
    "Área",
    "Días asistidos",
    "Total horas (decimal)",
    "Total horas (HH:MM)",
    "Jornadas incompletas",
    "Jornadas en curso",
]
STATUS_TEXT = {"COMPLETA": "COMPLETA", "INCOMPLETA": "INCOMPLETA", "EN_CURSO": "EN CURSO"}


@dataclass
class ExportFilters:
    date_from: date
    date_to: date
    area_id: int | None = None


@dataclass
class Table:
    name: str
    headers: list[str]
    rows: list[list]
    photo_columns: tuple[int, ...] = ()


def _person_cols(person: Person) -> list:
    return [person.code, person.full_name, person.area.name if person.area else ""]


def shifts_table(db: Session, f: ExportFilters, tz, now: datetime, max_shift_hours: float) -> Table:
    shifts = load_shifts(
        db, date_from=f.date_from, date_to=f.date_to, tz=tz, now=now, max_shift_hours=max_shift_hours, area_id=f.area_id
    )
    rows = [shift_row(s, tz) for s in shifts]
    return Table("jornadas", SHIFT_HEADERS, rows, photo_columns=(11, 12))


def shift_row(s: Shift, tz) -> list:
    person = (s.entry or s.exit).person
    return [
        s.work_date.isoformat(),
        *_person_cols(person),
        fmt_time(s.entry.ts, tz) if s.entry else "",
        fmt_time(s.exit.ts, tz) if s.exit else "",
        s.hours if s.hours is not None else "",
        s.hhmm or "",
        STATUS_TEXT.get(s.status, s.status),
        s.entry.method if s.entry else "",
        s.exit.method if s.exit else "",
        (s.entry.photo_path or "") if s.entry else "",
        (s.exit.photo_path or "") if s.exit else "",
    ]


def events_table(db: Session, f: ExportFilters, tz) -> Table:
    lo, hi = day_bounds_utc(f.date_from, f.date_to, tz)
    query = (
        select(AttendanceEvent)
        .options(joinedload(AttendanceEvent.person).joinedload(Person.area))
        .where(AttendanceEvent.ts >= lo, AttendanceEvent.ts < hi)
        .order_by(AttendanceEvent.ts)
    )
    if f.area_id is not None:
        query = query.join(Person, Person.id == AttendanceEvent.person_id).where(Person.area_id == f.area_id)
    rows = []
    for ev in db.scalars(query).unique():
        rows.append(
            [
                fmt_date(ev.ts, tz),
                fmt_time(ev.ts, tz),
                *_person_cols(ev.person),
                ev.event_type,
                ev.method,
                ev.face_score if ev.face_score is not None else "",
                ev.face_threshold if ev.face_threshold is not None else "",
                ev.fingerprint_score if ev.fingerprint_score is not None else "",
                ev.liveness,
                "SÍ" if ev.voided else "NO",
                ev.void_reason or "",
                ev.photo_path or "",
            ]
        )
    return Table("marcaciones", EVENT_HEADERS, rows, photo_columns=(13,))


def summary_table(db: Session, f: ExportFilters, tz, now: datetime, max_shift_hours: float) -> Table:
    shifts = load_shifts(
        db, date_from=f.date_from, date_to=f.date_to, tz=tz, now=now, max_shift_hours=max_shift_hours, area_id=f.area_id
    )
    totals = totals_by_person(shifts)
    query = select(Person).options(joinedload(Person.area)).order_by(Person.last_name, Person.first_name)
    if f.area_id is not None:
        query = query.where(Person.area_id == f.area_id)
    rows = []
    for person in db.scalars(query).unique():
        t = totals.get(person.id)
        if t is None and not person.active:
            continue
        rows.append(
            [
                *_person_cols(person),
                t.days if t else 0,
                t.hours if t else 0.0,
                t.hhmm if t else "00:00",
                t.incomplete if t else 0,
                t.open if t else 0,
            ]
        )
    return Table("resumen", SUMMARY_HEADERS, rows)


def to_csv(table: Table, delimiter: str = ",") -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(table.headers)
    for row in table.rows:
        writer.writerow(["" if v is None else (f"{v:.2f}" if isinstance(v, float) else v) for v in row])
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(table: Table, title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = table.name[:31]
    ws.append(table.headers)
    header_fill = PatternFill("solid", fgColor="1E3A5F")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    for row in table.rows:
        ws.append(row)
    for col_idx, header in enumerate(table.headers, start=1):
        width = max([len(str(header))] + [len(str(r[col_idx - 1])) for r in table.rows[:500]]) + 2
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(width, 10), 48)
        for r in range(2, len(table.rows) + 2):
            cell = ws.cell(row=r, column=col_idx)
            if isinstance(cell.value, float):
                cell.number_format = "0.00" if "Horas" in header or "horas" in header else "0.0000"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.properties.title = title
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_zip(table: Table, csv_bytes: bytes, data_path: Path) -> tuple[bytes, int]:
    """ZIP con el CSV y las fotos referenciadas, con las mismas rutas relativas del CSV."""
    out = io.BytesIO()
    added: set[str] = set()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{table.name}.csv", csv_bytes)
        for row in table.rows:
            for col in table.photo_columns:
                rel = row[col]
                if not rel or rel in added:
                    continue
                file = (data_path / rel).resolve()
                if data_path.resolve() in file.parents and file.exists():
                    zf.write(file, arcname=rel)
                    added.add(rel)
    return out.getvalue(), len(added)
