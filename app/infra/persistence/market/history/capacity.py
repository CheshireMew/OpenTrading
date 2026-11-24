from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import shutil
from typing import Any, Iterable

from app.infra.persistence.market.history.artifacts import artifact_json
from app.infra.persistence.market.history.filesystem_inventory import (
    StorageInventory,
    file_storage_metadata,
    filesystem_allocated_bytes as filesystem_allocated_bytes,
    managed_object_identity as managed_object_identity,
    registered_roots_inventory,
    unique_registered_paths,
    within_registered_roots,
)
from app.infra.structured_data import load_json_file


OPERATION_MANIFEST = "_operation.json"
ROOTS_MANIFEST = "_storage_roots.json"
ROOTS_SCHEMA_VERSION = "signal-lab.storage-roots.v1"
OPERATION_SCHEMA_VERSION = "signal-lab.storage-operation.v2"
ARTIFACT_CLASSES = {"truth", "deliverable", "cache", "temporary", "evidence"}


class StorageCapacityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoragePreflight:
    producer: str
    root: str
    registered_roots: tuple[str, ...]
    estimated_peak_bytes: int
    current_managed_bytes: int
    current_logical_bytes: int
    current_unique_object_bytes: int
    current_object_count: int
    maximum_managed_bytes: int
    free_bytes: int
    minimum_free_bytes: int
    projected_managed_bytes: int
    projected_free_bytes: int
    identity_algorithm: str
    allocation_algorithm: str
    checked_at: str


