from __future__ import annotations

import json
from typing import Any


def decode_strict_json_object(content: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid numeric constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    decoded = json.loads(
        content,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )
    if not isinstance(decoded, dict):
        raise TypeError("JSON root must be an object")
    return decoded


__all__ = ["decode_strict_json_object"]
