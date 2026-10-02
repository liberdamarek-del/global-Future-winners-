"""Všechny časy v projektu jsou UTC ve formátu 'YYYY-MM-DDTHH:MM:SSZ'."""

from datetime import date, datetime, timezone

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("čas bez časové zóny — použij UTC (timezone.utc)")
    return dt.astimezone(timezone.utc).strftime(ISO_FORMAT)


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, ISO_FORMAT).replace(tzinfo=timezone.utc)


def parse_date(value: str) -> date:
    """Přijme pouze přesné datum 'YYYY-MM-DD'."""
    if len(value) != 10:
        raise ValueError(f"očekáváno datum YYYY-MM-DD, ne {value!r}")
    return date.fromisoformat(value)
