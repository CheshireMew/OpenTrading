from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from signal_lab.storage.catalog_rows import upsert_instrument_row
from signal_lab.storage.codec import json_dumps, utc_now
from signal_lab.storage.database import SignalLabDatabase
from signal_lab.storage.price_rows import (
    is_external_project_reference,
    save_price_snapshot_row,
)


class BundleImportRepository:
    """Owns one bundle import transaction and its terminal state."""

    def __init__(self, database: SignalLabDatabase) -> None:
        self._database = database

    def begin_bundle_import(
        self,
        *,
        import_id: str,
        bundle_hash: str,
        bundle_path: Path,
    ) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO snapshot_bundle_imports(
                    import_id, bundle_hash, bundle_path, accepted_at, status
                ) VALUES (?, ?, ?, ?, 'pending')
                """,
                (import_id, bundle_hash, str(bundle_path.resolve()), utc_now()),
            )

    def complete_bundle_import(
        self,
        *,
        import_id: str,
        snapshots: Sequence[Any],
        coverage_by_snapshot: dict[str, Sequence[dict[str, Any]]],
        details: dict[str, Any],
    ) -> None:
        with self._database.connect() as connection:
            for snapshot in snapshots:
                if is_external_project_reference(snapshot.provider, snapshot.metadata):
                    raise ValueError(
                        "external project price data cannot be written to the active Signal Lab database"
                    )
                upsert_instrument_row(connection, snapshot.instrument, (), {}, utc_now())
                save_price_snapshot_row(
                    connection,
                    snapshot,
                    coverage_by_snapshot.get(snapshot.snapshot_hash, ()),
                )
            cursor = connection.execute(
                """
                UPDATE snapshot_bundle_imports
                SET status = 'ok', completed_at = ?, snapshot_count = ?, details_json = ?
                WHERE import_id = ? AND status = 'pending'
                """,
                (utc_now(), len(snapshots), json_dumps(details), import_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"bundle import is not pending: {import_id}")

    def fail_bundle_import(self, import_id: str, message: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE snapshot_bundle_imports
                SET status = 'failed', completed_at = ?, details_json = ?
                WHERE import_id = ? AND status = 'pending'
                """,
                (utc_now(), json_dumps({"error": message}), import_id),
            )
