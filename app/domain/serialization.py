from __future__ import annotations

import json
from typing import Any, Callable


class StructuredDataError(ValueError):
    """Stable failure raised by every untrusted structured-data boundary."""

    def __init__(self, code: str, source: str, detail: str) -> None:
        self.code = code
        self.source = source
        self.detail = detail
        super().__init__(f"{code}: {detail} ({source})")


def dumps_json(
    value: Any,
    *,
    sort_keys: bool = True,
    compact: bool = False,
    indent: int | None = None,
    default: Callable[[Any], Any] | None = None,
) -> str:
    if compact and indent is not None:
        raise ValueError("compact JSON cannot also be indented")
    separators = (",", ":") if compact else None
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=sort_keys,
            separators=separators,
            indent=indent,
            allow_nan=False,
            default=default,
        )
    except (TypeError, ValueError) as exc:
        raise StructuredDataError("json.encode_failed", "in-memory value", str(exc)) from exc


def canonical_json_bytes(value: Any, *, default: Callable[[Any], Any] | None = None) -> bytes:
    return dumps_json(value, compact=True, default=default).encode("utf-8")
