from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from collections.abc import Set
from typing import Any

from app.infra.structured_data import (
    DEFAULT_JSON_BUDGET,
    JsonBudget,
    canonical_json_bytes,
    load_json_file,
    loads_json,
)


MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_DEPTH = 16
MAX_MANIFEST_NODES = 200_000
MAX_MANIFEST_STRING = 16_384


def load_json_document(path: Path, *, max_bytes: int = MAX_MANIFEST_BYTES) -> Any:
    return load_json_file(
        path,
        budget=JsonBudget(
            max_bytes=max_bytes,
            max_depth=MAX_MANIFEST_DEPTH,
            max_nodes=MAX_MANIFEST_NODES,
            max_string_chars=MAX_MANIFEST_STRING,
            max_number_chars=DEFAULT_JSON_BUDGET.max_number_chars,
            max_exponent=DEFAULT_JSON_BUDGET.max_exponent,
        ),
    )


def loads_json_document(text: str, *, source: str) -> Any:
    return loads_json(text, source=source)


def content_hash(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def require_object(
    value: Any,
    *,
    source: str,
    required: set[str],
    optional: Set[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{source} must be an object")
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise ValueError(f"{source} is missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{source} has unknown fields: {', '.join(sorted(unknown))}")
    return value
