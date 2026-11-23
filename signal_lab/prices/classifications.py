from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from signal_lab.config import SignalLabConfig
from signal_lab.data.snapshots import RawSnapshotStore
from signal_lab.prices.contracts import content_hash, load_json_document, require_object
from signal_lab.storage.catalog_repository import CatalogRepository
from signal_lab.storage.database import SignalLabDatabase
from signal_lab.storage.classification_repository import ClassificationRepository


CLASSIFICATION_SCHEMA_VERSION = "signal-lab.classification.v1"


class ClassificationService:
    """Point-in-time classification import and query boundary."""

    def __init__(self, root: Path, config: SignalLabConfig) -> None:
        self.root = root.expanduser().resolve()
        self.config = config
        database = SignalLabDatabase(self.root)
        self._catalog = CatalogRepository(database)
        self._repository = ClassificationRepository(database)

    def import_file(self, path: Path) -> dict[str, Any]:
        payload = _validate_classification_document(load_json_document(path))
        scheme = payload["scheme"]
        unknown_instruments = sorted({
            item["canonical_code"]
            for item in payload["memberships"]
            if self._catalog.get_instrument(item["canonical_code"]) is None
        })
        if unknown_instruments:
            raise ValueError(
                "classification memberships reference unknown instruments: "
                + ", ".join(unknown_instruments)
            )
        retrieved_at = datetime.fromisoformat(scheme["retrieved_at"])
        if retrieved_at.tzinfo is None:
            raise ValueError("classification scheme retrieved_at must be timezone-aware")
        normalized_scheme = {
            **scheme,
            "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat(),
        }
        source = RawSnapshotStore(self.root, self.config).save(
            scheme["provider"],
            f"classifications-{scheme['scheme_id']}-{scheme['version']}",
            payload,
            retrieved_at,
        )
        snapshot_hash = content_hash(
            {
                "schema_version": payload["schema_version"],
                "scheme": normalized_scheme,
                "classifications": payload["classifications"],
                "memberships": payload["memberships"],
                "metadata": payload.get("metadata", {}),
            }
        )
        self._repository.save_classification_snapshot(
            snapshot_hash=snapshot_hash,
            scheme=normalized_scheme,
            source_snapshot_hash=source.snapshot_hash,
            classifications=payload["classifications"],
            memberships=payload["memberships"],
            metadata=payload.get("metadata", {}),
        )
        return {
            "status": "ok",
            "schema_version": CLASSIFICATION_SCHEMA_VERSION,
            "classification_snapshot_hash": snapshot_hash,
            "source_snapshot_hash": source.snapshot_hash,
            "scheme_id": scheme["scheme_id"],
            "scheme_version": scheme["version"],
            "classification_count": len(payload["classifications"]),
            "membership_count": len(payload["memberships"]),
        }

    def memberships(
        self,
        canonical_code: str,
        *,
        as_of: date,
        scheme_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._repository.classification_memberships(
            canonical_code, as_of=as_of, scheme_id=scheme_id,
        )


def _validate_classification_document(value: Any) -> dict[str, Any]:
    payload = require_object(
        value,
        source="classification document",
        required={"schema_version", "scheme", "classifications", "memberships"},
        optional={"metadata"},
    )
    if payload["schema_version"] != CLASSIFICATION_SCHEMA_VERSION:
        raise ValueError(f"unsupported classification schema: {payload['schema_version']}")
    scheme = require_object(
        payload["scheme"],
        source="classification scheme",
        required={"scheme_id", "name", "version", "provider", "retrieved_at"},
        optional={"metadata"},
    )
    for key in ("scheme_id", "name", "version", "provider", "retrieved_at"):
        if not isinstance(scheme[key], str) or not scheme[key].strip():
            raise ValueError(f"classification scheme {key} must be a non-empty string")
    if not isinstance(payload["classifications"], list) or not payload["classifications"]:
        raise ValueError("classification document requires at least one classification")
    nodes: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(payload["classifications"]):
        item = require_object(
            raw,
            source=f"classifications[{index}]",
            required={"classification_id", "name", "parent_id"},
            optional={"metadata"},
        )
        classification_id = item["classification_id"]
        if not isinstance(classification_id, str) or not classification_id.strip():
            raise ValueError(f"classifications[{index}].classification_id must be non-empty")
        if classification_id in ids:
            raise ValueError(f"duplicate classification_id: {classification_id}")
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise ValueError(f"classifications[{index}].name must be non-empty")
        if item["parent_id"] is not None and not isinstance(item["parent_id"], str):
            raise ValueError(f"classifications[{index}].parent_id must be a string or null")
        ids.add(classification_id)
        nodes.append(item)
    for item in nodes:
        parent = item["parent_id"]
        if parent is not None and parent not in ids:
            raise ValueError(f"unknown parent classification: {parent}")
        if parent == item["classification_id"]:
            raise ValueError(f"classification cannot be its own parent: {parent}")
    _reject_classification_cycles(nodes)
    if not isinstance(payload["memberships"], list):
        raise ValueError("classification memberships must be an array")
    memberships: list[dict[str, Any]] = []
    intervals: dict[tuple[str, str], list[tuple[date, date | None]]] = {}
    for index, raw in enumerate(payload["memberships"]):
        item = require_object(
            raw,
            source=f"memberships[{index}]",
            required={"classification_id", "canonical_code", "valid_from", "valid_to"},
            optional={"metadata"},
        )
        if item["classification_id"] not in ids:
            raise ValueError(f"membership references unknown classification: {item['classification_id']}")
        if not isinstance(item["canonical_code"], str) or not item["canonical_code"].strip():
            raise ValueError(f"memberships[{index}].canonical_code must be non-empty")
        start = date.fromisoformat(item["valid_from"])
        end = date.fromisoformat(item["valid_to"]) if item["valid_to"] is not None else None
        if end is not None and end < start:
            raise ValueError(f"memberships[{index}] valid_to precedes valid_from")
        interval_key = (item["classification_id"], item["canonical_code"])
        for existing_start, existing_end in intervals.setdefault(interval_key, []):
            if _intervals_overlap(start, end, existing_start, existing_end):
                raise ValueError(
                    "overlapping classification membership interval: "
                    f"{item['classification_id']} {item['canonical_code']}"
                )
        intervals[interval_key].append((start, end))
        memberships.append(item)
    payload["classifications"] = nodes
    payload["memberships"] = memberships
    return payload


def _reject_classification_cycles(nodes: list[dict[str, Any]]) -> None:
    parents = {item["classification_id"]: item["parent_id"] for item in nodes}
    for start in parents:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                raise ValueError(f"classification hierarchy contains a cycle at {current}")
            seen.add(current)
            current = parents[current]


def _intervals_overlap(
    first_start: date,
    first_end: date | None,
    second_start: date,
    second_end: date | None,
) -> bool:
    return (first_end is None or second_start <= first_end) and (
        second_end is None or first_start <= second_end
    )
