from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from app.infra.persistence.market.history.sql import CatalogConnection
from app.infra.persistence.market.history.codec import iso as _iso
from app.infra.persistence.market.history.codec import json_dumps, json_loads
from app.infra.persistence.market.history.codec import utc_now as _utc_now
from app.infra.persistence.market.history.database import MarketHistoryDatabase


class MacroHistoryRepository:
    """Owns normalized macro history snapshots."""

    def __init__(self, database: MarketHistoryDatabase) -> None:
        self._database = database

    def save_macro_history(
        self,
        *,
        snapshot_hash: str,
        series_id: str,
        provider: str,
        requested_start: date,
        requested_end: date,
        retrieved_at: datetime,
        source_snapshot_hash: str,
        values: Sequence[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        actual_start = _iso(values[0]["date"]) if values else None
        actual_end = _iso(values[-1]["date"]) if values else None
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE macro_history_snapshots SET is_latest = 0 WHERE series_id = ?",
                (series_id,),
            )
            connection.execute(
                """
                INSERT INTO macro_history_snapshots(
                    snapshot_hash, series_id, provider, requested_start, requested_end,
                    actual_start, actual_end, retrieved_at, source_snapshot_hash,
                    row_count, is_latest, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(snapshot_hash) DO UPDATE SET is_latest = 1,
                    metadata_json = excluded.metadata_json
                """,
                (
                    snapshot_hash, series_id, provider, requested_start.isoformat(),
                    requested_end.isoformat(), actual_start, actual_end, retrieved_at.isoformat(),
                    source_snapshot_hash, len(values), json_dumps(metadata or {}),
                ),
            )
            connection.execute(
                "DELETE FROM macro_history_values WHERE snapshot_hash = ?",
                (snapshot_hash,),
            )
            connection.executemany(
                """
                INSERT INTO macro_history_values(
                    snapshot_hash, observation_date, value, realtime_start, realtime_end
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_hash, _iso(item["date"]), item["value"],
                        _iso(item["realtime_start"]) if item.get("realtime_start") else None,
                        _iso(item["realtime_end"]) if item.get("realtime_end") else None,
                    )
                    for item in values
                ],
            )
        return self._database.location

    def load_macro_history(
        self,
        series_id: str,
        *,
        snapshot_hash: str | None = None,
        covering_start: date | None = None,
        covering_end: date | None = None,
    ) -> dict[str, Any] | None:
        query = "SELECT * FROM macro_history_snapshots WHERE series_id = ?"
        parameters: list[Any] = [series_id]
        if snapshot_hash:
            query += " AND snapshot_hash = ?"
            parameters.append(snapshot_hash)
        elif covering_start and covering_end:
            query += " AND requested_start <= ? AND requested_end >= ?"
            parameters.extend([covering_start.isoformat(), covering_end.isoformat()])
        else:
            query += " AND is_latest = 1"
        query += " ORDER BY retrieved_at DESC LIMIT 1"
        with self._database.connect() as connection:
            row = connection.execute(query, parameters).fetchone()
            if row is None:
                return None
            values = connection.execute(
                "SELECT * FROM macro_history_values WHERE snapshot_hash = ? ORDER BY observation_date",
                (row["snapshot_hash"],),
            ).fetchall()
        return {
            **dict(row),
            "metadata": json_loads(row["metadata_json"]),
            "values": [
                {
                    "date": date.fromisoformat(item["observation_date"]),
                    "value": item["value"],
                    "realtime_start": date.fromisoformat(item["realtime_start"]) if item["realtime_start"] else None,
                    "realtime_end": date.fromisoformat(item["realtime_end"]) if item["realtime_end"] else None,
                }
                for item in values
            ],
        }


class IndicatorRepository:
    """Owns indicator definitions, observations, and their read inventory."""

    def __init__(self, database: MarketHistoryDatabase) -> None:
        self._database = database

    def upsert_indicator_series(self, definitions: Sequence[dict[str, Any]]) -> None:
        now = _utc_now()
        with self._database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO indicator_series(
                    indicator_id, provider, provider_series_id, name, short_label,
                    category, group_id, group_label, unit, frequency, polarity,
                    description, is_scored, raw_weight, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(indicator_id) DO UPDATE SET
                    provider = excluded.provider,
                    provider_series_id = excluded.provider_series_id,
                    name = excluded.name,
                    short_label = excluded.short_label,
                    category = excluded.category,
                    group_id = excluded.group_id,
                    group_label = excluded.group_label,
                    unit = excluded.unit,
                    frequency = excluded.frequency,
                    polarity = excluded.polarity,
                    description = excluded.description,
                    is_scored = excluded.is_scored,
                    raw_weight = excluded.raw_weight,
                    updated_at = excluded.updated_at
                WHERE indicator_series.provider IS DISTINCT FROM excluded.provider
                   OR indicator_series.provider_series_id IS DISTINCT FROM excluded.provider_series_id
                   OR indicator_series.name IS DISTINCT FROM excluded.name
                   OR indicator_series.short_label IS DISTINCT FROM excluded.short_label
                   OR indicator_series.category IS DISTINCT FROM excluded.category
                   OR indicator_series.group_id IS DISTINCT FROM excluded.group_id
                   OR indicator_series.group_label IS DISTINCT FROM excluded.group_label
                   OR indicator_series.unit IS DISTINCT FROM excluded.unit
                   OR indicator_series.frequency IS DISTINCT FROM excluded.frequency
                   OR indicator_series.polarity IS DISTINCT FROM excluded.polarity
                   OR indicator_series.description IS DISTINCT FROM excluded.description
                   OR indicator_series.is_scored IS DISTINCT FROM excluded.is_scored
                   OR indicator_series.raw_weight IS DISTINCT FROM excluded.raw_weight
                """,
                [
                    (
                        item["indicator_id"],
                        item["provider"],
                        item.get("provider_series_id"),
                        item["name"],
                        item["short_label"],
                        item.get("category", "Macro"),
                        item["group_id"],
                        item["group_label"],
                        item.get("unit", ""),
                        item.get("frequency", "daily"),
                        item["polarity"],
                        item["description"],
                        int(item.get("is_scored", True)),
                        float(item.get("raw_weight", 0.0)),
                        now,
                    )
                    for item in definitions
                ],
            )

    def upsert_indicator_observations(
        self,
        indicator_id: str,
        rows: Sequence[dict[str, Any]],
        *,
        source: str,
        retrieved_at: datetime,
        snapshot_hash: str,
    ) -> int:
        if not rows:
            return 0
        with self._database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO indicator_observations(
                    indicator_id, observation_date, value, source, retrieved_at, snapshot_hash
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(indicator_id, observation_date) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source,
                    retrieved_at = excluded.retrieved_at,
                    snapshot_hash = excluded.snapshot_hash
                WHERE indicator_observations.value IS DISTINCT FROM excluded.value
                   OR indicator_observations.source IS DISTINCT FROM excluded.source
                   OR indicator_observations.snapshot_hash IS DISTINCT FROM excluded.snapshot_hash
                """,
                [
                    (
                        indicator_id,
                        _iso(item["observation_date"]),
                        float(item["value"]),
                        source,
                        retrieved_at.isoformat(),
                        snapshot_hash,
                    )
                    for item in rows
                ],
            )
        return len(rows)

    def indicator_history(
        self,
        indicator_ids: Sequence[str],
        *,
        start_at: datetime | date | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not indicator_ids:
            return {}
        placeholders = ",".join("?" for _ in indicator_ids)
        query = f"""
            SELECT indicator_id, observation_date, value, source, retrieved_at, snapshot_hash
            FROM indicator_observations
            WHERE indicator_id IN ({placeholders})
        """
        parameters: list[Any] = list(indicator_ids)
        if start_at is not None:
            query += " AND observation_date >= ?"
            parameters.append(_iso(start_at))
        query += " ORDER BY indicator_id, observation_date"
        with self._database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        output: dict[str, list[dict[str, Any]]] = {item: [] for item in indicator_ids}
        for row in rows:
            timestamp = datetime.combine(
                date.fromisoformat(row["observation_date"][:10]),
                datetime.min.time(),
                tzinfo=UTC,
            )
            output.setdefault(row["indicator_id"], []).append(
                {
                    "date": row["observation_date"],
                    "timestamp": timestamp,
                    "value": row["value"],
                    "source": row["source"],
                    "retrieved_at": row["retrieved_at"],
                    "snapshot_hash": row["snapshot_hash"],
                }
            )
        return output

    def indicator_inventory(
        self,
        connection: CatalogConnection | None = None,
    ) -> list[dict[str, Any]]:
        if connection is None:
            with self._database.connect() as owned:
                owned.execute("BEGIN")
                return self.indicator_inventory(owned)
        rows = connection.execute(
                """
                SELECT s.*, COUNT(o.observation_date) AS row_count,
                       MIN(o.observation_date) AS start_at,
                       MAX(o.observation_date) AS end_at,
                       MAX(o.retrieved_at) AS retrieved_at
                FROM indicator_series AS s
                LEFT JOIN indicator_observations AS o
                  ON o.indicator_id = s.indicator_id
                GROUP BY s.indicator_id
                ORDER BY s.group_id, s.indicator_id
                """
        ).fetchall()
        return [dict(row) for row in rows]
