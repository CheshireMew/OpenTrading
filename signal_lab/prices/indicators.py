from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from signal_lab.config import SignalLabConfig
from signal_lab.immutability import deep_freeze
from signal_lab.prices.artifacts import PriceArtifactStore, frame_semantic_sha256
from signal_lab.prices.models import PriceSnapshot
from signal_lab.storage.artifacts import storage_item
from signal_lab.storage.capacity import ManagedStorage
from signal_lab.storage.database import SignalLabDatabase
from signal_lab.storage.file_integrity import file_sha256
from signal_lab.storage.price_repository import PriceRepository
from signal_lab.structured_data import canonical_json_bytes


INDICATOR_SCHEMA_VERSION = "price-indicators.v2"


@dataclass(frozen=True, slots=True)
class IndicatorDefinition:
    indicator_id: str
    version: str
    parameters: dict[str, Any]
    input_contract: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", deep_freeze(self.parameters))


INDICATOR_DEFINITIONS = (
    IndicatorDefinition("sma", "1", {"windows": [20, 50, 200]}, "selected close"),
    IndicatorDefinition("ema", "1", {"windows": [20, 50]}, "selected close"),
    IndicatorDefinition("rsi", "wilder-1", {"period": 14}, "selected close"),
    IndicatorDefinition("macd", "1", {"fast": 12, "slow": 26, "signal": 9}, "selected close"),
    IndicatorDefinition("bollinger", "1", {"window": 20, "deviations": 2}, "selected close"),
    IndicatorDefinition("atr", "wilder-1", {"period": 14}, "raw OHLC"),
    IndicatorDefinition("obv", "1", {}, "selected close and volume"),
)


