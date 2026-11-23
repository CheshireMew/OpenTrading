from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
from hashlib import sha256
from pathlib import Path
from typing import Any

from config.market_data import MarketDataConfig
from app.infra.persistence.market.history import MarketHistoryDatabase, artifact_json
from app.infra.persistence.market.history.artifacts import storage_item
from app.infra.persistence.market.history.capacity import ManagedStorage
from app.infra.persistence.market.history.raw_snapshots import RawSnapshotRepository
from app.infra.structured_data import JsonBudget, canonical_json_bytes, load_gzip_json_file


RAW_JSON_BUDGET = JsonBudget(
    max_bytes=64 * 1024 * 1024,
    max_depth=32,
    max_nodes=2_000_000,
    max_string_chars=1_000_000,
)


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    snapshot_hash: str
    acquisition_id: str
    provider: str
    resource: str
    retrieved_at: datetime
    path: Path


class RawSnapshotStore:
    def __init__(self, root: Path, config: MarketDataConfig) -> None:
        self.base = root.expanduser().resolve()
        self.config = config
        self.root = self.base / "raw"
        self._repository = RawSnapshotRepository(MarketHistoryDatabase(self.base))

    def save(self, provider: str, resource: str, payload: Any, retrieved_at: datetime) -> RawSnapshot:
        if retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if not provider or len(provider) > 256 or any(ord(character) < 32 for character in provider):
            raise ValueError("provider must be a non-empty metadata label of at most 256 characters")
        if not resource or len(resource) > 1024 or any(ord(character) < 32 for character in resource):
            raise ValueError("resource must be a non-empty metadata label of at most 1024 characters")
        canonical = canonical_json_bytes(payload)
        if len(canonical) > RAW_JSON_BUDGET.max_bytes:
            raise ValueError(f"raw snapshot exceeds {RAW_JSON_BUDGET.max_bytes} bytes")
        snapshot_hash = sha256(canonical).hexdigest()
        existing = self._repository.record(snapshot_hash)
        path = (
            Path(existing["path"])
            if existing is not None and Path(existing["path"]).is_file()
            else self.root / "objects" / snapshot_hash[:2] / f"{snapshot_hash}.json.gz"
        )
        try:
            path.resolve().relative_to(self.root.resolve())
        except ValueError as exc:
            raise ValueError(f"raw snapshot target escapes its managed root: {path}") from exc
        normalized_retrieved_at = retrieved_at.astimezone(timezone.utc)
        storage = self._managed_storage()
        if not path.exists():
            preflight = storage.preflight(
                "raw-snapshot",
                estimated_peak_bytes=max(1024 * 1024, len(canonical) * 2 + 4096),
            )
            operation = storage.operation_directory("raw-snapshot", snapshot_hash)
            storage.begin_operation(
                operation,
                operation_id=snapshot_hash,
                producer="raw-snapshot",
                preflight=preflight,
            )
            temporary = operation / "snapshot.json.gz.tmp"
            metadata_path = path.with_suffix(".meta.json")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with temporary.open("wb") as raw:
                    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                        compressed.write(canonical)
                temporary.replace(path)
                artifact_json(
                    metadata_path,
                    {
                        "snapshot_hash": snapshot_hash,
                        "content_bytes": len(canonical),
                    },
                )
                storage.finish_operation(
                    operation,
                    status="artifacts_ready",
                    inventory=[
                        storage_item(path, "truth"),
                        storage_item(metadata_path, "evidence"),
                    ],
                )
                acquisition_id = self._repository.register(
                    snapshot_hash=snapshot_hash,
                    provider=provider,
                    resource=resource,
                    retrieved_at=normalized_retrieved_at,
                    path=path,
                )
                storage.finish_operation(
                    operation,
                    status="published",
                    inventory=[
                        storage_item(path, "truth"),
                        storage_item(metadata_path, "evidence"),
                    ],
                )
            except BaseException as exc:
                inventory = [
                    storage_item(candidate, artifact_class)
                    for candidate, artifact_class in (
                        (temporary, "temporary"),
                        (path, "truth"),
                        (metadata_path, "evidence"),
                    )
                    if candidate.is_file()
                ]
                storage.finish_failure(
                    operation,
                    error=exc,
                    inventory=inventory,
                )
                raise
        else:
            acquisition_id = self._repository.register(
                snapshot_hash=snapshot_hash,
                provider=provider,
                resource=resource,
                retrieved_at=normalized_retrieved_at,
                path=path,
            )
            operation = storage.operation_directory("raw-snapshot", snapshot_hash)
            if (operation / "_operation.json").is_file():
                storage.finish_operation(
                    operation,
                    status="published",
                    inventory=[
                        storage_item(path, "truth"),
                        storage_item(path.with_suffix(".meta.json"), "evidence"),
                    ],
                )
        return RawSnapshot(
            snapshot_hash,
            acquisition_id,
            provider,
            resource,
            normalized_retrieved_at,
            path,
        )

    def _managed_storage(self) -> ManagedStorage:
        return ManagedStorage(
            self.base,
            maximum_managed_bytes=self.config.max_managed_bytes,
            minimum_free_bytes=self.config.min_free_bytes,
        )

    @staticmethod
    def load(snapshot: RawSnapshot) -> Any:
        payload = load_gzip_json_file(snapshot.path, budget=RAW_JSON_BUDGET)
        canonical = canonical_json_bytes(payload)
        if sha256(canonical).hexdigest() != snapshot.snapshot_hash:
            raise ValueError(f"raw snapshot hash mismatch: {snapshot.path}")
        return payload
