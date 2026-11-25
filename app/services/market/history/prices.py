from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha256
import logging
from typing import Any, Callable, Literal

import pandas as pd

from config.market_data import MarketDataConfig
from app.infra.market_data.http import HttpTransport, UrllibJsonTransport
from app.services.market.history.acquisition import PriceAcquirer
from app.domain.market.history.analytics import calculate_analytics
from app.infra.persistence.market.history.price_artifacts import PriceArtifactStore
from app.services.market.history.catalog import instrument_payload, resolve_instrument
from app.domain.market.history.coverage import coverage_report, resolve_date_range
from app.contracts.market_data import empty_coverage, history_envelope
from app.domain.market.history.models import Instrument, PriceSnapshot
from app.infra.market_data.providers import PriceProvider, make_provider
from app.infra.persistence.market.history.database import MarketHistoryDatabase
from app.infra.persistence.market.history.price_repository import PriceRepository


LOGGER = logging.getLogger("app.domain.market.history")


class PriceService:
    def __init__(
        self,
        database: MarketHistoryDatabase,
        config: MarketDataConfig,
        *,
        provider_builder: Callable[..., PriceProvider] = make_provider,
        transport: HttpTransport | None = None,
    ) -> None:
        self.root = database.root
        self._database = database
        self._prices = PriceRepository(self._database)
        http_transport = transport or UrllibJsonTransport()
        self.artifacts = PriceArtifactStore(self.root, config)
        self._acquirer = PriceAcquirer(
            self.root,
            config,
            self._database,
            self._prices,
            provider_builder,
            http_transport,
        )

    def daily_snapshot(self, instrument_query: str, *, start: date, end: date) -> PriceSnapshot:
        """Reuse daily acquisition and cached evidence without building exports or analytics."""
        if start > end:
            raise ValueError("start must not be after end")
        matches = resolve_instrument(self._database, instrument_query)
        if len(matches) != 1:
            raise ValueError(f"daily instrument could not be resolved: {instrument_query}")
        instrument = matches[0]
        snapshot, _, _, warnings = self._obtain_snapshot(
            instrument, start, end, refresh=False, cache_only=False,
            # FRED FX observations have no intraday OHLC. Keep those available
            # to macro research, rather than presenting them as chart candles.
            explicit_provider="yfinance" if instrument.asset_class == "fx" else None,
        )
        if snapshot is None:
            raise ValueError("; ".join(warnings) or f"daily history is unavailable: {instrument_query}")
        return snapshot

    def history(
        self,
        instrument_query: str,
        *,
        period: str | None = None,
        start: date | None = None,
        end: date | None = None,
        basis: Literal["raw", "adjusted", "both"] | None = None,
        refresh: bool = False,
        cache_only: bool = False,
        provider: str | None = None,
        export: Literal["csv", "json"] | None = None,
        now: datetime | None = None,
        include_analytics: bool = True,
    ) -> dict[str, Any]:
        request = {
            "command": "prices.history", "instrument": instrument_query,
            "period": period, "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None, "timeframe": "1d",
            "basis": basis, "refresh": refresh, "cache_only": cache_only,
            "provider": provider, "export": export,
        }
        try:
            if refresh and cache_only:
                raise ValueError("--refresh and --cache-only are mutually exclusive")
            matches = resolve_instrument(self._database, instrument_query)
            if len(matches) > 1:
                return _envelope(
                    status="ambiguous", request=request,
                    instrument={"query": instrument_query, "candidates": [instrument_payload(item) for item in matches]},
                    warnings=["instrument name matches multiple assets; use a canonical code"],
                )
            if not matches:
                return _error_envelope(request, f"instrument could not be resolved: {instrument_query}")
            instrument = matches[0]
            requested_start, requested_end = resolve_date_range(
                instrument, period=period, start=start, end=end, now=now,
            )
            effective_basis = basis or ("adjusted" if instrument.asset_class in {"stock", "etf"} else "raw")
            snapshot, coverage, attempts, warnings = self._obtain_snapshot(
                instrument, requested_start, requested_end,
                refresh=refresh, cache_only=cache_only, explicit_provider=provider,
            )
            if snapshot is None:
                return _envelope(
                    status="error", request=request, instrument=instrument_payload(instrument),
                    coverage=empty_coverage(requested_start, requested_end),
                    source={"selected": None, "attempts": attempts},
                    warnings=warnings or ["no provider returned usable data"],
                )
            if include_analytics:
                price_basis, statistics, indicators = calculate_analytics(snapshot, effective_basis)
            else:
                price_basis, statistics, indicators = {
                    "requested": effective_basis,
                    "primary": effective_basis,
                    "available": ["raw", "adjusted"],
                }, None, None
            artifact = self.artifacts.write_snapshot(snapshot, export=export)
            status = "ok" if coverage["complete"] else "partial"
            return _envelope(
                status=status, request={**request, "resolved_start": requested_start.isoformat(), "resolved_end": requested_end.isoformat()},
                instrument=instrument_payload(instrument), coverage=coverage,
                source={
                    "selected": snapshot.provider, "provider_symbol": snapshot.provider_symbol,
                    "retrieved_at": snapshot.retrieved_at.isoformat(),
                    "source_snapshot_hash": snapshot.source_snapshot_hash,
                    "attempts": attempts,
                },
                price_basis=price_basis, statistics=statistics, indicators=indicators,
                artifact=artifact, warnings=warnings,
            )
        except ValueError as exc:
            LOGGER.warning("price history request rejected for %s: %s", instrument_query, exc)
            return _error_envelope(request, str(exc))
        except Exception as exc:
            LOGGER.exception("price history failed for %s", instrument_query)
            return _error_envelope(request, str(exc))

    def update(
        self,
        instrument_query: str,
        *,
        end: date | None = None,
        start: date | None = None,
        basis: Literal["raw", "adjusted", "both"] | None = None,
        provider: str | None = None,
        export: Literal["csv", "json"] | None = None,
        overlap_days: int = 14,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Extend the current immutable history with a verified overlapping tail."""

        request = {
            "command": "prices.update",
            "instrument": instrument_query,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "basis": basis,
            "provider": provider,
            "export": export,
            "overlap_days": overlap_days,
            "timeframe": "1d",
        }
        try:
            if overlap_days < 1 or overlap_days > 366:
                raise ValueError("overlap_days must be between 1 and 366")
            matches = resolve_instrument(self._database, instrument_query)
            if len(matches) > 1:
                return _envelope(
                    status="ambiguous",
                    request=request,
                    instrument={
                        "query": instrument_query,
                        "candidates": [instrument_payload(item) for item in matches],
                    },
                    warnings=["instrument name matches multiple assets; use a canonical code"],
                )
            if not matches:
                return _error_envelope(request, f"instrument could not be resolved: {instrument_query}")
            instrument = matches[0]
            effective_end = end or resolve_date_range(
                instrument, period="1mo", start=None, end=None, now=now,
            )[1]
            try:
                baseline = self._prices.load_price_snapshot(
                    instrument.canonical_code, timeframe="1d",
                )
            except FileNotFoundError:
                if start is None:
                    raise ValueError("the first update requires --start") from None
                result = self.history(
                    instrument_query,
                    start=start,
                    end=effective_end,
                    basis=basis,
                    refresh=True,
                    provider=provider,
                    export=export,
                    now=now,
                )
                result["request"] = request
                return result
            if effective_end < baseline.requested_start:
                raise ValueError("update end must not precede the current snapshot")
            selected_provider = provider or baseline.provider
            if selected_provider != baseline.provider:
                result = self.history(
                    instrument_query,
                    start=baseline.requested_start,
                    end=effective_end,
                    basis=basis,
                    refresh=True,
                    provider=selected_provider,
                    export=export,
                    now=now,
                )
                result["request"] = request
                return result
            last_date = baseline.actual_end or baseline.requested_end
            overlap_start = max(
                baseline.requested_start,
                last_date - timedelta(days=overlap_days - 1),
            )
            tail, _, attempts, warnings = self._obtain_snapshot(
                instrument,
                overlap_start,
                effective_end,
                refresh=True,
                cache_only=False,
                explicit_provider=selected_provider,
            )
            if tail is None:
                return _envelope(
                    status="error",
                    request=request,
                    instrument=instrument_payload(instrument),
                    coverage=empty_coverage(baseline.requested_start, effective_end),
                    source={"selected": None, "attempts": attempts},
                    warnings=warnings or ["no provider returned an incremental tail"],
                )
            merged = {bar.observation_date: bar for bar in baseline.bars}
            merged.update({bar.observation_date: bar for bar in tail.bars})
            bars = tuple(merged[day] for day in sorted(merged) if day <= effective_end)
            coverage, issues = coverage_report(
                instrument, bars, baseline.requested_start, effective_end,
            )
            source_hashes = list(dict.fromkeys([
                *baseline.metadata.get("source_snapshot_hashes", [baseline.source_snapshot_hash]),
                *tail.metadata.get("source_snapshot_hashes", [tail.source_snapshot_hash]),
            ]))
            source_acquisition_ids = list(dict.fromkeys([
                *baseline.metadata.get("source_acquisition_ids", []),
                *tail.metadata.get("source_acquisition_ids", []),
            ]))
            composite_source_hash = sha256(
                ("signal-lab.incremental.v1|" + "|".join(source_hashes)).encode("utf-8")
            ).hexdigest()
            snapshot = PriceSnapshot(
                instrument=instrument,
                timeframe="1d",
                provider=baseline.provider,
                provider_symbol=baseline.provider_symbol,
                requested_start=baseline.requested_start,
                requested_end=effective_end,
                retrieved_at=tail.retrieved_at,
                bars=bars,
                source_snapshot_hash=composite_source_hash,
                price_basis=baseline.price_basis,
                coverage_status="complete" if coverage["complete"] else "partial",
                metadata={
                    **baseline.metadata,
                    "parent_snapshot_hash": baseline.snapshot_hash,
                    "incremental_tail_snapshot_hash": tail.snapshot_hash,
                    "update_overlap_start": overlap_start.isoformat(),
                    "source_snapshot_hashes": source_hashes,
                    "source_acquisition_ids": source_acquisition_ids,
                    "source_attempts": attempts,
                    "provider_warnings": warnings,
                },
            )
            self._prices.save_price_snapshot(snapshot, coverage_issues=issues)
            effective_basis = basis or (
                "adjusted" if instrument.asset_class in {"stock", "etf"} else "raw"
            )
            price_basis, statistics, indicators = calculate_analytics(snapshot, effective_basis)
            artifact = self.artifacts.write_snapshot(snapshot, export=export)
            return _envelope(
                status="ok" if coverage["complete"] else "partial",
                request={
                    **request,
                    "resolved_start": baseline.requested_start.isoformat(),
                    "resolved_end": effective_end.isoformat(),
                },
                instrument=instrument_payload(instrument),
                coverage=coverage,
                source={
                    "selected": snapshot.provider,
                    "provider_symbol": snapshot.provider_symbol,
                    "retrieved_at": snapshot.retrieved_at.isoformat(),
                    "source_snapshot_hash": snapshot.source_snapshot_hash,
                    "source_snapshot_hashes": source_hashes,
                    "attempts": attempts,
                },
                price_basis=price_basis,
                statistics=statistics,
                indicators=indicators,
                artifact=artifact,
                warnings=list(dict.fromkeys(warnings + coverage.get("method_notes", []))),
            )
        except Exception as exc:
            LOGGER.exception("price update failed for %s", instrument_query)
            return _error_envelope(request, str(exc))

    def point(
        self,
        instrument_query: str,
        observation_date: date,
        *,
        policy: Literal["exact", "on-or-before"] = "on-or-before",
        refresh: bool = False,
        cache_only: bool = False,
        provider: str | None = None,
        export: Literal["csv", "json"] | None = None,
    ) -> dict[str, Any]:
        request = {
            "command": "prices.point", "instrument": instrument_query,
            "date": observation_date.isoformat(), "policy": policy,
            "refresh": refresh, "cache_only": cache_only, "provider": provider, "export": export,
        }
        matches = resolve_instrument(self._database, instrument_query)
        if len(matches) != 1:
            result = self.history(
                instrument_query, start=observation_date, end=observation_date,
                refresh=refresh, cache_only=cache_only, provider=provider, export=export,
            )
            result["request"] = request
            return result

        instrument = matches[0]
        starts = [observation_date] if policy == "exact" else _point_window_starts(
            instrument, observation_date,
        )
        accumulated_attempts: list[dict[str, Any]] = []
        accumulated_warnings: list[str] = []
        last_result: dict[str, Any] | None = None
        for window_start in starts:
            candidate = self.history(
                instrument_query, start=window_start, end=observation_date,
                refresh=refresh, cache_only=cache_only, provider=provider, export=export,
            )
            last_result = candidate
            source = candidate.get("source")
            if isinstance(source, dict):
                for attempt in source.get("attempts", []):
                    annotated = dict(attempt)
                    if annotated.get("attempt_scope") != "origin_fetch":
                        annotated["lookback_start"] = window_start.isoformat()
                    accumulated_attempts.append(annotated)
            accumulated_warnings.extend(candidate.get("warnings", []))
            artifact = candidate.get("artifact")
            if candidate["status"] not in {"ok", "partial"} or not artifact or artifact.get("rows", 0) == 0:
                continue
            frame = self.artifacts.read_frame(artifact["path"]).sort_values("date")
            frame["date"] = pd.to_datetime(frame["date"]).dt.date
            exact = frame.loc[frame["date"] == observation_date]
            eligible = frame.loc[frame["date"] <= observation_date]
            selected = exact.iloc[-1] if not exact.empty else None
            if selected is None and policy == "on-or-before" and not eligible.empty:
                selected = eligible.iloc[-1]
            if selected is None:
                continue
            candidate["request"] = request
            if isinstance(candidate.get("source"), dict):
                candidate["source"]["attempts"] = _unique_attempts(accumulated_attempts)
            candidate["warnings"] = list(dict.fromkeys(accumulated_warnings))
            candidate["statistics"] = {
                "requested_date": observation_date.isoformat(),
                "matched_date": selected["date"].isoformat(),
                "open": float(selected["open"]), "high": float(selected["high"]),
                "low": float(selected["low"]), "close": float(selected["close"]),
                "adjusted_close": float(selected["adjusted_close"]),
                "volume": float(selected["volume"]) if pd.notna(selected["volume"]) else None,
            }
            candidate["indicators"] = None
            return candidate

        result = last_result or _error_envelope(request, "no price satisfies the requested point policy")
        result["request"] = request
        result["status"] = "error"
        result["statistics"] = None
        result["indicators"] = None
        if isinstance(result.get("source"), dict):
            result["source"]["attempts"] = _unique_attempts(accumulated_attempts)
        result["warnings"] = list(dict.fromkeys([
            *accumulated_warnings, "no price satisfies the requested point policy",
        ]))
        return result

    def compare(
        self,
        instrument_queries: list[str],
        *,
        period: str | None = None,
        start: date | None = None,
        end: date | None = None,
        refresh: bool = False,
        cache_only: bool = False,
        provider: str | None = None,
        export: Literal["csv", "json"] | None = None,
    ) -> dict[str, Any]:
        request = {
            "command": "prices.compare", "instruments": instrument_queries,
            "period": period, "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None, "refresh": refresh,
            "cache_only": cache_only, "provider": provider, "export": export,
        }
        if len(instrument_queries) < 2:
            return _error_envelope(request, "prices compare requires at least two instruments")
        histories = [
            self.history(
                item, period=period, start=start, end=end, refresh=refresh,
                cache_only=cache_only, provider=provider,
            )
            for item in instrument_queries
        ]
        if any(item["status"] not in {"ok", "partial"} for item in histories):
            return _envelope(
                status="error", request=request,
                instrument=[item["instrument"] for item in histories],
                source={"attempts": [item["source"] for item in histories]},
                warnings=["one or more instruments could not be loaded"],
            )
        series = {}
        for item in histories:
            code = item["instrument"]["canonical_code"]
            frame = self.artifacts.read_frame(item["artifact"]["path"])
            instrument_payload_item = item["instrument"]
            adjusted = instrument_payload_item["asset_class"] in {"stock", "etf"}
            values = {
                pd.Timestamp(row["date"]).date(): (
                    float(row["adjusted_close"]) if adjusted else float(row["close"])
                )
                for _, row in frame.iterrows()
            }
            series[code] = pd.Series(values, dtype="float64")
        frame = pd.DataFrame(series).dropna(how="any").sort_index()
        if frame.empty:
            return _error_envelope(request, "instruments have no common actual dates")
        normalized = frame.divide(frame.iloc[0]).multiply(100.0)
        artifact = self.artifacts.write_comparison(normalized, export=export)
        statuses = [item["status"] for item in histories]
        return _envelope(
            status="ok" if all(item == "ok" for item in statuses) else "partial",
            request=request, instrument=[item["instrument"] for item in histories],
            coverage={
                "requested_start": histories[0]["coverage"]["requested_start"],
                "requested_end": histories[0]["coverage"]["requested_end"],
                "actual_start": frame.index[0].isoformat(), "actual_end": frame.index[-1].isoformat(),
                "expected_trading_days": None, "actual_records": len(frame), "missing_dates": [],
                "complete": all(item == "ok" for item in statuses),
                "incomplete_reasons": ["one or more component histories are partial"] if "partial" in statuses else [],
                "method_notes": ["common actual dates only; no cross-market forward fill"],
            },
            source={"components": [item["source"] for item in histories]},
            price_basis={"primary": "asset_default", "normalized_first_value": 100},
            statistics={
                code: {
                    "first": float(normalized[code].iloc[0]),
                    "last": float(normalized[code].iloc[-1]),
                    "period_return": float(frame[code].iloc[-1] / frame[code].iloc[0] - 1),
                }
                for code in normalized.columns
            },
            indicators=None, artifact=artifact,
            warnings=[warning for item in histories for warning in item["warnings"]],
        )

    def _obtain_snapshot(
        self,
        instrument: Instrument,
        start: date,
        end: date,
        *,
        refresh: bool,
        cache_only: bool,
        explicit_provider: str | None,
    ) -> tuple[PriceSnapshot | None, dict[str, Any], list[dict[str, Any]], list[str]]:
        return self._acquirer.obtain(
            instrument,
            start,
            end,
            refresh=refresh,
            cache_only=cache_only,
            explicit_provider=explicit_provider,
        )

def _point_window_starts(instrument: Instrument, observation_date: date) -> list[date]:
    candidates = [
        observation_date - timedelta(days=14),
        observation_date - timedelta(days=90),
        observation_date - timedelta(days=365),
        observation_date - timedelta(days=3650),
        instrument.listed_on or date(1900, 1, 1),
    ]
    starts: list[date] = []
    for candidate in candidates:
        bounded = min(candidate, observation_date)
        if bounded not in starts:
            starts.append(bounded)
    return starts


def _unique_attempts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for attempt in attempts:
        key = repr(sorted(attempt.items()))
        if key not in seen:
            seen.add(key)
            unique.append(attempt)
    return unique


_envelope = history_envelope


def _error_envelope(request: dict[str, Any], message: str) -> dict[str, Any]:
    return _envelope(status="error", request=request, warnings=[message])