class PriceIndicatorService:
    """Materialize deterministic indicator series for one immutable price snapshot."""

    def __init__(self, root: Path, config: SignalLabConfig) -> None:
        self.root = root.expanduser().resolve()
        self.config = config
        self._prices = PriceRepository(SignalLabDatabase(self.root))
        self.artifacts = PriceArtifactStore(self.root, config)

    def materialize(
        self,
        canonical_code: str,
        *,
        snapshot_hash: str | None = None,
        basis: Literal["raw", "adjusted"] = "raw",
    ) -> dict[str, Any]:
        snapshot = self._prices.load_price_snapshot(canonical_code, snapshot_hash)
        registry_hash = indicator_registry_hash()
        destination = (
            self.artifacts.snapshot_directory(snapshot)
            / f"indicators-{basis}-{registry_hash[:16]}.parquet"
        )
        expected = {
            b"signal_lab_indicator_schema_version": INDICATOR_SCHEMA_VERSION.encode("ascii"),
            b"signal_lab_snapshot_hash": snapshot.snapshot_hash.encode("ascii"),
            b"signal_lab_indicator_basis": basis.encode("ascii"),
            b"signal_lab_indicator_registry_hash": registry_hash.encode("ascii"),
        }
        if not destination.exists():
            storage = ManagedStorage(
                self.root,
                maximum_managed_bytes=self.config.max_managed_bytes,
                minimum_free_bytes=self.config.min_free_bytes,
            )
            preflight = storage.preflight(
                "price-indicator-artifact",
                estimated_peak_bytes=max(4 * 1024 * 1024, len(snapshot.bars) * 2048),
            )
            operation_id = f"indicator-{snapshot.snapshot_hash}-{basis}-{registry_hash[:16]}"
            operation = storage.operation_directory("price-indicator-artifact", operation_id)
            storage.begin_operation(
                operation,
                operation_id=operation_id,
                producer="price-indicator-artifact",
                preflight=preflight,
            )
            temporary = operation / "indicators.parquet.tmp"
            try:
                frame = indicator_frame(snapshot, basis)
                table = pa.Table.from_pandas(frame, preserve_index=False)
                metadata = dict(table.schema.metadata or {})
                metadata.update(expected)
                metadata[b"signal_lab_semantic_sha256"] = frame_semantic_sha256(frame).encode(
                    "ascii"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(table.replace_schema_metadata(metadata), temporary, compression="zstd")
                temporary.replace(destination)
                storage.finish_operation(
                    operation,
                    status="published",
                    inventory=[storage_item(destination, "cache")],
                )
            except BaseException as exc:
                inventory = [
                    storage_item(path, "temporary")
                    for path in (temporary, destination)
                    if path.is_file()
                ]
                storage.finish_failure(
                    operation,
                    error=exc,
                    inventory=inventory,
                )
                raise
        metadata = pq.read_schema(destination).metadata or {}
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ValueError(f"immutable indicator artifact metadata mismatch: {destination}")
        row_count = pq.read_metadata(destination).num_rows
        if row_count != len(snapshot.bars):
            raise ValueError(f"immutable indicator artifact row count mismatch: {destination}")
        semantic_hash = metadata.get(b"signal_lab_semantic_sha256")
        actual_semantic_hash = frame_semantic_sha256(pd.read_parquet(destination)).encode("ascii")
        if semantic_hash is None or semantic_hash != actual_semantic_hash:
            raise ValueError(f"immutable indicator artifact content mismatch: {destination}")
        return {
            "path": str(destination.resolve()),
            "rows": row_count,
            "sha256": file_sha256(destination),
            "snapshot_hash": snapshot.snapshot_hash,
            "basis": basis,
            "indicator_schema_version": INDICATOR_SCHEMA_VERSION,
            "indicator_registry_hash": registry_hash,
            "definitions": indicator_definitions_payload(),
        }


def indicator_frame(
    snapshot: PriceSnapshot,
    basis: Literal["raw", "adjusted"],
) -> pd.DataFrame:
    observed_at = pd.DatetimeIndex([bar.observed_at for bar in snapshot.bars])
    selected = pd.Series(
        [bar.adjusted_close if basis == "adjusted" else bar.close for bar in snapshot.bars],
        index=observed_at,
        dtype="float64",
    )
    high = pd.Series([bar.high for bar in snapshot.bars], index=observed_at, dtype="float64")
    low = pd.Series([bar.low for bar in snapshot.bars], index=observed_at, dtype="float64")
    raw_close = pd.Series([bar.close for bar in snapshot.bars], index=observed_at, dtype="float64")
    volume = pd.Series([bar.volume for bar in snapshot.bars], index=observed_at, dtype="float64")
    frame = pd.DataFrame(
        {
            "date": [bar.observation_date for bar in snapshot.bars],
            "observed_at": observed_at,
            "basis": basis,
            "price": selected.to_numpy(),
            "snapshot_hash": snapshot.snapshot_hash,
        }
    )
    for window in (20, 50, 200):
        frame[f"sma_{window}"] = selected.rolling(window=window, min_periods=window).mean().to_numpy()
    for window in (20, 50):
        frame[f"ema_{window}"] = selected.ewm(span=window, adjust=False, min_periods=window).mean().to_numpy()
    frame["rsi_14"] = _wilder_rsi_series(selected, 14).to_numpy()
    ema_fast = selected.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_slow = selected.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    frame["macd"] = macd.to_numpy()
    frame["macd_signal"] = signal.to_numpy()
    frame["macd_histogram"] = (macd - signal).to_numpy()
    middle = selected.rolling(window=20, min_periods=20).mean()
    deviation = selected.rolling(window=20, min_periods=20).std(ddof=0)
    frame["bollinger_mid"] = middle.to_numpy()
    frame["bollinger_upper"] = (middle + 2 * deviation).to_numpy()
    frame["bollinger_lower"] = (middle - 2 * deviation).to_numpy()
    true_range = pd.concat(
        [high - low, (high - raw_close.shift(1)).abs(), (low - raw_close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    frame["atr_14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().to_numpy()
    direction = np.sign(selected.diff().fillna(0.0).to_numpy(dtype=float))
    volume_values = volume.fillna(0.0).to_numpy(dtype=float)
    frame["obv"] = np.cumsum(direction * volume_values)
    return frame


def latest_indicator_summary(
    snapshot: PriceSnapshot,
    basis: Literal["raw", "adjusted"],
) -> dict[str, Any]:
    frame = indicator_frame(snapshot, basis)
    reasons: dict[str, str] = {}
    if frame.empty:
        return _empty_indicators("no usable price records")
    latest = frame.iloc[-1]
    indicators: dict[str, Any] = {
        "schema_version": INDICATOR_SCHEMA_VERSION,
        "registry_hash": indicator_registry_hash(),
        "sma": {},
        "price_vs_sma": {},
    }
    for window in (20, 50, 200):
        key = str(window)
        average = _finite_or_none(latest[f"sma_{window}"])
        indicators["sma"][key] = average
        indicators["price_vs_sma"][key] = (
            _finite_or_none(float(latest["price"]) / average - 1) if average else None
        )
        if average is None:
            reasons[f"sma{window}"] = f"{window} price records are required"
    indicators.update(
        {
            "ema": {
                "20": _finite_or_none(latest["ema_20"]),
                "50": _finite_or_none(latest["ema_50"]),
            },
            "rsi14": _finite_or_none(latest["rsi_14"]),
            "macd": {
                "value": _finite_or_none(latest["macd"]),
                "signal": _finite_or_none(latest["macd_signal"]),
                "histogram": _finite_or_none(latest["macd_histogram"]),
            },
            "bollinger": {
                "middle": _finite_or_none(latest["bollinger_mid"]),
                "upper": _finite_or_none(latest["bollinger_upper"]),
                "lower": _finite_or_none(latest["bollinger_lower"]),
            },
            "atr14": _finite_or_none(latest["atr_14"]),
            "obv": _finite_or_none(latest["obv"]),
        }
    )
    if indicators["rsi14"] is None:
        reasons["rsi14"] = "15 price records are required"
    indicators["unavailable_reasons"] = reasons
    return indicators


def indicator_definitions_payload() -> list[dict[str, Any]]:
    return [
        {
            "indicator_id": item.indicator_id,
            "version": item.version,
            "parameters": item.parameters,
            "input_contract": item.input_contract,
        }
        for item in INDICATOR_DEFINITIONS
    ]


def indicator_registry_hash() -> str:
    return sha256(
        canonical_json_bytes(
            {
                "schema_version": INDICATOR_SCHEMA_VERSION,
                "definitions": indicator_definitions_payload(),
            }
        )
    ).hexdigest()


def _wilder_rsi_series(prices: pd.Series, period: int) -> pd.Series:
    if prices.empty:
        return pd.Series(index=prices.index, dtype="float64")
    deltas = prices.diff()
    gains = deltas.clip(lower=0)
    losses = -deltas.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss
    values = 100 - 100 / (1 + relative_strength)
    values = values.mask((average_loss == 0) & (average_gain > 0), 100.0)
    values = values.mask((average_loss == 0) & (average_gain == 0), 50.0)
    return values


def _empty_indicators(reason: str) -> dict[str, Any]:
    return {
        "schema_version": INDICATOR_SCHEMA_VERSION,
        "registry_hash": indicator_registry_hash(),
        "sma": {"20": None, "50": None, "200": None},
        "price_vs_sma": {"20": None, "50": None, "200": None},
        "ema": {"20": None, "50": None},
        "rsi14": None,
        "macd": {"value": None, "signal": None, "histogram": None},
        "bollinger": {"middle": None, "upper": None, "lower": None},
        "atr14": None,
        "obv": None,
        "unavailable_reasons": {"all": reason},
    }


def _finite_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    numeric = float(value)
    return numeric if np.isfinite(numeric) else None