class ManagedStorage:
    """Blocking preflight and report-only ownership inventory for runtime artifacts."""

    def __init__(
        self,
        root: Path,
        *,
        maximum_managed_bytes: int,
        minimum_free_bytes: int,
        additional_roots: Iterable[Path] = (),
    ) -> None:
        self.root = root.expanduser().resolve()
        if maximum_managed_bytes < 1 or minimum_free_bytes < 1:
            raise ValueError("storage budgets must be positive")
        self.maximum_managed_bytes = maximum_managed_bytes
        self.minimum_free_bytes = minimum_free_bytes
        self._additional_roots = tuple(path.expanduser().resolve() for path in additional_roots)

    def registered_roots(self) -> tuple[Path, ...]:
        roots = [self.root]
        roots.extend(Path(item["path"]) for item in self.registered_root_entries())
        roots.extend(self._additional_roots)
        return unique_registered_paths(roots)

    def registered_root_entries(self) -> list[dict[str, Any]]:
        path = self.root / ROOTS_MANIFEST
        if not path.is_file():
            return []
        payload = load_json_file(path)
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != ROOTS_SCHEMA_VERSION
            or payload.get("owner") != "signal-lab"
            or not isinstance(payload.get("roots"), list)
        ):
            raise StorageCapacityError(f"invalid managed storage root registry: {path}")
        entries: list[dict[str, Any]] = []
        for index, item in enumerate(payload["roots"]):
            if not isinstance(item, dict):
                raise StorageCapacityError(f"invalid managed storage root entry {index}: {path}")
            try:
                root = Path(str(item["path"])).expanduser().resolve()
            except (KeyError, OSError, RuntimeError, ValueError) as exc:
                raise StorageCapacityError(f"invalid managed storage root entry {index}: {path}") from exc
            if item.get("status") not in {"active", "retired"}:
                raise StorageCapacityError(f"invalid managed storage root status at entry {index}: {path}")
            entries.append({**item, "path": str(root)})
        return entries

    def register_root(
        self,
        path: Path,
        *,
        producer: str,
        operation_id: str,
        status: str = "active",
    ) -> Path:
        candidate = path.expanduser().resolve()
        if status not in {"active", "retired"}:
            raise ValueError(f"invalid managed root status: {status}")
        if candidate == Path(candidate.anchor):
            raise ValueError(f"a drive root cannot be registered as a managed artifact root: {candidate}")
        if candidate == self.root:
            return self.root / ROOTS_MANIFEST
        registry_path = self.root / ROOTS_MANIFEST
        self.root.mkdir(parents=True, exist_ok=True)
        with _storage_registry_lock(self.root):
            entries = self.registered_root_entries()
            now = datetime.now(timezone.utc).isoformat()
            selected = {
                "path": str(candidate),
                "producer": producer,
                "operation_id": operation_id,
                "status": status,
                "registered_at": now,
                "updated_at": now,
            }
            replaced = False
            for index, item in enumerate(entries):
                if Path(item["path"]) == candidate:
                    selected["registered_at"] = item.get("registered_at", now)
                    entries[index] = selected
                    replaced = True
                    break
            if not replaced:
                entries.append(selected)
            entries.sort(key=lambda item: item["path"].casefold())
            return artifact_json(
                registry_path,
                {
                    "schema_version": ROOTS_SCHEMA_VERSION,
                    "owner": "signal-lab",
                    "roots": entries,
                    "updated_at": now,
                },
            )

    def preflight(self, producer: str, *, estimated_peak_bytes: int | None) -> StoragePreflight:
        inventory = registered_roots_inventory(self.registered_roots())
        if inventory.unknown_paths:
            sample = "; ".join(inventory.unknown_paths[:3])
            raise StorageCapacityError(
                f"{producer} cannot start because allocated storage or object identity is unknown: {sample}"
            )
        return preflight_capacity(
            producer,
            capacity_path=self._capacity_path(),
            current_managed_bytes=inventory.filesystem_allocated_bytes,
            current_logical_bytes=inventory.logical_bytes,
            current_unique_object_bytes=inventory.managed_unique_object_bytes,
            current_object_count=inventory.object_count,
            registered_roots=inventory.registered_roots,
            identity_algorithm=inventory.identity_algorithm,
            allocation_algorithm=inventory.allocation_algorithm,
            estimated_peak_bytes=estimated_peak_bytes,
            maximum_managed_bytes=self.maximum_managed_bytes,
            minimum_free_bytes=self.minimum_free_bytes,
        )

    def operation_directory(self, producer: str, operation_id: str) -> Path:
        for label, value in (("producer", producer), ("operation_id", operation_id)):
            if (
                not value
                or value in {".", ".."}
                or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in value)
            ):
                raise ValueError(f"storage {label} must be a lowercase path-safe identifier")
        directory_id = (
            operation_id
            if len(operation_id) <= 40
            else sha256(operation_id.encode("utf-8")).hexdigest()[:32]
        )
        return self.root / ".operations" / producer / directory_id

    def begin_operation(
        self,
        directory: Path,
        *,
        operation_id: str,
        producer: str,
        preflight: StoragePreflight,
    ) -> Path:
        controlled = self._controlled(directory)
        controlled.mkdir(parents=True, exist_ok=True)
        existing_path = controlled / OPERATION_MANIFEST
        if existing_path.is_file():
            existing = load_json_file(existing_path)
            if (
                not isinstance(existing, dict)
                or existing.get("operation_id") != operation_id
                or existing.get("producer") != producer
                or existing.get("owner") != "signal-lab"
            ):
                raise RuntimeError(f"storage operation identity collision: {controlled}")
            return existing_path
        initial = registered_roots_inventory((controlled,))
        now = datetime.now(timezone.utc).isoformat()
        manifest = {
            "schema_version": OPERATION_SCHEMA_VERSION,
            "operation_id": operation_id,
            "producer": producer,
            "owner": "signal-lab",
            "status": "staging",
            "preflight": asdict(preflight),
            "inventory": [],
            "inventory_by_class": {},
            "new_objects": [],
            "reused_objects": [],
            "residuals": [],
            "terminal_storage": initial.summary(),
            "cleanup_policy": "report-only",
            "created_at": now,
            "updated_at": now,
        }
        return artifact_json(existing_path, manifest)

    def finish_operation(
        self,
        directory: Path,
        *,
        status: str,
        inventory: list[dict[str, Any]],
        error: str | None = None,
    ) -> Path:
        if status not in {"artifacts_ready", "published", "failed", "interrupted"}:
            raise ValueError(f"invalid storage operation status: {status}")
        controlled = self._controlled(directory)
        path = controlled / OPERATION_MANIFEST
        payload = load_json_file(path)
        if not isinstance(payload, dict) or payload.get("owner") != "signal-lab":
            raise ValueError(f"invalid storage operation manifest: {path}")
        evidence = operation_storage_evidence(
            controlled,
            inventory,
            previous_status=str(payload.get("status", "unknown")),
            status=status,
            previous_inventory=(
                payload["inventory"] if isinstance(payload.get("inventory"), list) else []
            ),
            registered_roots=self.registered_roots(),
        )
        payload["schema_version"] = OPERATION_SCHEMA_VERSION
        payload["status"] = status
        payload.update(evidence)
        payload["error"] = error
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        return artifact_json(path, payload)

    def finish_failure(
        self,
        directory: Path,
        *,
        error: BaseException,
        inventory: list[dict[str, Any]],
    ) -> Path:
        return self.finish_operation(
            directory,
            status=(
                "interrupted"
                if isinstance(error, (KeyboardInterrupt, SystemExit))
                else "failed"
            ),
            inventory=inventory,
            error=f"{type(error).__name__}: {error}",
        )

    def try_finish_failure(
        self,
        directory: Path,
        *,
        error: BaseException,
        inventory: list[dict[str, Any]],
    ) -> bool:
        try:
            self.finish_failure(directory, error=error, inventory=inventory)
        except (OSError, ValueError, RuntimeError):
            return False
        return True

    def status(self) -> dict[str, Any]:
        roots = self.registered_roots()
        storage = registered_roots_inventory(roots)
        capacity_root = _existing_parent(self._capacity_path())
        free_bytes = shutil.disk_usage(capacity_root).free
        operations: list[dict[str, Any]] = []
        manifest_directories: set[Path] = set()
        manifest_paths: set[Path] = set()
        for root in roots:
            if not root.is_dir():
                continue
            try:
                for path in root.rglob(OPERATION_MANIFEST):
                    resolved_path = path.resolve()
                    if resolved_path in manifest_paths or not path.is_file():
                        continue
                    manifest_paths.add(resolved_path)
                    directory = path.parent.resolve()
                    manifest_directories.add(directory)
                    operations.append(self._operation_status(path, directory, storage))
            except OSError as exc:
                operations.append(
                    {
                        "operation_id": None,
                        "producer": None,
                        "status": "unknown",
                        "directory": str(root),
                        "error": str(exc),
                        "cleanup_candidate": False,
                    }
                )
        unresolved = []
        for staging_root in self._staging_roots():
            if not staging_root.is_dir():
                continue
            for child in staging_root.iterdir():
                if child.is_dir() and child.resolve() not in manifest_directories:
                    unresolved.append(str(child.resolve()))
        registered_entries = self.registered_root_entries()
        unresolved_registered_roots = [
            item["path"]
            for item in registered_entries
            if item["status"] == "active" and not Path(item["path"]).exists()
        ]
        cleanup_candidates = [
            item for item in operations if item.get("cleanup_candidate") is True
        ]
        return {
            "root": str(self.root),
            "registered_roots": list(storage.registered_roots),
            "managed_bytes": storage.filesystem_allocated_bytes,
            "logical_bytes": storage.logical_bytes,
            "filesystem_allocated_bytes": storage.filesystem_allocated_bytes,
            "managed_unique_object_bytes": storage.managed_unique_object_bytes,
            "managed_object_count": storage.object_count,
            "managed_path_count": storage.path_count,
            "identity_algorithm": storage.identity_algorithm,
            "allocation_algorithm": storage.allocation_algorithm,
            "inventory_unknown_paths": list(storage.unknown_paths),
            "maximum_managed_bytes": self.maximum_managed_bytes,
            "free_bytes": free_bytes,
            "minimum_free_bytes": self.minimum_free_bytes,
            "operations": operations,
            "cleanup_candidates": cleanup_candidates,
            "unresolved_staging": unresolved,
            "unresolved_registered_roots": unresolved_registered_roots,
            "cleanup_policy": "report-only",
            "reclaimable_bytes": {
                "lower_bound": 0,
                "upper_bound": sum(
                    int(item.get("filesystem_allocated_bytes", 0)) for item in cleanup_candidates
                ),
                "status": "unknown-without-complete-link-and-reflink-closure",
            },
        }

    def _operation_status(
        self,
        path: Path,
        directory: Path,
        storage: StorageInventory,
    ) -> dict[str, Any]:
        try:
            payload = load_json_file(path)
            if not isinstance(payload, dict) or payload.get("owner") != "signal-lab":
                raise ValueError("manifest has no Signal Lab owner")
            terminal_paths = [
                item for item in storage.paths
                if within_registered_roots(Path(item.path), (directory,))
            ]
            unique_objects = {item.identity: item for item in terminal_paths}
            directory_prefix = os.path.normcase(str(directory) + os.sep)
            terminal_unknown = [
                item for item in storage.unknown_paths
                if os.path.normcase(item).startswith(directory_prefix)
                or os.path.normcase(item).startswith(os.path.normcase(str(directory) + ":"))
            ]
            status = payload.get("status")
            return {
                "operation_id": payload.get("operation_id"),
                "producer": payload.get("producer"),
                "status": status,
                "directory": str(directory),
                "updated_at": payload.get("updated_at"),
                "logical_bytes": sum(item.logical_bytes for item in terminal_paths),
                "filesystem_allocated_bytes": sum(
                    item.allocated_bytes for item in unique_objects.values()
                ),
                "managed_unique_object_bytes": sum(
                    item.logical_bytes for item in unique_objects.values()
                ),
                "object_count": len(unique_objects),
                "unknown_paths": terminal_unknown,
                "residuals": payload.get("residuals", []),
                "cleanup_candidate": status in {"failed", "interrupted"},
            }
        except (OSError, ValueError) as exc:
            return {
                "operation_id": None,
                "producer": None,
                "status": "unknown",
                "directory": str(directory),
                "error": str(exc),
                "cleanup_candidate": False,
            }

    def _capacity_path(self) -> Path:
        for candidate in reversed(self._additional_roots):
            if candidate != self.root:
                return candidate
        return self.root

    def _staging_roots(self) -> tuple[Path, ...]:
        return (
            self.root / ".operations",
            self.root / "runs" / ".staging",
            self.root / "datasets" / ".staging",
            self.root / "exports" / "datasets" / "prices" / ".staging",
            self.root / "bundles" / ".staging",
        )

    def _controlled(self, path: Path) -> Path:
        resolved = path.expanduser().resolve()
        if not within_registered_roots(resolved, self.registered_roots()):
            raise ValueError(f"managed artifact path escapes every registered runtime root: {resolved}")
        return resolved


