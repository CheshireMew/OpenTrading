from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.identities import raw_acquisition_id


class RawSnapshotRepository:
    """Owns raw snapshot identities and their controlled physical locations."""

    def __init__(self, database: MarketHistoryDatabase) -> None:
        self.database = database
        self.root = database.root.resolve()

    def register(
        self,
        *,
        snapshot_hash: str,
        provider: str,
        resource: str,
        retrieved_at: datetime,
        path: Path,
    ) -> str:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError(f"raw snapshot path escapes the data root: {resolved}") from exc
        normalized_retrieved_at = retrieved_at.astimezone(timezone.utc).isoformat()
        acquisition_id = raw_acquisition_id(
            snapshot_hash,
            provider,
            resource,
            normalized_retrieved_at,
        )
        created_at = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO raw_snapshots(
                    snapshot_hash, provider, resource, retrieved_at, relative_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_hash) DO NOTHING
                """,
                (
                    snapshot_hash, provider, resource, normalized_retrieved_at, relative,
                    created_at,
                ),
            )
            stored = connection.execute(
                "SELECT relative_path FROM raw_snapshots WHERE snapshot_hash = ?",
                (snapshot_hash,),
            ).fetchone()
            if stored is None or stored["relative_path"] != relative:
                raise ValueError(
                    f"raw snapshot content identity points to a different object: {snapshot_hash}"
                )
            connection.execute(
                """
                INSERT INTO raw_snapshot_acquisitions(
                    acquisition_id, snapshot_hash, provider, resource, retrieved_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(acquisition_id) DO NOTHING
                """,
                (
                    acquisition_id, snapshot_hash, provider, resource,
                    normalized_retrieved_at, created_at,
                ),
            )
        return acquisition_id

    def record(self, snapshot_hash: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM raw_snapshots WHERE snapshot_hash = ?", (snapshot_hash,),
            ).fetchone()
        if row is None:
            return None
        relative = Path(row["relative_path"])
        if relative.is_absolute():
            raise ValueError(f"raw snapshot record contains an absolute path: {snapshot_hash}")
        resolved = (self.root / relative).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"raw snapshot record escapes the data root: {snapshot_hash}") from exc
        return {
            "snapshot_hash": row["snapshot_hash"],
            "provider": row["provider"],
            "resource": row["resource"],
            "retrieved_at": row["retrieved_at"],
            "path": str(resolved),
            "created_at": row["created_at"],
        }

    def acquisitions(self, snapshot_hash: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT acquisition_id, snapshot_hash, provider, resource, retrieved_at, created_at
                FROM raw_snapshot_acquisitions
                WHERE snapshot_hash = ?
                ORDER BY retrieved_at, acquisition_id
                """,
                (snapshot_hash,),
            ).fetchall()
        return [dict(row) for row in rows]

    def acquisition(self, acquisition_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT acquisition_id, snapshot_hash, provider, resource, retrieved_at, created_at
                FROM raw_snapshot_acquisitions WHERE acquisition_id = ?
                """,
                (acquisition_id,),
            ).fetchone()
        return dict(row) if row is not None else None
