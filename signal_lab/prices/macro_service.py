from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from signal_lab.config import SignalLabConfig
from signal_lab.data.fred_client import FredObservationClient
from signal_lab.data.http import HttpTransport, UrllibJsonTransport
from signal_lab.data.snapshots import RawSnapshotStore
from signal_lab.prices.catalog import instrument_payload, resolve_instrument
from signal_lab.prices.coverage import resolve_date_range
from signal_lab.prices.history_contract import empty_coverage, history_envelope
from signal_lab.storage.artifacts import storage_item
from signal_lab.storage.capacity import ManagedStorage
from signal_lab.storage.database import SignalLabDatabase
from signal_lab.storage.macro_repository import MacroHistoryRepository
from signal_lab.structured_data import canonical_json_bytes


MACRO_PARQUET_SCHEMA_VERSION = "macro-values.v2"


class MacroService:
    def __init__(
        self,
        root: Path,
        config: SignalLabConfig,
        transport: HttpTransport | None = None,
    ) -> None:
        self.root = root.expanduser().resolve()
        self.config = config
        self._database = SignalLabDatabase(self.root)
        self._history = MacroHistoryRepository(self._database)
        self._transport = transport or UrllibJsonTransport()
        self._fred = FredObservationClient(config.fred_api_key, self._transport)

    def history(
        self,
        series_query: str,
        *,
        period: str | None = None,
        start: date | None = None,
        end: date | None = None,
        refresh: bool = False,
        cache_only: bool = False,
        export: Literal["csv", "json"] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        request = {
            "command": "macro.history", "series": series_query, "period": period,
            "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
            "refresh": refresh, "cache_only": cache_only, "provider": "fred", "export": export,
        }
        try:
            if refresh and cache_only:
                raise ValueError("--refresh and --cache-only are mutually exclusive")
            matches = resolve_instrument(self._database, series_query)
            matches = [item for item in matches if item.asset_class == "macro"]
            if not matches:
                return _envelope("error", request, warnings=[f"macro series could not be resolved: {series_query}"])
            if len(matches) > 1:
                return _envelope(
                    "ambiguous", request,
                    instrument={"query": series_query, "candidates": [instrument_payload(item) for item in matches]},
                    warnings=["macro series name is ambiguous; use FRED:<series_id>"],
                )
            instrument = matches[0]
            requested_start, requested_end = resolve_date_range(
                instrument, period=period, start=start, end=end, now=now,
            )
            series_id = instrument.canonical_code.removeprefix("FRED:")
            cached = None if refresh else self._history.load_macro_history(
                series_id, covering_start=requested_start, covering_end=requested_end,
            )
            attempts: list[dict[str, Any]] = []
            if cached:
                values = [
                    item for item in cached["values"]
                    if requested_start <= item["date"] <= requested_end
                ]
                source_hash = cached["source_snapshot_hash"]
                retrieved_at = datetime.fromisoformat(cached["retrieved_at"])
                official_missing_dates = [
                    date.fromisoformat(item) for item in cached["metadata"].get("official_missing_dates", [])
                    if requested_start <= date.fromisoformat(item) <= requested_end
                ]
                origin_attempts = list(cached["metadata"].get("source_attempts", []))
                attempts.extend(
                    {**attempt, "attempt_scope": "origin_fetch"}
                    for attempt in origin_attempts
                )
                attempts.append(
                    {
                        "provider": "fred", "status": "cache", "records": len(values),
                        "attempt_scope": "current_request",
                    }
                )
            elif cache_only:
                return _envelope(
                    "error", request, instrument=instrument_payload(instrument),
                    coverage=empty_coverage(requested_start, requested_end),
                    source={"selected": None, "attempts": []},
                    warnings=["cache contains no macro snapshot covering the requested range"],
                )
            else:
                payload, transport_name = self._fetch_fred(series_id, requested_start, requested_end)
                raw = RawSnapshotStore(self.root, self.config).save(
                    "fred", f"macro-history-{series_id}", payload, datetime.now(timezone.utc),
                )
                values = _parse_values(payload)
                official_missing_dates = _official_missing_dates(payload)
                source_hash = raw.snapshot_hash
                retrieved_at = raw.retrieved_at
                attempts.append(
                    {
                        "provider": "fred", "transport": transport_name, "status": "ok",
                        "records": len(values), "source_snapshot_hash": source_hash,
                    }
                )
                origin_attempts = list(attempts)
            coverage = _macro_coverage(values, official_missing_dates, requested_start, requested_end)
            snapshot_hash = _snapshot_hash(series_id, requested_start, requested_end, source_hash, values)
            self._history.save_macro_history(
                snapshot_hash=snapshot_hash, series_id=series_id, provider="fred",
                requested_start=requested_start, requested_end=requested_end,
                retrieved_at=retrieved_at, source_snapshot_hash=source_hash, values=values,
                metadata={
                    "official_missing_dates": [item.isoformat() for item in official_missing_dates],
                    "source_attempts": origin_attempts,
                    "source_acquisition_ids": [raw.acquisition_id] if not cached else list(
                        cached["metadata"].get("source_acquisition_ids", [])
                    ),
                },
            )
            artifact = self._write_artifact(series_id, snapshot_hash, values, export)
            statistics = _statistics(values)
            return _envelope(
                "ok" if coverage["complete"] else "partial", request,
                instrument=instrument_payload(instrument), coverage=coverage,
                source={
                    "selected": "fred", "provider_symbol": series_id,
                    "retrieved_at": retrieved_at.isoformat(),
                    "source_snapshot_hash": source_hash, "attempts": attempts,
                },
                price_basis={"requested": "value", "primary": "value", "available": ["value"]},
                statistics=statistics, indicators=None, artifact=artifact,
                warnings=coverage["method_notes"],
            )
        except Exception as exc:
            return _envelope("error", request, warnings=[str(exc)])

    def _fetch_fred(self, series_id: str, start: date, end: date) -> tuple[dict[str, Any], str]:
        try:
            return self._fred.fetch_latest(series_id, start, end)
        except Exception as exc:
            source = "FRED observations API" if self.config.fred_api_key else "FRED public CSV"
            raise RuntimeError(f"{source} request failed") from exc

    def _write_artifact(
        self,
        series_id: str,
        snapshot_hash: str,
        values: list[dict[str, Any]],
        export: Literal["csv", "json"] | None,
    ) -> dict[str, Any]:
        safe_code = quote(f"FRED:{series_id}", safe=".-@")
        directory = self.root / "exports" / "macro" / safe_code / "1d" / snapshot_hash
        path = directory / "history.parquet"
        export_path = directory / f"history.{export}" if export else None
        frame = pd.DataFrame(values)
        requires_write = not path.exists() or (
            export_path is not None and not export_path.exists()
        )
        if requires_write:
            storage = ManagedStorage(
                self.root,
                maximum_managed_bytes=self.config.max_managed_bytes,
                minimum_free_bytes=self.config.min_free_bytes,
            )
            preflight = storage.preflight(
                "macro-price-artifact",
                estimated_peak_bytes=max(4 * 1024 * 1024, len(values) * 2048 + 8192),
            )
            operation_id = f"macro-{snapshot_hash}-{export or 'parquet'}"
            operation = storage.operation_directory("macro-price-artifact", operation_id)
            storage.begin_operation(
                operation,
                operation_id=operation_id,
                producer="macro-price-artifact",
                preflight=preflight,
            )
            parquet_temporary = operation / "history.parquet.tmp"
            export_temporary = operation / f"history.{export}.tmp" if export else None
            try:
                directory.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    table = pa.Table.from_pandas(frame, preserve_index=False)
                    metadata = dict(table.schema.metadata or {})
                    metadata[b"signal_lab_parquet_schema_version"] = (
                        MACRO_PARQUET_SCHEMA_VERSION.encode("ascii")
                    )
                    metadata[b"signal_lab_snapshot_hash"] = snapshot_hash.encode("ascii")
                    pq.write_table(
                        table.replace_schema_metadata(metadata),
                        parquet_temporary,
                        compression="zstd",
                    )
                    parquet_temporary.replace(path)
                if export_path is not None and not export_path.exists():
                    assert export_temporary is not None
                    if export == "csv":
                        frame.to_csv(export_temporary, index=False)
                    else:
                        frame.to_json(
                            export_temporary,
                            orient="records",
                            date_format="iso",
                            force_ascii=False,
                        )
                    export_temporary.replace(export_path)
                storage.finish_operation(
                    operation,
                    status="published",
                    inventory=[
                        storage_item(candidate, "deliverable")
                        for candidate in (path, export_path)
                        if candidate is not None and candidate.is_file()
                    ],
                )
            except BaseException as exc:
                storage.finish_failure(
                    operation,
                    error=exc,
                    inventory=[
                        storage_item(candidate, artifact_class)
                        for candidate, artifact_class in (
                            (parquet_temporary, "temporary"),
                            (export_temporary, "temporary"),
                            (path, "deliverable"),
                            (export_path, "deliverable"),
                        )
                        if candidate is not None and candidate.is_file()
                    ],
                )
                raise
        existing_metadata = pq.read_schema(path).metadata or {}
        if existing_metadata.get(b"signal_lab_snapshot_hash") != snapshot_hash.encode("ascii"):
            raise ValueError(f"immutable macro artifact metadata mismatch: {path}")
        try:
            pd.testing.assert_frame_equal(
                pd.read_parquet(path).reset_index(drop=True),
                frame.reset_index(drop=True),
                check_dtype=False,
                check_exact=True,
            )
        except AssertionError as exc:
            raise ValueError(f"immutable macro artifact content mismatch: {path}") from exc
        exports = []
        if export_path is not None:
            if export == "csv":
                expected_export = frame.to_csv(index=False).encode("utf-8")
            else:
                expected_export = frame.to_json(
                    orient="records", date_format="iso", force_ascii=False,
                ).encode("utf-8")
            if export_path.read_bytes() != expected_export:
                raise ValueError(f"immutable macro export content mismatch: {export_path}")
            exports.append({"format": export, "path": str(export_path.resolve())})
        digest = sha256(path.read_bytes()).hexdigest()
        version = (pq.read_schema(path).metadata or {}).get(
            b"signal_lab_parquet_schema_version", b"",
        ).decode("ascii")
        return {
            "path": str(path.resolve()), "rows": len(values), "sha256": digest,
            "parquet_schema_version": version, "exports": exports,
        }


def _parse_values(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("FRED response has no observations list")
    values: list[dict[str, Any]] = []
    for row in rows:
        if row.get("value") in {None, "", "."}:
            continue
        values.append(
            {
                "date": date.fromisoformat(row["date"]), "value": float(row["value"]),
                "realtime_start": date.fromisoformat(row["realtime_start"]) if row.get("realtime_start") else None,
                "realtime_end": date.fromisoformat(row["realtime_end"]) if row.get("realtime_end") else None,
            }
        )
    if not values:
        raise ValueError("FRED returned no usable observations")
    values.sort(key=lambda item: str(item["date"]))
    return values


def _official_missing_dates(payload: Any) -> list[date]:
    rows = (payload.get("observations") or []) if isinstance(payload, dict) else []
    return sorted(
        date.fromisoformat(row["date"])
        for row in rows
        if row.get("date") and row.get("value") in {None, "", "."}
    )


def _macro_coverage(
    values: list[dict[str, Any]],
    official_missing_dates: list[date],
    start: date,
    end: date,
) -> dict[str, Any]:
    actual_dates = [item["date"] for item in values]
    reasons = []
    if not values:
        reasons.append("FRED returned no usable observations")
    elif actual_dates[0] > start + timedelta(days=7):
        reasons.append("first observation is more than seven days after the requested start")
    elif actual_dates[-1] < end - timedelta(days=7):
        reasons.append("last observation is more than seven days before the requested end")
    return {
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "actual_start": actual_dates[0].isoformat() if actual_dates else None,
        "actual_end": actual_dates[-1].isoformat() if actual_dates else None,
        "expected_trading_days": None, "actual_records": len(values),
        "missing_dates": [item.isoformat() for item in official_missing_dates],
        "complete": not reasons, "incomplete_reasons": reasons,
        "method_notes": ["FRED series frequency and official missing values are preserved; no interpolation is applied"],
    }


def _statistics(values: list[dict[str, Any]]) -> dict[str, Any]:
    series = pd.Series([item["value"] for item in values], dtype="float64")
    dates = [item["date"] for item in values]
    first, latest = float(series.iloc[0]), float(series.iloc[-1])
    return {
        "first_value": first, "latest_value": latest, "absolute_change": latest - first,
        "percent_change": latest / first - 1 if first else None,
        "period_high": float(series.max()), "period_high_date": dates[int(series.argmax())].isoformat(),
        "period_low": float(series.min()), "period_low_date": dates[int(series.argmin())].isoformat(),
        "mean": float(series.mean()), "standard_deviation": float(series.std(ddof=1)) if len(series) > 1 else None,
        "unavailable_reasons": {} if len(series) > 1 else {"standard_deviation": "two observations are required"},
    }


def _snapshot_hash(
    series_id: str,
    start: date,
    end: date,
    source_hash: str,
    values: list[dict[str, Any]],
) -> str:
    payload = [
        [item["date"].isoformat(), item["value"], item["realtime_start"].isoformat() if item["realtime_start"] else None]
        for item in values
    ]
    return sha256(
        f"{MACRO_PARQUET_SCHEMA_VERSION}|{series_id}|{start}|{end}|{source_hash}|".encode("utf-8")
        + canonical_json_bytes(payload)
    ).hexdigest()


_envelope = history_envelope
