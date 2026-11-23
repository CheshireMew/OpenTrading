from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import logging
from pathlib import Path
from typing import Any, Callable

from signal_lab.config import SignalLabConfig
from signal_lab.data.http import HttpTransport
from signal_lab.data.snapshots import RawSnapshotStore
from signal_lab.prices.coverage import coverage_report
from signal_lab.prices.history_contract import empty_coverage
from signal_lab.prices.models import Instrument, PriceBar, PriceSnapshot
from signal_lab.prices.providers import (
    PriceProvider,
    provider_order,
    provider_symbol,
)
from signal_lab.storage.database import SignalLabDatabase
from signal_lab.storage.price_repository import PriceRepository


LOGGER = logging.getLogger("signal_lab.prices")


class PriceAcquirer:
    """Acquire or project one immutable price snapshot from cache/provider evidence."""

    def __init__(
        self,
        root: Path,
        config: SignalLabConfig,
        database: SignalLabDatabase,
        prices: PriceRepository,
        provider_builder: Callable[..., PriceProvider],
        transport: HttpTransport,
    ) -> None:
        self.root = root
        self.config = config
        self._database = database
        self._prices = prices
        self.provider_builder = provider_builder
        self.transport = transport

    def obtain(
        self,
        instrument: Instrument,
        start: date,
        end: date,
        *,
        refresh: bool,
        cache_only: bool,
        explicit_provider: str | None,
    ) -> tuple[PriceSnapshot | None, dict[str, Any], list[dict[str, Any]], list[str]]:
        attempts: list[dict[str, Any]] = []
        warnings: list[str] = []
        if not refresh:
            cached = self._prices.find_cached_price_snapshot(
                instrument.canonical_code, start, end, explicit_provider,
            )
            if cached:
                subset = tuple(bar for bar in cached.bars if start <= bar.observation_date <= end)
                coverage, issues = coverage_report(instrument, subset, start, end)
                attempts.extend(
                    {**attempt, "attempt_scope": "origin_fetch"}
                    for attempt in cached.metadata.get("source_attempts", [])
                )
                attempts.append({
                    "provider": cached.provider,
                    "status": "cache",
                    "records": len(subset),
                    "attempt_scope": "current_request",
                })
                cached_warnings = list(cached.metadata.get("provider_warnings", []))
                if (
                    cached.requested_start == start
                    and cached.requested_end == end
                    and len(subset) == len(cached.bars)
                ):
                    return cached, coverage, attempts, list(dict.fromkeys([
                        *cached_warnings, *coverage.get("method_notes", []),
                    ]))
                derived = PriceSnapshot(
                    instrument=instrument,
                    timeframe="1d",
                    provider=cached.provider,
                    provider_symbol=cached.provider_symbol,
                    requested_start=start,
                    requested_end=end,
                    retrieved_at=cached.retrieved_at,
                    bars=subset,
                    source_snapshot_hash=cached.source_snapshot_hash,
                    price_basis=cached.price_basis,
                    coverage_status="complete" if coverage["complete"] else "partial",
                    metadata={**cached.metadata, "derived_from_cache": cached.snapshot_hash},
                )
                self._prices.save_price_snapshot(derived, coverage_issues=issues)
                return derived, coverage, attempts, list(dict.fromkeys([
                    *cached_warnings, *coverage.get("method_notes", []),
                ]))
        if cache_only:
            return None, empty_coverage(start, end), attempts, [
                "cache contains no snapshot covering the requested range"
            ]

        candidates: list[tuple[PriceSnapshot, dict[str, Any], list[dict[str, Any]]]] = []
        for name in provider_order(instrument, explicit_provider):
            try:
                mapped_symbol = provider_symbol(self._database, instrument, name)
                LOGGER.info(
                    "fetching %s from %s as %s",
                    instrument.canonical_code,
                    name,
                    mapped_symbol,
                )
                adapter = self.provider_builder(
                    name,
                    fred_api_key=self.config.fred_api_key,
                    tiingo_token=self.config.tiingo_api_token,
                    transport=self.transport,
                )
                fetched = adapter.fetch(instrument, mapped_symbol, start, end)
                raw = RawSnapshotStore(self.root, self.config).save(
                    name,
                    f"prices-{instrument.canonical_code}-1d",
                    fetched.payload,
                    datetime.now(timezone.utc),
                )
                provider_bars = tuple(
                    bar for bar in fetched.bars if start <= bar.observation_date <= end
                )
                bars, duplicate_dates = normalize_daily_bars(provider_bars)
                coverage, issues = coverage_report(
                    instrument, bars, start, end, duplicate_dates=duplicate_dates,
                )
                issues.extend(
                    {"type": "provider_anomaly", "date": None, "detail": warning}
                    for warning in fetched.warnings
                )
                snapshot = PriceSnapshot(
                    instrument=instrument,
                    timeframe="1d",
                    provider=name,
                    provider_symbol=mapped_symbol,
                    requested_start=start,
                    requested_end=end,
                    retrieved_at=raw.retrieved_at,
                    bars=bars,
                    source_snapshot_hash=raw.snapshot_hash,
                    price_basis="both",
                    coverage_status="complete" if coverage["complete"] else "partial",
                    metadata={
                        "provider_warnings": list(fetched.warnings),
                        "source_snapshot_hashes": [raw.snapshot_hash],
                        "source_acquisition_ids": [raw.acquisition_id],
                    },
                )
                candidates.append((snapshot, coverage, issues))
                attempts.append({
                    "provider": name,
                    "provider_symbol": mapped_symbol,
                    "status": "complete" if coverage["complete"] else "partial",
                    "records": len(bars),
                    "missing_dates": len(coverage["missing_dates"]),
                    "duplicate_dates": len(duplicate_dates),
                    "source_snapshot_hash": raw.snapshot_hash,
                })
                warnings.extend(fetched.warnings)
                if coverage["complete"]:
                    break
            except Exception as exc:
                LOGGER.warning(
                    "provider %s failed for %s: %s",
                    name,
                    instrument.canonical_code,
                    exc,
                )
                attempts.append({"provider": name, "status": "error", "error": str(exc)})
        if not candidates:
            return None, empty_coverage(start, end), attempts, warnings
        snapshot, coverage, issues = min(
            candidates,
            key=lambda item: (len(item[1]["missing_dates"]), -item[1]["actual_records"]),
        )
        snapshot = replace(
            snapshot,
            metadata={**snapshot.metadata, "source_attempts": list(attempts)},
        )
        self._prices.save_price_snapshot(snapshot, coverage_issues=issues)
        warnings.extend(coverage.get("method_notes", []))
        return snapshot, coverage, attempts, list(dict.fromkeys(warnings))


def normalize_daily_bars(
    bars: tuple[PriceBar, ...],
) -> tuple[tuple[PriceBar, ...], tuple[date, ...]]:
    grouped: dict[date, list[PriceBar]] = {}
    for bar in sorted(bars, key=lambda item: item.observed_at):
        grouped.setdefault(bar.observation_date, []).append(bar)
    duplicate_dates = tuple(sorted(day for day, items in grouped.items() if len(items) > 1))
    normalized = tuple(grouped[day][-1] for day in sorted(grouped))
    return normalized, duplicate_dates
