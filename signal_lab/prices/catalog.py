from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any

from signal_lab.data.http import HttpTransport, UrllibJsonTransport
from signal_lab.prices.catalog_conventions import (
    default_provider_mappings as default_provider_mappings,
    infer_instrument,
    looks_canonical,
)
from signal_lab.prices.catalog_record import (
    CatalogRecord,
    instrument_payload as instrument_payload,
)
from signal_lab.prices.catalog_seed import CATALOG_SEED_VERSION, seed_records
from signal_lab.prices.catalog_sources import catalog_source_loaders
from signal_lab.prices.models import Instrument
from signal_lab.storage.catalog_repository import CatalogRepository
from signal_lab.storage.database import SignalLabDatabase
from signal_lab.storage.projections import MetadataRepository


_SEED_LOCK = Lock()


def sync_instrument_catalog(
    database: SignalLabDatabase,
    *,
    include_remote: bool = True,
    transport: HttpTransport | None = None,
) -> dict[str, Any]:
    catalog = CatalogRepository(database)
    metadata = MetadataRepository(database)
    records = list(seed_records())
    warnings: list[str] = []
    attempts: list[dict[str, Any]] = [{"source": "built_in_seed", "status": "ok", "records": len(records)}]
    if include_remote:
        http = transport or UrllibJsonTransport()
        loaders, source_warnings, source_attempts = catalog_source_loaders(http)
        warnings.extend(source_warnings)
        attempts.extend(source_attempts)
        with ThreadPoolExecutor(max_workers=len(loaders)) as executor:
            futures = {
                source: executor.submit(_load_catalog_records, loader)
                for source, loader in loaders
            }
        for source, _ in loaders:
            try:
                loaded = futures[source].result()
                records.extend(loaded)
                attempts.append({"source": source, "status": "ok", "records": len(loaded)})
            except Exception as exc:
                warnings.append(f"{source} catalog unavailable: {exc}")
                attempts.append({"source": source, "status": "error", "error": str(exc)})
    deduplicated: dict[str, CatalogRecord] = {}
    for record in records:
        existing = deduplicated.get(record.instrument.canonical_code)
        if existing is None:
            deduplicated[record.instrument.canonical_code] = record
        elif record.priority > existing.priority:
            record.aliases.update(existing.aliases)
            for provider, symbol in existing.provider_mappings.items():
                record.provider_mappings.setdefault(provider, symbol)
            deduplicated[record.instrument.canonical_code] = record
        elif existing:
            existing.aliases.update(record.aliases)
            for provider, symbol in record.provider_mappings.items():
                existing.provider_mappings.setdefault(provider, symbol)
    catalog.upsert_instruments(
        [
            (
                record.instrument,
                sorted({(record.instrument.canonical_code, "canonical_code"), *record.aliases}),
                record.provider_mappings,
            )
            for record in deduplicated.values()
        ]
    )
    metadata.set("instrument_catalog_seed_version", CATALOG_SEED_VERSION)
    successful = {item["source"] for item in attempts if item["status"] == "ok"}
    complete = not include_remote or (
        bool(successful & {"akshare_A-share", "baostock_mainland"})
        and bool(successful & {"akshare_US security", "nasdaq_trader_us"})
        and bool(successful & {"akshare_Hong Kong security", "hkex_hong_kong"})
    )
    return {
        "instrument_count": len(deduplicated),
        "alias_count": sum(len(record.aliases) + 1 for record in deduplicated.values()),
        "complete": complete,
        "attempts": attempts,
        "warnings": warnings,
    }

def _load_catalog_records(
    loader: Callable[[], Iterable[CatalogRecord]],
) -> list[CatalogRecord]:
    return list(loader())

def resolve_instrument(database: SignalLabDatabase, query: str) -> list[Instrument]:
    stripped = query.strip()
    if not stripped:
        return []
    _ensure_seed_catalog(database)
    canonical = stripped.upper()
    if looks_canonical(canonical):
        catalog = CatalogRepository(database)
        existing = catalog.get_instrument(canonical)
        if existing:
            return [existing]
        inferred = infer_instrument(canonical)
        if inferred:
            catalog.upsert_instrument(
                inferred,
                aliases=[(canonical, "canonical_code")],
                provider_mappings=default_provider_mappings(inferred),
            )
            return [inferred]
    matches = CatalogRepository(database).resolve_instruments(stripped)
    if matches:
        return matches
    return []


def _ensure_seed_catalog(database: SignalLabDatabase) -> None:
    metadata = MetadataRepository(database)
    if metadata.get("instrument_catalog_seed_version") == CATALOG_SEED_VERSION:
        return
    with _SEED_LOCK:
        if metadata.get("instrument_catalog_seed_version") != CATALOG_SEED_VERSION:
            sync_instrument_catalog(database, include_remote=False)
