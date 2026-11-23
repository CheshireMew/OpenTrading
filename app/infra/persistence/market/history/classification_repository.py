from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from app.infra.persistence.market.history.codec import json_dumps
from app.infra.persistence.market.history.database import MarketHistoryDatabase


class ClassificationRepository:
    """Owns versioned classification schemes and memberships."""

    def __init__(self, database: MarketHistoryDatabase) -> None:
        self._database = database

    def save_classification_snapshot(
        self,
        *,
        snapshot_hash: str,
        scheme: dict[str, Any],
        source_snapshot_hash: str,
        classifications: Sequence[dict[str, Any]],
        memberships: Sequence[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO classification_snapshots(
                    snapshot_hash, scheme_id, scheme_name, scheme_version, provider,
                    retrieved_at, source_snapshot_hash, metadata_json, is_latest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(snapshot_hash) DO UPDATE SET
                    metadata_json = excluded.metadata_json
                """,
                (
                    snapshot_hash, scheme["scheme_id"], scheme["name"], scheme["version"],
                    scheme["provider"], scheme["retrieved_at"], source_snapshot_hash,
                    json_dumps(metadata or {}),
                ),
            )
            connection.execute("DELETE FROM classifications WHERE snapshot_hash = ?", (snapshot_hash,))
            connection.executemany(
                """
                INSERT INTO classifications(
                    snapshot_hash, classification_id, name, parent_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_hash, item["classification_id"], item["name"],
                        item.get("parent_id"), json_dumps(item.get("metadata", {})),
                    )
                    for item in classifications
                ],
            )
            connection.executemany(
                """
                INSERT INTO classification_memberships(
                    snapshot_hash, classification_id, canonical_code, valid_from,
                    valid_to, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_hash, item["classification_id"], item["canonical_code"],
                        item["valid_from"], item.get("valid_to"),
                        json_dumps(item.get("metadata", {})),
                    )
                    for item in memberships
                ],
            )
            connection.execute(
                "UPDATE classification_snapshots SET is_latest = 0 WHERE scheme_id = ?",
                (scheme["scheme_id"],),
            )
            connection.execute(
                """
                UPDATE classification_snapshots SET is_latest = 1
                WHERE snapshot_hash = (
                    SELECT snapshot_hash FROM classification_snapshots
                    WHERE scheme_id = ?
                    ORDER BY retrieved_at DESC, snapshot_hash DESC
                    LIMIT 1
                )
                """,
                (scheme["scheme_id"],),
            )

    def classification_memberships(
        self,
        canonical_code: str,
        *,
        as_of: date,
        scheme_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT snapshot.scheme_id, snapshot.scheme_name, snapshot.scheme_version,
                   node.classification_id, node.name, node.parent_id,
                   membership.valid_from, membership.valid_to,
                   snapshot.snapshot_hash AS classification_snapshot_hash
            FROM classification_snapshots AS snapshot
            JOIN classifications AS node USING(snapshot_hash)
            JOIN classification_memberships AS membership
              ON membership.snapshot_hash = node.snapshot_hash
             AND membership.classification_id = node.classification_id
            WHERE snapshot.is_latest = 1
              AND membership.canonical_code = ?
              AND membership.valid_from <= ?
              AND (membership.valid_to IS NULL OR membership.valid_to >= ?)
        """
        parameters: list[Any] = [canonical_code, as_of.isoformat(), as_of.isoformat()]
        if scheme_id:
            query += " AND snapshot.scheme_id = ?"
            parameters.append(scheme_id)
        query += " ORDER BY snapshot.scheme_id, node.classification_id"
        with self._database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]
