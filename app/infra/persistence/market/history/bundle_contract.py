from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.infra.persistence.market.history.contracts import require_object
from app.infra.persistence.market.history.identities import raw_acquisition_id


BUNDLE_SCHEMA_VERSION = "signal-lab.snapshot-bundle.v2"
LEGACY_BUNDLE_SCHEMA_VERSION = "signal-lab.snapshot-bundle.v1"

def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = require_object(
        value,
        source="bundle manifest",
        required={"schema_version", "created_at", "snapshots", "raw_snapshots"},
    )
    if manifest["schema_version"] not in {
        BUNDLE_SCHEMA_VERSION, LEGACY_BUNDLE_SCHEMA_VERSION,
    }:
        raise ValueError(f"unsupported bundle schema: {manifest['schema_version']}")
    _aware_datetime(manifest["created_at"], "bundle created_at")
    if not isinstance(manifest["snapshots"], list) or not manifest["snapshots"]:
        raise ValueError("bundle requires at least one price snapshot")
    if not isinstance(manifest["raw_snapshots"], list):
        raise ValueError("bundle raw_snapshots must be an array")
    snapshot_ids: set[str] = set()
    for index, raw in enumerate(manifest["snapshots"]):
        item = require_object(
            raw,
            source=f"snapshots[{index}]",
            required={
                "snapshot_hash", "instrument", "timeframe", "provider", "provider_symbol",
                "requested_start", "requested_end", "retrieved_at", "source_snapshot_hash",
                "raw_evidence_hashes", "price_basis", "coverage_status", "metadata",
                "coverage_issues", "artifact",
            } | ({"identity_version"} if manifest["schema_version"] == BUNDLE_SCHEMA_VERSION else set()),
        )
        if item["snapshot_hash"] in snapshot_ids:
            raise ValueError(f"duplicate bundle snapshot: {item['snapshot_hash']}")
        _sha256_value(item["snapshot_hash"], f"snapshots[{index}].snapshot_hash")
        if "identity_version" in item and item["identity_version"] not in {1, 2}:
            raise ValueError(f"snapshots[{index}].identity_version must be 1 or 2")
        snapshot_ids.add(item["snapshot_hash"])
        instrument = require_object(
            item["instrument"],
            source=f"snapshots[{index}].instrument",
            required={
                "canonical_code", "name", "asset_class", "market", "exchange", "currency",
                "timezone", "listed_on", "is_continuous", "metadata",
            },
        )
        for key in (
            "canonical_code", "name", "asset_class", "market", "exchange", "currency",
            "timezone",
        ):
            _nonempty_string(instrument[key], f"snapshots[{index}].instrument.{key}")
        if instrument["listed_on"] is not None:
            _date_value(instrument["listed_on"], f"snapshots[{index}].instrument.listed_on")
        if type(instrument["is_continuous"]) is not bool:
            raise ValueError(f"snapshots[{index}].instrument.is_continuous must be boolean")
        if not isinstance(instrument["metadata"], dict):
            raise ValueError(f"snapshots[{index}].instrument.metadata must be an object")
        artifact = require_object(
            item["artifact"],
            source=f"snapshots[{index}].artifact",
            required={
                "path", "size_bytes", "file_sha256", "parquet_schema_version", "row_count",
            },
        )
        for key in ("timeframe", "provider", "price_basis", "coverage_status"):
            _nonempty_string(item[key], f"snapshots[{index}].{key}")
        if item["provider_symbol"] is not None:
            _nonempty_string(item["provider_symbol"], f"snapshots[{index}].provider_symbol")
        requested_start = _date_value(
            item["requested_start"], f"snapshots[{index}].requested_start",
        )
        requested_end = _date_value(
            item["requested_end"], f"snapshots[{index}].requested_end",
        )
        if requested_start > requested_end:
            raise ValueError(f"snapshots[{index}] requested_start exceeds requested_end")
        _aware_datetime(item["retrieved_at"], f"snapshots[{index}].retrieved_at")
        _sha256_value(
            item["source_snapshot_hash"], f"snapshots[{index}].source_snapshot_hash",
        )
        if item["price_basis"] not in {"raw", "adjusted", "both"}:
            raise ValueError(f"snapshots[{index}].price_basis is unsupported")
        if item["coverage_status"] not in {"complete", "partial", "unchecked"}:
            raise ValueError(f"snapshots[{index}].coverage_status is unsupported")
        if not isinstance(item["metadata"], dict):
            raise ValueError(f"snapshots[{index}].metadata must be an object")
        if not isinstance(item["raw_evidence_hashes"], list) or not item["raw_evidence_hashes"]:
            raise ValueError(f"snapshots[{index}].raw_evidence_hashes must be an array")
        for raw_index, raw_hash in enumerate(item["raw_evidence_hashes"]):
            _sha256_value(
                raw_hash, f"snapshots[{index}].raw_evidence_hashes[{raw_index}]",
            )
        if len(set(item["raw_evidence_hashes"])) != len(item["raw_evidence_hashes"]):
            raise ValueError(f"snapshots[{index}].raw_evidence_hashes contains duplicates")
        if not isinstance(item["coverage_issues"], list):
            raise ValueError(f"snapshots[{index}].coverage_issues must be an array")
        for issue_index, raw_issue in enumerate(item["coverage_issues"]):
            issue = require_object(
                raw_issue,
                source=f"snapshots[{index}].coverage_issues[{issue_index}]",
                required={"type", "date", "detail"},
            )
            _nonempty_string(
                issue["type"], f"snapshots[{index}].coverage_issues[{issue_index}].type",
            )
            if issue["date"] is not None:
                _date_value(
                    issue["date"],
                    f"snapshots[{index}].coverage_issues[{issue_index}].date",
                )
            if not isinstance(issue["detail"], str):
                raise ValueError(
                    f"snapshots[{index}].coverage_issues[{issue_index}].detail must be a string"
                )
        _nonempty_string(artifact["path"], f"snapshots[{index}].artifact.path")
        _nonnegative_integer(
            artifact["size_bytes"], f"snapshots[{index}].artifact.size_bytes",
        )
        _sha256_value(
            artifact["file_sha256"], f"snapshots[{index}].artifact.file_sha256",
        )
        _nonempty_string(
            artifact["parquet_schema_version"],
            f"snapshots[{index}].artifact.parquet_schema_version",
        )
        _nonnegative_integer(
            artifact["row_count"], f"snapshots[{index}].artifact.row_count",
        )
    raw_ids: set[str] = set()
    for index, raw in enumerate(manifest["raw_snapshots"]):
        required = {
            "snapshot_hash", "path", "size_bytes", "file_sha256",
        }
        if manifest["schema_version"] == BUNDLE_SCHEMA_VERSION:
            required.add("acquisitions")
        else:
            required.update({"provider", "resource", "retrieved_at"})
        item = require_object(
            raw,
            source=f"raw_snapshots[{index}]",
            required=required,
        )
        if item["snapshot_hash"] in raw_ids:
            raise ValueError(f"duplicate raw snapshot: {item['snapshot_hash']}")
        _sha256_value(item["snapshot_hash"], f"raw_snapshots[{index}].snapshot_hash")
        _nonempty_string(item["path"], f"raw_snapshots[{index}].path")
        if manifest["schema_version"] == BUNDLE_SCHEMA_VERSION:
            if not isinstance(item["acquisitions"], list) or not item["acquisitions"]:
                raise ValueError(f"raw_snapshots[{index}].acquisitions must be a non-empty array")
            for acquisition_index, acquisition_value in enumerate(item["acquisitions"]):
                acquisition = require_object(
                    acquisition_value,
                    source=f"raw_snapshots[{index}].acquisitions[{acquisition_index}]",
                    required={"acquisition_id", "provider", "resource", "retrieved_at"},
                )
                _sha256_value(
                    acquisition["acquisition_id"],
                    f"raw_snapshots[{index}].acquisitions[{acquisition_index}].acquisition_id",
                )
                for key in ("provider", "resource"):
                    _nonempty_string(
                        acquisition[key],
                        f"raw_snapshots[{index}].acquisitions[{acquisition_index}].{key}",
                    )
                _aware_datetime(
                    acquisition["retrieved_at"],
                    f"raw_snapshots[{index}].acquisitions[{acquisition_index}].retrieved_at",
                )
                expected_acquisition_id = raw_acquisition_id(
                    item["snapshot_hash"],
                    acquisition["provider"],
                    acquisition["resource"],
                    datetime.fromisoformat(acquisition["retrieved_at"]).astimezone(
                        timezone.utc
                    ).isoformat(),
                )
                if acquisition["acquisition_id"] != expected_acquisition_id:
                    raise ValueError(
                        f"raw_snapshots[{index}].acquisitions[{acquisition_index}] "
                        "identity does not match its provenance"
                    )
        else:
            for key in ("provider", "resource"):
                _nonempty_string(item[key], f"raw_snapshots[{index}].{key}")
            _aware_datetime(item["retrieved_at"], f"raw_snapshots[{index}].retrieved_at")
            item["acquisitions"] = [
                {
                    "acquisition_id": raw_acquisition_id(
                        item["snapshot_hash"], item["provider"], item["resource"],
                        datetime.fromisoformat(item["retrieved_at"]).astimezone(
                            timezone.utc
                        ).isoformat(),
                    ),
                    "provider": item["provider"],
                    "resource": item["resource"],
                    "retrieved_at": datetime.fromisoformat(item["retrieved_at"]).astimezone(
                        timezone.utc
                    ).isoformat(),
                }
            ]
        _nonnegative_integer(item["size_bytes"], f"raw_snapshots[{index}].size_bytes")
        _sha256_value(item["file_sha256"], f"raw_snapshots[{index}].file_sha256")
        raw_ids.add(item["snapshot_hash"])
    return manifest

def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _sha256_value(value: Any, field: str) -> str:
    text = _nonempty_string(value, field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field} must be a lowercase SHA-256 hash")
    return text


def _date_value(value: Any, field: str) -> date:
    text = _nonempty_string(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def _aware_datetime(value: Any, field: str) -> datetime:
    text = _nonempty_string(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _nonnegative_integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value
