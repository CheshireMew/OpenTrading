from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from app.infra.persistence.market.history.catalog_rows import normalize_alias as _normalize_alias
from app.infra.persistence.market.history.catalog_rows import upsert_instrument_row as _upsert_instrument_row
from app.infra.persistence.market.history.codec import json_loads
from app.infra.persistence.market.history.codec import utc_now as _utc_now
from app.infra.persistence.market.history.database import MarketHistoryDatabase


class CatalogRepository:
    """Owns canonical instruments, aliases, and provider mappings."""

    def __init__(self, database: MarketHistoryDatabase) -> None:
        self._database = database

    def upsert_instrument(
        self,
        instrument: Any,
        *,
        aliases: Sequence[tuple[str, str]] = (),
        provider_mappings: dict[str, str] | None = None,
    ) -> None:
        now = _utc_now()
        with self._database.connect() as connection:
            _upsert_instrument_row(
                connection, instrument, aliases, provider_mappings or {}, now,
            )

    def upsert_instruments(
        self,
        records: Sequence[tuple[Any, Sequence[tuple[str, str]], dict[str, str]]],
    ) -> None:
        now = _utc_now()
        with self._database.connect() as connection:
            for instrument, aliases, provider_mappings in records:
                _upsert_instrument_row(
                    connection, instrument, aliases, provider_mappings, now,
                )

    def get_instrument(self, canonical_code: str) -> Any | None:
        from app.domain.market.history.models import Instrument

        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM instruments WHERE canonical_code = ?",
                (canonical_code,),
            ).fetchone()
        if row is None:
            return None
        return Instrument(
            canonical_code=row["canonical_code"], name=row["name"],
            asset_class=row["asset_class"], market=row["market"], exchange=row["exchange_code"],
            currency=row["currency"], timezone=row["timezone"],
            listed_on=date.fromisoformat(row["listed_on"]) if row["listed_on"] else None,
            is_continuous=bool(row["is_continuous"]), metadata=json_loads(row["metadata_json"]),
        )

    def resolve_instruments(self, query: str) -> list[Any]:
        from app.domain.market.history.models import Instrument

        canonical = query.strip().upper()
        normalized = _normalize_alias(query)
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM instruments WHERE canonical_code = ?
                UNION
                SELECT instrument.*
                FROM instrument_aliases AS alias
                JOIN instruments AS instrument USING(canonical_code)
                WHERE alias.normalized_alias = ?
                ORDER BY canonical_code
                """,
                (canonical, normalized),
            ).fetchall()
        return [
            Instrument(
                canonical_code=row["canonical_code"], name=row["name"],
                asset_class=row["asset_class"], market=row["market"], exchange=row["exchange_code"],
                currency=row["currency"], timezone=row["timezone"],
                listed_on=date.fromisoformat(row["listed_on"]) if row["listed_on"] else None,
                is_continuous=bool(row["is_continuous"]), metadata=json_loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def provider_mapping(self, canonical_code: str, provider: str) -> str | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT provider_symbol FROM provider_mappings WHERE canonical_code = ? AND provider = ?",
                (canonical_code, provider),
            ).fetchone()
        return row["provider_symbol"] if row else None
