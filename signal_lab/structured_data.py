from __future__ import annotations

from dataclasses import dataclass
import gzip
import json
import math
from pathlib import Path
import re
from typing import Any, BinaryIO, Callable, Protocol


class BinaryReadable(Protocol):
    def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True, slots=True)
class JsonBudget:
    max_bytes: int = 8 * 1024 * 1024
    max_depth: int = 16
    max_nodes: int = 200_000
    max_string_chars: int = 16_384
    max_number_chars: int = 128
    max_exponent: int = 308


DEFAULT_JSON_BUDGET = JsonBudget()


class StructuredDataError(ValueError):
    """Stable failure raised by every untrusted structured-data boundary."""

    def __init__(self, code: str, source: str, detail: str) -> None:
        self.code = code
        self.source = source
        self.detail = detail
        super().__init__(f"{code}: {detail} ({source})")


def load_json_file(
    path: Path,
    *,
    budget: JsonBudget = DEFAULT_JSON_BUDGET,
) -> Any:
    source = str(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise StructuredDataError("json.read_failed", source, str(exc)) from exc
    if size > budget.max_bytes:
        raise StructuredDataError(
            "json.too_large", source, f"document exceeds {budget.max_bytes} bytes",
        )
    try:
        with path.open("rb") as stream:
            raw = _read_limited(stream, source=source, max_bytes=budget.max_bytes)
    except StructuredDataError:
        raise
    except OSError as exc:
        raise StructuredDataError("json.read_failed", source, str(exc)) from exc
    return loads_json(raw, source=source, budget=budget)


def load_gzip_json_file(
    path: Path,
    *,
    budget: JsonBudget = DEFAULT_JSON_BUDGET,
) -> Any:
    source = str(path)
    try:
        with path.open("rb") as raw_stream:
            with gzip.GzipFile(fileobj=raw_stream, mode="rb") as stream:
                raw = _read_limited(stream, source=source, max_bytes=budget.max_bytes)
    except StructuredDataError:
        raise
    except (OSError, EOFError) as exc:
        raise StructuredDataError("json.decompression_failed", source, str(exc)) from exc
    return loads_json(raw, source=source, budget=budget)


def load_json_response(
    response: BinaryIO,
    *,
    source: str,
    budget: JsonBudget = DEFAULT_JSON_BUDGET,
) -> Any:
    headers = getattr(response, "headers", None)
    content_length = headers.get("Content-Length") if headers is not None else None
    if content_length:
        try:
            declared = int(content_length)
        except (TypeError, ValueError):
            declared = None
        if declared is not None and declared > budget.max_bytes:
            raise StructuredDataError(
                "json.too_large", source, f"response exceeds {budget.max_bytes} bytes",
            )
    raw = _read_limited(response, source=source, max_bytes=budget.max_bytes)
    return loads_json(raw, source=source, budget=budget)


def read_bounded_response(
    response: BinaryIO,
    *,
    source: str,
    max_bytes: int,
) -> bytes:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    headers = getattr(response, "headers", None)
    content_length = headers.get("Content-Length") if headers is not None else None
    if content_length:
        try:
            declared = int(content_length)
        except (TypeError, ValueError):
            declared = None
        if declared is not None and declared > max_bytes:
            raise StructuredDataError(
                "response.too_large", source, f"response exceeds {max_bytes} bytes",
            )
    return _read_limited(
        response,
        source=source,
        max_bytes=max_bytes,
        too_large_code="response.too_large",
    )


def loads_json(
    document: str | bytes | bytearray,
    *,
    source: str,
    budget: JsonBudget = DEFAULT_JSON_BUDGET,
) -> Any:
    if isinstance(document, str):
        raw = document.encode("utf-8")
        text = document
    else:
        raw = bytes(document)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StructuredDataError(
                "json.invalid_encoding", source, "document must use UTF-8",
            ) from exc
    if len(raw) > budget.max_bytes:
        raise StructuredDataError(
            "json.too_large", source, f"document exceeds {budget.max_bytes} bytes",
        )
    _preflight_json(text, source=source, budget=budget)
    try:
        return json.loads(
            text,
            object_pairs_hook=lambda items: _unique_object(items, source=source),
            parse_constant=lambda token: _reject_constant(token, source=source),
            parse_int=lambda token: _parse_int(token, source=source, budget=budget),
            parse_float=lambda token: _parse_float(token, source=source, budget=budget),
        )
    except StructuredDataError:
        raise
    except json.JSONDecodeError as exc:
        raise StructuredDataError("json.invalid_syntax", source, str(exc)) from exc


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


def _read_limited(
    stream: BinaryReadable,
    *,
    source: str,
    max_bytes: int,
    too_large_code: str = "json.too_large",
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(64 * 1024, max_bytes - total + 1))
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8")
        total += len(chunk)
        if total > max_bytes:
            raise StructuredDataError(
                too_large_code, source, f"document exceeds {max_bytes} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _preflight_json(text: str, *, source: str, budget: JsonBudget) -> None:
    index = 0
    depth = 0
    nodes = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character in " \t\r\n,:":
            index += 1
            continue
        if character == '"':
            index = _scan_string(text, index, source=source, budget=budget)
            nodes += 1
        elif character in "[{":
            depth += 1
            nodes += 1
            if depth > budget.max_depth:
                raise StructuredDataError(
                    "json.too_deep", source, f"nesting exceeds {budget.max_depth}",
                )
            index += 1
        elif character in "]}":
            depth -= 1
            index += 1
        elif character == "-" or character.isdigit():
            end = index + 1
            while end < length and text[end] not in " \t\r\n,]}":
                end += 1
            token = text[index:end]
            _validate_number_token(token, source=source, budget=budget)
            nodes += 1
            index = end
        elif text.startswith("true", index):
            nodes += 1
            index += 4
        elif text.startswith("false", index):
            nodes += 1
            index += 5
        elif text.startswith("null", index):
            nodes += 1
            index += 4
        else:
            index += 1
        if nodes > budget.max_nodes:
            raise StructuredDataError(
                "json.too_many_nodes", source, f"node count exceeds {budget.max_nodes}",
            )


def _scan_string(text: str, start: int, *, source: str, budget: JsonBudget) -> int:
    index = start + 1
    characters = 0
    while index < len(text):
        character = text[index]
        if character == '"':
            return index + 1
        if character == "\\":
            index += 1
            if index >= len(text):
                return index
            if text[index] == "u":
                index += 4
        characters += 1
        if characters > budget.max_string_chars:
            raise StructuredDataError(
                "json.string_too_long", source,
                f"string length exceeds {budget.max_string_chars} characters",
            )
        index += 1
    return index


_JSON_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE]([+-]?[0-9]+))?\Z")


def _validate_number_token(token: str, *, source: str, budget: JsonBudget) -> None:
    if len(token) > budget.max_number_chars:
        raise StructuredDataError(
            "json.number_too_long", source,
            f"number token exceeds {budget.max_number_chars} characters",
        )
    match = _JSON_NUMBER.fullmatch(token)
    if match is None:
        return
    exponent = match.group(1)
    if exponent is not None and abs(int(exponent)) > budget.max_exponent:
        raise StructuredDataError(
            "json.exponent_out_of_range", source,
            f"absolute exponent exceeds {budget.max_exponent}",
        )


def _unique_object(items: list[tuple[str, Any]], *, source: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise StructuredDataError("json.duplicate_key", source, f"duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str, *, source: str) -> Any:
    raise StructuredDataError("json.non_finite_number", source, f"number is not finite: {token}")


def _parse_int(token: str, *, source: str, budget: JsonBudget) -> int:
    _validate_number_token(token, source=source, budget=budget)
    return int(token)


def _parse_float(token: str, *, source: str, budget: JsonBudget) -> float:
    _validate_number_token(token, source=source, budget=budget)
    value = float(token)
    if not math.isfinite(value):
        raise StructuredDataError("json.non_finite_number", source, f"number is not finite: {token}")
    return value
