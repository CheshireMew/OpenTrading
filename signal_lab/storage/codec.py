from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast

from signal_lab.structured_data import dumps_json, loads_json


def json_dumps(value: Any) -> str:
    return dumps_json(value, default=_json_default)


def json_loads(value: str) -> Any:
    return loads_json(value, source="Signal Lab database JSON field")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, (datetime, date)) else str(value)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(cast(Any, value))
    if isinstance(value, tuple):
        return list(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"cannot serialize {type(value).__name__}")
