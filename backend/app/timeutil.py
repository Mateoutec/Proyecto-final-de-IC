"""Zonas horarias y formatos. En la base todo es UTC; se muestra en la zona configurada."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.errors import AppError


@lru_cache(maxsize=8)
def get_tz(name: str = "") -> ZoneInfo:
    if name:
        try:
            return ZoneInfo(name)
        except Exception as exc:  # noqa: BLE001
            raise AppError(f"Zona horaria inválida: {name}") from exc
    try:
        from tzlocal import get_localzone

        tz = get_localzone()
        if isinstance(tz, ZoneInfo):
            return tz
        return ZoneInfo(str(tz))
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def tz_name(tz: ZoneInfo) -> str:
    return getattr(tz, "key", str(tz))


def to_local(dt: datetime, tz: ZoneInfo) -> datetime:
    return dt.astimezone(tz)


def fmt_date(dt: datetime, tz: ZoneInfo) -> str:
    return to_local(dt, tz).strftime("%Y-%m-%d")


def fmt_time(dt: datetime, tz: ZoneInfo, seconds: bool = True) -> str:
    return to_local(dt, tz).strftime("%H:%M:%S" if seconds else "%H:%M")


def iso_local(dt: datetime | None, tz: ZoneInfo) -> str | None:
    return to_local(dt, tz).isoformat(timespec="seconds") if dt else None


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    return to_local(dt, tz).date()


def day_bounds_utc(start: date, end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[inicio de `start`, inicio del día siguiente a `end`) en UTC."""
    lo = datetime.combine(start, time.min, tzinfo=tz).astimezone(timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return lo, hi


def parse_local_datetime(value: str, tz: ZoneInfo) -> datetime:
    """Interpreta '2026-10-24T08:15' (hora local) o un ISO con zona; devuelve UTC."""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AppError("Fecha y hora inválidas; usa el formato AAAA-MM-DDTHH:MM") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


def hours_decimal(seconds: float) -> float:
    return round(seconds / 3600.0, 2)


def hours_hhmm(seconds: float) -> str:
    minutes = int(round(seconds / 60.0))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
