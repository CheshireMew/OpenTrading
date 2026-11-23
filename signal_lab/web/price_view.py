from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlencode

from app.product import api_path
from signal_lab.config import SignalLabConfig
from signal_lab.prices.catalog import instrument_payload, resolve_instrument
from signal_lab.prices.classifications import ClassificationService
from signal_lab.prices.indicators import (
    indicator_definitions_payload,
    indicator_registry_hash,
)
from signal_lab.prices.history_contract import history_envelope
from signal_lab.storage import SignalLabDatabase
from signal_lab.storage.price_repository import PriceRepository
from signal_lab.structured_data import canonical_json_bytes
from signal_lab.web.price_cache import CachedPriceProjection, ProjectionCache
from signal_lab.web.price_projection import (
    build_price_projection,
    select_daily_snapshot_hash,
)


_PRICE_PROJECTION_VERSION = "price-read-projection.v1"


class PriceReadView:
    """Read-only price projection used by the local HTTP workbench."""

    def __init__(self, config: SignalLabConfig, root: Path, database: SignalLabDatabase) -> None:
        self._database = database
        self._prices = PriceRepository(database)
        self._classifications = ClassificationService(root, config)
        self._projection_cache = ProjectionCache()

    def history(
        self,
        instrument: str,
        *,
        start: date,
        end: date,
        basis: str = "raw",
        limit: int = 5000,
        snapshot_hash: str | None = None,
    ) -> dict[str, Any]:
        if basis not in {"raw", "adjusted"}:
            raise ValueError("basis must be raw or adjusted")
        if start > end:
            raise ValueError("start must not be after end")
        payload, projection = self._cached_projection(
            instrument, start=start, end=end, basis=basis,
            snapshot_hash=snapshot_hash,
        )
        if projection is None:
            return payload
        snapshot_hash = payload["artifact"]["snapshot_hash"]
        canonical_code = payload["instrument"]["canonical_code"]
        truncated = len(projection.records) > limit
        if truncated:
            indexes = sorted(set(
                round(index * (len(projection.records) - 1) / (limit - 1))
                for index in range(limit)
            ))
            visible_records = tuple(projection.records[index] for index in indexes)
        else:
            visible_records = projection.records
        payload["records"] = visible_records
        if truncated:
            payload["recent_records"] = projection.records[-100:]
        payload["records_total"] = len(projection.records)
        payload["records_truncated"] = truncated
        payload["indicator_projection"] = {
            "materialized": False,
            "snapshot_hash": snapshot_hash,
            "basis": basis,
            "indicator_schema_version": "price-indicators.v2",
            "indicator_registry_hash": indicator_registry_hash(),
            "definitions": indicator_definitions_payload(),
        }
        payload["classifications"] = self._classifications.memberships(canonical_code, as_of=end)
        payload["artifact"]["download_url"] = api_path("/signal-lab/prices/download") + "?" + urlencode({
            "instrument": instrument,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "basis": basis,
            "snapshot": snapshot_hash,
        })
        return payload

    def download(
        self,
        instrument: str,
        *,
        start: date,
        end: date,
        basis: str,
        snapshot_hash: str | None = None,
    ) -> tuple[bytes, str]:
        if start > end:
            raise ValueError("start must not be after end")
        payload, projection = self._cached_projection(
            instrument, start=start, end=end, basis=basis,
            snapshot_hash=snapshot_hash,
        )
        if projection is None:
            raise FileNotFoundError("cached price history is unavailable")
        canonical = payload["instrument"]["canonical_code"]
        filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", canonical).strip("_") or "price-history"
        return projection.frame.to_csv(index=False).encode("utf-8-sig"), f"{filename}-{basis}.csv"

    def _cached_projection(
        self,
        instrument_query: str,
        *,
        start: date,
        end: date,
        basis: str,
        snapshot_hash: str | None = None,
    ) -> tuple[dict[str, Any], CachedPriceProjection | None]:
        matches = resolve_instrument(self._database, instrument_query)
        request = {
            "command": "prices.query",
            "instrument": instrument_query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "basis": basis,
            "cache_only": True,
            "snapshot_hash": snapshot_hash,
        }
        if len(matches) > 1:
            return history_envelope(
                "ambiguous",
                request,
                instrument={
                    "query": instrument_query,
                    "candidates": [instrument_payload(item) for item in matches],
                },
                warnings=["instrument name matches multiple assets; use a canonical code"],
            ), None
        if not matches:
            return history_envelope(
                "error",
                request,
                warnings=[f"instrument could not be resolved: {instrument_query}"],
            ), None
        instrument = matches[0]
        try:
            selected_snapshot_hash = select_daily_snapshot_hash(
                self._prices,
                instrument,
                start=start,
                end=end,
                requested_hash=snapshot_hash,
            )
        except ValueError as exc:
            return history_envelope(
                "error",
                request,
                instrument=instrument_payload(instrument),
                warnings=[str(exc)],
            ), None
        if selected_snapshot_hash is None:
            return history_envelope(
                "error",
                request,
                instrument=instrument_payload(instrument),
                warnings=["cache contains no snapshot covering the requested range"],
            ), None
        registry_hash = indicator_registry_hash()
        catalog_hash = sha256(canonical_json_bytes(instrument_payload(instrument))).hexdigest()
        key = (
            _PRICE_PROJECTION_VERSION,
            self._database.cache_key,
            instrument.canonical_code,
            selected_snapshot_hash,
            start.isoformat(),
            end.isoformat(),
            basis,
            registry_hash,
            catalog_hash,
        )
        projection = self._projection_cache.get_or_create(
            key,
            lambda: build_price_projection(
                self._prices,
                instrument,
                snapshot_hash=selected_snapshot_hash,
                start=start,
                end=end,
                basis=basis,
            ),
        )
        payload = history_envelope(
            projection.status,
            request,
            instrument=projection.instrument,
            coverage=projection.coverage,
            source=projection.source,
            price_basis=projection.price_basis,
            artifact=dict(projection.artifact),
            warnings=list(projection.warnings),
        )
        return payload, projection
