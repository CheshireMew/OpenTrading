from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import Any

from signal_lab.storage.sql import CatalogConnection
from signal_lab.storage.codec import json_dumps, json_loads, utc_now
from signal_lab.storage.database import SCHEMA_VERSION, SignalLabDatabase


class MetadataRepository:
    """Owns small application metadata values, not domain records."""

    def __init__(self, database: SignalLabDatabase) -> None:
        self.database = database

    def get(self, key: str) -> Any | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM application_metadata WHERE key = ?", (key,),
            ).fetchone()
        return json_loads(row["value_json"]) if row is not None else None

    def set(self, key: str, value: Any) -> None:
        encoded = json_dumps(value)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO application_metadata(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                WHERE application_metadata.value_json IS DISTINCT FROM excluded.value_json
                """,
                (key, encoded, utc_now()),
            )


class DatabaseProjection:
    """Explicit read model spanning domain tables at one database snapshot."""

    def __init__(self, database: SignalLabDatabase) -> None:
        self.database = database

    def indicator_revision(self, indicator_ids: Sequence[str]) -> str:
        if not indicator_ids:
            return "empty"
        placeholders = ",".join("?" for _ in indicator_ids)
        with self.database.connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS row_count,
                       MAX(retrieved_at) AS retrieved_at,
                       MAX(snapshot_hash) AS snapshot_hash,
                       MAX(observation_date) AS end_at
                FROM indicator_observations
                WHERE indicator_id IN ({placeholders})
                """,
                list(indicator_ids),
            ).fetchone()
        return sha256(json_dumps(dict(row)).encode("utf-8")).hexdigest()

    def summary(self, connection: CatalogConnection | None = None) -> dict[str, Any]:
        if connection is None:
            with self.database.connect() as owned:
                owned.execute("BEGIN")
                return self.summary(owned)
        tables = {
            "instruments": "instruments",
            "price_snapshots": "price_snapshots",
            "price_bars": "price_bars",
            "coverage_issues": "coverage_issues",
            "bundle_imports": "snapshot_bundle_imports",
            "classification_snapshots": "classification_snapshots",
            "classification_memberships": "classification_memberships",
            "price_datasets": "price_datasets",
            "macro_history_snapshots": "macro_history_snapshots",
            "macro_history_values": "macro_history_values",
            "macro_series": "indicator_series",
            "macro_observations": "indicator_observations",
            "jobs": "jobs",
        }
        counts = {
            label: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for label, table in tables.items()
        }
        return {
            "path": self.database.location,
            "schema_version": SCHEMA_VERSION,
            "size_bytes": self.database.size_bytes(connection),
            "counts": counts,
        }
