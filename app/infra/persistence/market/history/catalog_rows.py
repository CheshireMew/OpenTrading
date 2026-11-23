from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.infra.persistence.market.history.sql import CatalogConnection
from app.infra.persistence.market.history.codec import json_dumps


def normalize_alias(value: str) -> str:
    return "".join(value.strip().casefold().split())


def upsert_instrument_row(
    connection: CatalogConnection,
    instrument: Any,
    aliases: Sequence[tuple[str, str]],
    provider_mappings: dict[str, str],
    updated_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO instruments(
            canonical_code, name, asset_class, market, exchange_code, currency,
            timezone, listed_on, is_continuous, metadata_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(canonical_code) DO UPDATE SET
            name = excluded.name,
            asset_class = excluded.asset_class,
            market = excluded.market,
            exchange_code = excluded.exchange_code,
            currency = excluded.currency,
            timezone = excluded.timezone,
            listed_on = excluded.listed_on,
            is_continuous = excluded.is_continuous,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        WHERE instruments.name IS DISTINCT FROM excluded.name
           OR instruments.asset_class IS DISTINCT FROM excluded.asset_class
           OR instruments.market IS DISTINCT FROM excluded.market
           OR instruments.exchange_code IS DISTINCT FROM excluded.exchange_code
           OR instruments.currency IS DISTINCT FROM excluded.currency
           OR instruments.timezone IS DISTINCT FROM excluded.timezone
           OR instruments.listed_on IS DISTINCT FROM excluded.listed_on
           OR instruments.is_continuous IS DISTINCT FROM excluded.is_continuous
           OR instruments.metadata_json IS DISTINCT FROM excluded.metadata_json
        """,
        (
            instrument.canonical_code,
            instrument.name,
            instrument.asset_class,
            instrument.market,
            instrument.exchange,
            instrument.currency,
            instrument.timezone,
            instrument.listed_on.isoformat() if instrument.listed_on else None,
            int(instrument.is_continuous),
            json_dumps(instrument.metadata),
            updated_at,
        ),
    )
    connection.executemany(
        """
        INSERT INTO instrument_aliases(normalized_alias, alias, canonical_code, alias_kind)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(normalized_alias, canonical_code) DO UPDATE SET
            alias = excluded.alias, alias_kind = excluded.alias_kind
        WHERE instrument_aliases.alias IS DISTINCT FROM excluded.alias
           OR instrument_aliases.alias_kind IS DISTINCT FROM excluded.alias_kind
        """,
        [
            (normalize_alias(alias), alias, instrument.canonical_code, alias_kind)
            for alias, alias_kind in aliases
        ],
    )
    connection.executemany(
        """
        INSERT INTO provider_mappings(canonical_code, provider, provider_symbol)
        VALUES (?, ?, ?)
        ON CONFLICT(canonical_code, provider) DO UPDATE SET
            provider_symbol = excluded.provider_symbol
        WHERE provider_mappings.provider_symbol IS DISTINCT FROM excluded.provider_symbol
        """,
        [
            (instrument.canonical_code, provider, provider_symbol)
            for provider, provider_symbol in provider_mappings.items()
        ],
    )
