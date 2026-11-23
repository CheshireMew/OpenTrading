from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any, Literal, cast

import pandas as pd

from app.domain.immutability import deep_freeze
from app.infra.persistence.market.history.price_artifacts import snapshot_frame
from app.services.market.history.catalog import instrument_payload
from app.domain.market.history.coverage import coverage_report
from app.domain.market.history.indicators import indicator_frame
from app.infra.persistence.market.history.price_repository import PriceRepository
from app.services.market.history.price_cache import CachedPriceProjection


def select_daily_snapshot_hash(
    prices: PriceRepository,
    instrument: Any,
    *,
    start: date,
    end: date,
    requested_hash: str | None,
) -> str | None:
    if requested_hash is None:
        return prices.find_cached_price_snapshot_hash(
            instrument.canonical_code, start, end, None,
        )
    try:
        selected = prices.load_price_snapshot(
            instrument.canonical_code,
            requested_hash,
            timeframe="1d",
        )
    except FileNotFoundError:
        selected = None
    if (
        selected is None
        or selected.requested_start > start
        or selected.requested_end < end
    ):
        raise ValueError("the selected daily snapshot does not cover the requested range")
    return requested_hash


def build_price_projection(
    prices: PriceRepository,
    instrument: Any,
    *,
    snapshot_hash: str,
    start: date,
    end: date,
    basis: str,
) -> CachedPriceProjection:
    cached = prices.load_price_snapshot(instrument.canonical_code, snapshot_hash)
    bars = tuple(bar for bar in cached.bars if start <= bar.observation_date <= end)
    coverage, _ = coverage_report(instrument, bars, start, end)
    projection = replace(
        cached,
        requested_start=start,
        requested_end=end,
        bars=bars,
        coverage_status="complete" if coverage["complete"] else "partial",
    )
    frame = snapshot_frame(projection)
    indicators = indicator_frame(
        projection, cast(Literal["raw", "adjusted"], basis),
    ).drop(columns=["date", "basis", "price", "snapshot_hash"], errors="ignore")
    frame = frame.merge(indicators, on="observed_at", how="left")
    frame["display_price"] = frame["adjusted_close"] if basis == "adjusted" else frame["close"]
    records = tuple(cast(dict[str, Any], deep_freeze(item)) for item in _frame_records(frame))
    return CachedPriceProjection(
        frame=frame,
        records=records,
        status="ok" if coverage["complete"] else "partial",
        instrument=cast(dict[str, Any], deep_freeze(instrument_payload(instrument))),
        coverage=cast(dict[str, Any], deep_freeze(coverage)),
        source=cast(dict[str, Any], deep_freeze({
            "selected": cached.provider,
            "provider_symbol": cached.provider_symbol,
            "retrieved_at": cached.retrieved_at.isoformat(),
            "source_snapshot_hash": cached.source_snapshot_hash,
            "attempts": [{
                "provider": cached.provider,
                "status": "cache",
                "records": len(bars),
                "attempt_scope": "current_request",
            }],
        })),
        price_basis=basis,
        artifact=cast(dict[str, Any], deep_freeze({
            "snapshot_hash": cached.snapshot_hash,
            "materialized": False,
            "exports": [],
        })),
        warnings=tuple(cached.metadata.get("provider_warnings", [])),
    )


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    normalized = frame.copy()
    for column in normalized.columns:
        values = normalized[column]
        if isinstance(values.dtype, pd.DatetimeTZDtype) or pd.api.types.is_datetime64_any_dtype(values.dtype):
            normalized[column] = values.map(
                lambda value: None if pd.isna(value) else cast(pd.Timestamp, value).isoformat()
            )
        elif values.dtype == object:
            normalized[column] = values.map(
                lambda value: value.isoformat() if isinstance(value, date) else value
            )
    normalized = normalized.astype(object).where(pd.notna(normalized), None)
    return cast(list[dict[str, Any]], normalized.to_dict("records"))