def operation_storage_evidence(
    directory: Path,
    inventory: list[dict[str, Any]],
    *,
    previous_status: str,
    status: str,
    previous_inventory: list[dict[str, Any]] | None = None,
    registered_roots: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Build terminal physical and declared-object evidence for an operation manifest."""

    controlled = directory.expanduser().resolve()
    terminal = registered_roots_inventory((controlled,))
    declared = _declared_inventory_summary(
        controlled,
        inventory,
        registered_roots=tuple(registered_roots) if registered_roots is not None else (controlled,),
    )
    normalized_inventory = [
        {
            **item,
            "path": evidence["path"],
            "size_bytes": evidence["logical_bytes"],
            "filesystem_allocated_bytes": evidence["filesystem_allocated_bytes"],
            "managed_object_identity": evidence["managed_object_identity"],
            "link_count": evidence["link_count"],
        }
        for item, evidence in zip(inventory, declared["objects"], strict=True)
    ]
    previous_by_path = {
        str(item.get("path")): item
        for item in (previous_inventory or [])
        if isinstance(item, dict) and item.get("path")
    }
    reused: list[str] = []
    new: list[str] = []
    for item in normalized_inventory:
        previous = previous_by_path.get(str(item["path"]))
        if (
            previous_status == "published"
            and previous is not None
            and previous.get("managed_object_identity")
            == item.get("managed_object_identity")
        ):
            reused.append(str(item["path"]))
        else:
            new.append(str(item["path"]))
    residuals: list[str] = []
    if status in {"failed", "interrupted"}:
        residuals = [item.path for item in terminal.objects]
        residuals.extend(
            item["path"] for item in declared["objects"] if item.get("exists") is True
        )
        residuals = list(dict.fromkeys(residuals))
    return {
        "inventory": normalized_inventory,
        "inventory_by_class": declared["bytes_by_class"],
        "declared_inventory_bytes": declared["logical_bytes"],
        "new_objects": new,
        "reused_objects": reused,
        "residuals": residuals,
        "terminal_storage": terminal.summary(),
    }


def preflight_capacity(
    producer: str,
    *,
    capacity_path: Path,
    current_managed_bytes: int,
    estimated_peak_bytes: int | None,
    maximum_managed_bytes: int,
    minimum_free_bytes: int,
    registered_roots: tuple[str, ...] = (),
    current_logical_bytes: int | None = None,
    current_unique_object_bytes: int | None = None,
    current_object_count: int = 0,
    identity_algorithm: str = "caller-supplied",
    allocation_algorithm: str = "caller-supplied",
) -> StoragePreflight:
    if estimated_peak_bytes is None or estimated_peak_bytes < 0:
        raise StorageCapacityError(f"{producer} cannot start because its peak byte estimate is unknown")
    if current_managed_bytes < 0:
        raise ValueError("current managed bytes cannot be negative")
    capacity_root = _existing_parent(capacity_path.expanduser().resolve())
    free = shutil.disk_usage(capacity_root).free
    projected_managed = current_managed_bytes + estimated_peak_bytes
    projected_free = free - estimated_peak_bytes
    result = StoragePreflight(
        producer=producer,
        root=str(capacity_path.expanduser().resolve()),
        registered_roots=registered_roots,
        estimated_peak_bytes=estimated_peak_bytes,
        current_managed_bytes=current_managed_bytes,
        current_logical_bytes=(
            current_managed_bytes if current_logical_bytes is None else current_logical_bytes
        ),
        current_unique_object_bytes=(
            current_managed_bytes
            if current_unique_object_bytes is None
            else current_unique_object_bytes
        ),
        current_object_count=current_object_count,
        maximum_managed_bytes=maximum_managed_bytes,
        free_bytes=free,
        minimum_free_bytes=minimum_free_bytes,
        projected_managed_bytes=projected_managed,
        projected_free_bytes=projected_free,
        identity_algorithm=identity_algorithm,
        allocation_algorithm=allocation_algorithm,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
    failures = []
    if projected_managed > maximum_managed_bytes:
        failures.append(
            f"allocated usage would reach {projected_managed} bytes, above {maximum_managed_bytes}"
        )
    if projected_free < minimum_free_bytes:
        failures.append(
            f"free space would fall to {projected_free} bytes, below {minimum_free_bytes}"
        )
    if failures:
        raise StorageCapacityError(f"{producer} storage preflight blocked: {'; '.join(failures)}")
    return result


def _declared_inventory_summary(
    directory: Path,
    inventory: list[dict[str, Any]],
    *,
    registered_roots: tuple[Path, ...],
) -> dict[str, Any]:
    by_class: dict[str, int] = {}
    objects: list[dict[str, Any]] = []
    for item in inventory:
        artifact_class = str(item.get("class", "evidence"))
        if artifact_class not in ARTIFACT_CLASSES:
            raise ValueError(f"unsupported storage artifact class: {artifact_class}")
        raw_path = item.get("path")
        path: Path | None = None
        if isinstance(raw_path, str) and raw_path:
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = directory / candidate
            candidate = candidate.resolve()
            if not within_registered_roots(candidate, registered_roots):
                raise ValueError(f"declared storage inventory path escapes registered roots: {candidate}")
            path = candidate
        size = item.get("size_bytes")
        if not isinstance(size, int) or size < 0:
            size = path.stat().st_size if path is not None and path.is_file() else 0
        identity: str | None = None
        allocated: int | None = None
        links: int | None = None
        if path is not None and path.is_file():
            identity, actual_size, allocated, links = file_storage_metadata(path)
            if size != actual_size:
                raise ValueError(f"declared storage inventory size mismatch: {path}")
        by_class[artifact_class] = by_class.get(artifact_class, 0) + size
        objects.append(
            {
                "class": artifact_class,
                "path": str(path) if path is not None else str(raw_path or ""),
                "logical_bytes": size,
                "filesystem_allocated_bytes": allocated,
                "managed_object_identity": identity,
                "link_count": links,
                "exists": path.is_file() if path is not None else False,
            }
        )
    return {
        "bytes_by_class": dict(sorted(by_class.items())),
        "logical_bytes": sum(by_class.values()),
        "objects": objects,
    }


@contextmanager
def _storage_registry_lock(root: Path):
    lock_path = root / ".storage-roots.lock"
    with lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise StorageCapacityError(f"no existing capacity root for {path}")
        candidate = parent
    return candidate
