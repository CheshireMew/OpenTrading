from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import settings


DEFAULT_TIMEZONE = "Asia/Shanghai"


def get_timezone(name: str | None = None) -> tzinfo:
    timezone_name = name or getattr(settings, "TIMEZONE", DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def now_in_timezone(name: str | None = None) -> datetime:
    return datetime.now(get_timezone(name))


def to_utc(value: datetime | str, source_timezone: str | None = None) -> datetime:
    if isinstance(value, str):
        parsed: datetime | None = None
        for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, date_format)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f"Unsupported date format: {value}")
        value = parsed
    if value.tzinfo is None:
        value = value.replace(tzinfo=get_timezone(source_timezone))
    return value.astimezone(timezone.utc)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
