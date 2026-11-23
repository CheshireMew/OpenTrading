from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.infra.persistence.market.history.codec import json_dumps, json_loads
from app.infra.persistence.market.history.database import MarketHistoryDatabase


class PriceDatasetRepository:
    """Owns published price dataset manifests and membership rows."""

    def __init__(self, database: MarketHistoryDatabase) -> None:
        self._database = database

    def save_price_dataset(
        self,
        payload: dict[str, Any],
        members: Sequence[dict[str, Any]],
    ) -> None:
        manifest = Path(payload["manifest_path"]).resolve()
        relative_manifest = manifest.relative_to(self._database.root).as_posix()
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO price_datasets(
                    dataset_hash, name, timeframe, basis, requested_start, requested_end,
                    created_at, manifest_relative_path, row_count, instrument_count, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_hash) DO UPDATE SET
                    manifest_relative_path = excluded.manifest_relative_path,
                    row_count = excluded.row_count,
                    instrument_count = excluded.instrument_count,
                    metadata_json = excluded.metadata_json
                """,
                (
                    payload["dataset_hash"], payload["name"], payload["timeframe"],
                    payload["basis"], payload["requested_start"], payload["requested_end"],
                    payload["created_at"], relative_manifest, payload["row_count"],
                    payload["instrument_count"], json_dumps(payload.get("metadata", {})),
                ),
            )
            connection.execute(
                "DELETE FROM price_dataset_members WHERE dataset_hash = ?",
                (payload["dataset_hash"],),
            )
            connection.executemany(
                """
                INSERT INTO price_dataset_members(
                    dataset_hash, canonical_code, snapshot_hash, row_count,
                    partition_relative_path
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        payload["dataset_hash"], item["canonical_code"], item["snapshot_hash"],
                        item["row_count"], item["partition_relative_path"],
                    )
                    for item in members
                ],
            )

    def price_dataset(self, dataset_hash: str) -> dict[str, Any]:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM price_datasets WHERE dataset_hash = ?", (dataset_hash,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"price dataset does not exist: {dataset_hash}")
            members = connection.execute(
                "SELECT * FROM price_dataset_members WHERE dataset_hash = ? ORDER BY canonical_code",
                (dataset_hash,),
            ).fetchall()
        payload = dict(row)
        payload["manifest_path"] = str(
            (self._database.root / payload.pop("manifest_relative_path")).resolve()
        )
        payload["metadata"] = json_loads(payload.pop("metadata_json"))
        payload["members"] = [dict(item) for item in members]
        return payload
