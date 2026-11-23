from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from app.infra.persistence.market.history.sql import CatalogConnection
from app.infra.persistence.market.history.catalog_repository import CatalogRepository
from app.infra.persistence.market.history.catalog_rows import upsert_instrument_row as _upsert_instrument_row
from app.infra.persistence.market.history.codec import json_loads
from app.infra.persistence.market.history.codec import utc_now as _utc_now
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.price_rows import is_external_project_reference as _is_external_project_reference
from app.infra.persistence.market.history.price_rows import save_price_snapshot_row as _save_price_snapshot_row


class PriceRepository:
    """Owns normalized price snapshots, bars, coverage, and cache selection."""

    def __init__(self, database: MarketHistoryDatabase) -> None:
        self._database = database
        self._catalog = CatalogRepository(database)

    def save_price_snapshot(
        self,
        snapshot: Any,
        *,
        coverage_issues: Sequence[dict[str, Any]] = (),
    ) -> str:
        if _is_external_project_reference(snapshot.provider, snapshot.metadata):
            raise ValueError(
                "external project price data cannot be written to the active Signal Lab database"
            )
        with self._database.connect() as connection:
            _upsert_instrument_row(connection, snapshot.instrument, (), {}, _utc_now())
            _save_price_snapshot_row(connection, snapshot, coverage_issues)
        return self._database.location

    def list_price_snapshots(
        self,
        *,
        snapshot_hashes: Sequence[str] | None = None,
        canonical_codes: Sequence[str] | None = None,
    ) -> list[Any]:
        query = "SELECT canonical_code, snapshot_hash FROM price_snapshots"
        clauses: list[str] = []
        parameters: list[Any] = []
        if snapshot_hashes is not None:
            if not snapshot_hashes:
                return []
            clauses.append(f"snapshot_hash IN ({','.join('?' for _ in snapshot_hashes)})")
            parameters.extend(snapshot_hashes)
        if canonical_codes is not None:
            if not canonical_codes:
                return []
            clauses.append(f"canonical_code IN ({','.join('?' for _ in canonical_codes)})")
            parameters.extend(canonical_codes)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY canonical_code, requested_start, requested_end, snapshot_hash"
        with self._database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            self.load_price_snapshot(row["canonical_code"], row["snapshot_hash"])
            for row in rows
        ]

    def coverage_issues(self, snapshot_hash: str) -> list[dict[str, Any]]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT issue_type AS type, issue_date AS date, detail
                FROM coverage_issues WHERE snapshot_hash = ?
                ORDER BY issue_type, issue_date, detail
                """,
                (snapshot_hash,),
            ).fetchall()
        return [
            {"type": row["type"], "date": row["date"] or None, "detail": row["detail"]}
            for row in rows
        ]

    def load_price_snapshot(
        self,
        canonical_code: str,
        snapshot_hash: str | None = None,
        *,
        timeframe: str | None = None,
        provider: str | None = None,
    ) -> Any:
        from app.domain.market.history.models import PriceBar, PriceSnapshot

        with self._database.connect() as connection:
            if snapshot_hash is None:
                query = "SELECT * FROM price_snapshots WHERE canonical_code = ? AND is_latest = 1"
                parameters: list[Any] = [canonical_code]
                if timeframe:
                    query += " AND timeframe = ?"
                    parameters.append(timeframe)
                if provider:
                    query += " AND provider = ?"
                    parameters.append(provider)
                query += (
                    " ORDER BY (actual_end IS NOT NULL) DESC, actual_end DESC, "
                    "actual_start ASC, retrieved_at DESC, snapshot_hash DESC LIMIT 1"
                )
                row = connection.execute(query, parameters).fetchone()
            else:
                query = """
                    SELECT * FROM price_snapshots
                    WHERE canonical_code = ?
                      AND (snapshot_hash = ? OR source_snapshot_hash = ?)
                """
                parameters = [canonical_code, snapshot_hash, snapshot_hash]
                if timeframe:
                    query += " AND timeframe = ?"
                    parameters.append(timeframe)
                if provider:
                    query += " AND provider = ?"
                    parameters.append(provider)
                query += " ORDER BY retrieved_at DESC LIMIT 1"
                row = connection.execute(query, parameters).fetchone()
            if row is None:
                raise FileNotFoundError(f"price snapshot does not exist: {canonical_code}")
            bar_rows = connection.execute(
                "SELECT * FROM price_bars WHERE snapshot_hash = ? ORDER BY observed_at",
                (row["snapshot_hash"],),
            ).fetchall()
        instrument = self._catalog.get_instrument(canonical_code)
        if instrument is None:
            raise ValueError(f"price snapshot references an unknown instrument: {canonical_code}")
        return PriceSnapshot(
            instrument=instrument, timeframe=row["timeframe"], provider=row["provider"],
            provider_symbol=row["provider_symbol"],
            requested_start=date.fromisoformat(row["requested_start"]),
            requested_end=date.fromisoformat(row["requested_end"]),
            retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
            source_snapshot_hash=row["source_snapshot_hash"], price_basis=row["price_basis"],
            coverage_status=row["coverage_status"], metadata=json_loads(row["metadata_json"]),
            identity_version=row["identity_version"],
            _persisted_snapshot_hash=(
                row["snapshot_hash"] if row["identity_version"] == 1 else None
            ),
            bars=tuple(
                PriceBar(
                    observed_at=datetime.fromisoformat(item["observed_at"]),
                    open=item["open"], high=item["high"], low=item["low"], close=item["close"],
                    adjusted_close=item["adjusted_close"], volume=item["volume"],
                    dividend=item["dividend"], split_factor=item["split_factor"],
                )
                for item in bar_rows
            ),
        )

    def find_cached_price_snapshot(
        self,
        canonical_code: str,
        start: date,
        end: date,
        provider: str | None = None,
    ) -> Any | None:
        snapshot_hash = self.find_cached_price_snapshot_hash(
            canonical_code, start, end, provider,
        )
        return (
            self.load_price_snapshot(canonical_code, snapshot_hash)
            if snapshot_hash is not None
            else None
        )

    def find_cached_price_snapshot_hash(
        self,
        canonical_code: str,
        start: date,
        end: date,
        provider: str | None = None,
    ) -> str | None:
        """Select a covering snapshot without decoding all of its price bars."""

        query = """
            SELECT snapshot_hash FROM price_snapshots
            WHERE canonical_code = ? AND timeframe = '1d'
              AND requested_start <= ? AND requested_end >= ?
        """
        parameters: list[Any] = [canonical_code, start.isoformat(), end.isoformat()]
        if provider:
            query += " AND provider = ?"
            parameters.append(provider)
        query += " ORDER BY (coverage_status = 'complete') DESC, retrieved_at DESC LIMIT 1"
        with self._database.connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return str(row["snapshot_hash"]) if row else None

    def price_inventory(
        self,
        connection: CatalogConnection | None = None,
    ) -> list[dict[str, Any]]:
        if connection is None:
            with self._database.connect() as owned:
                owned.execute("BEGIN")
                return self.price_inventory(owned)
        rows = connection.execute(
                """
                WITH ranked AS (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY canonical_code, timeframe, provider
                               ORDER BY (actual_end IS NOT NULL) DESC, actual_end DESC,
                                        actual_start ASC, retrieved_at DESC, snapshot_hash DESC
                           ) AS rank_in_provider
                    FROM price_snapshots
                    WHERE is_latest = 1
                )
                SELECT canonical_code AS symbol, timeframe, provider AS price_source,
                       provider_symbol AS venue, snapshot_hash AS data_hash,
                       metadata_json AS source_note, retrieved_at AS updated_at, row_count,
                       actual_start AS start_at, actual_end AS end_at
                FROM ranked
                WHERE rank_in_provider = 1
                ORDER BY canonical_code, timeframe, provider
                """
        ).fetchall()
        return [dict(row) for row in rows]

    def daily_explorer_inventory(
        self,
        connection: CatalogConnection | None = None,
    ) -> list[dict[str, Any]]:
        """Return one explicitly identified daily snapshot per instrument for the web explorer."""

        if connection is None:
            with self._database.connect() as owned:
                owned.execute("BEGIN")
                return self.daily_explorer_inventory(owned)
        rows = connection.execute(
            """
            WITH ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY canonical_code
                           ORDER BY (actual_end IS NOT NULL) DESC, actual_end DESC,
                                    actual_start ASC, (coverage_status = 'complete') DESC,
                                    retrieved_at DESC, snapshot_hash DESC
                       ) AS explorer_rank
                FROM price_snapshots
                WHERE is_latest = 1 AND timeframe = '1d' AND row_count > 0
            )
            SELECT canonical_code AS symbol, timeframe, provider AS price_source,
                   provider_symbol AS venue, snapshot_hash AS data_hash,
                   retrieved_at AS updated_at, row_count,
                   actual_start AS start_at, actual_end AS end_at,
                   coverage_status
            FROM ranked
            WHERE explorer_rank = 1
            ORDER BY canonical_code
            """
        ).fetchall()
        return [dict(row) for row in rows]
