from __future__ import annotations

from signal_lab.prices.models import PriceSnapshot
from signal_lab.storage.price_repository import PriceRepository


def snapshot_closure(
    prices: PriceRepository,
    selected: list[PriceSnapshot],
) -> list[PriceSnapshot]:
    snapshots = {item.snapshot_hash: item for item in selected}
    pending = list(selected)
    while pending:
        current = pending.pop()
        for dependency_hash in lineage_snapshot_hashes(current):
            if dependency_hash in snapshots:
                continue
            matches = prices.list_price_snapshots(snapshot_hashes=[dependency_hash])
            if len(matches) != 1:
                raise ValueError(
                    f"price snapshot lineage is missing: {current.snapshot_hash} -> {dependency_hash}"
                )
            dependency = matches[0]
            snapshots[dependency.snapshot_hash] = dependency
            pending.append(dependency)
    ordered: list[PriceSnapshot] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item: PriceSnapshot) -> None:
        if item.snapshot_hash in visited:
            return
        if item.snapshot_hash in visiting:
            raise ValueError(f"price snapshot lineage contains a cycle: {item.snapshot_hash}")
        visiting.add(item.snapshot_hash)
        for dependency_hash in lineage_snapshot_hashes(item):
            visit(snapshots[dependency_hash])
        visiting.remove(item.snapshot_hash)
        visited.add(item.snapshot_hash)
        ordered.append(item)

    for item in sorted(
        snapshots.values(),
        key=lambda value: (
            value.instrument.canonical_code,
            value.requested_start,
            value.requested_end,
            value.retrieved_at,
            value.snapshot_hash,
        ),
    ):
        visit(item)
    return ordered


def lineage_snapshot_hashes(snapshot: PriceSnapshot) -> tuple[str, ...]:
    keys = ("parent_snapshot_hash", "incremental_tail_snapshot_hash", "derived_from_cache")
    return tuple(
        str(snapshot.metadata[key])
        for key in keys
        if isinstance(snapshot.metadata.get(key), str) and snapshot.metadata[key]
    )


def raw_evidence_hashes(snapshot: PriceSnapshot) -> tuple[str, ...]:
    values = snapshot.metadata.get("source_snapshot_hashes")
    if values is None:
        values = [snapshot.source_snapshot_hash]
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError(
            f"price snapshot has invalid raw evidence provenance: {snapshot.snapshot_hash}"
        )
    hashes = tuple(dict.fromkeys(str(value) for value in values))
    if any(len(value) != 64 or any(character not in "0123456789abcdef" for character in value) for value in hashes):
        raise ValueError(
            f"price snapshot has invalid raw evidence hash: {snapshot.snapshot_hash}"
        )
    return hashes
