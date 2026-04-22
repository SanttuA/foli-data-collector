from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def unix_to_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except (TypeError, ValueError, OSError):
        return None


def unix_to_iso(value: Any) -> str | None:
    return isoformat_z(unix_to_datetime(value))


def seconds_between(later: datetime, earlier_iso: str | None) -> int | None:
    earlier = parse_utc(earlier_iso)
    if earlier is None:
        return None
    return max(0, int((later - earlier).total_seconds()))


def add_seconds(value: datetime, seconds: int | float) -> str:
    return isoformat_z(value + timedelta(seconds=float(seconds))) or ""


def http_date_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return isoformat_z(parsed)

