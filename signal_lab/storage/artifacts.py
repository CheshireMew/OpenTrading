from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, cast

from signal_lab.structured_data import dumps_json


def artifact_json(path: Path, value: Any) -> Path:
    """Write a user-visible artifact; never use this as application state."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        dumps_json(_json_safe(value), indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def artifact_records(path: Path, records: Iterable[Any]) -> Path:
    """Write columnar run or label output; normalized inputs live in SQLite."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        raw = asdict(cast(Any, record)) if is_dataclass(record) else dict(record)
        row = {}
        for key, value in raw.items():
            if isinstance(value, (dict, list, tuple)):
                row[key] = dumps_json(_json_safe(value))
            else:
                row[key] = value
        rows.append(row)
    temporary = path.with_name(f".{path.name}.tmp")
    pq.write_table(pa.Table.from_pylist(rows), temporary)
    temporary.replace(path)
    return path


def storage_item(path: Path, artifact_class: str) -> dict[str, Any]:
    return {
        "class": artifact_class,
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
    }


def storage_items(paths: Iterable[Path], artifact_class: str) -> list[dict[str, Any]]:
    return [storage_item(path, artifact_class) for path in paths if path.is_file()]


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return _json_safe(asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value
