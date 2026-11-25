from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal

import numpy as np
import pandas as pd

from app.domain.immutability import deep_freeze
from app.domain.market.history.models import PriceSnapshot
from app.domain.market.technical_analysis import TechnicalAnalysis
from app.domain.serialization import canonical_json_bytes


INDICATOR_SCHEMA_VERSION = "price-indicators.v3"


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
    IndicatorDefinition("ema", "sma-seeded-1", {"windows": [20, 50]}, "selected close"),
    IndicatorDefinition("rsi", "wilder-sma-2", {"period": 14, "flat": 50}, "selected close"),
    IndicatorDefinition("macd", "sma-seeded-1", {"fast": 12, "slow": 26, "signal": 9}, "selected close"),
    IndicatorDefinition("bollinger", "1", {"window": 20, "deviations": 2}, "selected close"),
    IndicatorDefinition("atr", "wilder-sma-2", {"period": 14}, "raw OHLC"),
    IndicatorDefinition("obv", "1", {}, "selected close and volume"),
)


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
    prices = selected.tolist()
    def align(values):
        return [float("nan")] * (len(prices) - len(values)) + values
    for window in (20, 50):
        frame[f"ema_{window}"] = align(TechnicalAnalysis.calculate_ema_series(prices, window))
    frame["rsi_14"] = align(TechnicalAnalysis.calculate_rsi_series(prices, 14))
    macd, signal, histogram = TechnicalAnalysis.calculate_macd_series(prices)
    frame["macd"] = align(macd)
    frame["macd_signal"] = align(signal)
    frame["macd_histogram"] = align(histogram)
    middle = selected.rolling(window=20, min_periods=20).mean()
    deviation = selected.rolling(window=20, min_periods=20).std(ddof=0)
    frame["bollinger_mid"] = middle.to_numpy()
    frame["bollinger_upper"] = (middle + 2 * deviation).to_numpy()
    frame["bollinger_lower"] = (middle - 2 * deviation).to_numpy()
    frame["atr_14"] = align(TechnicalAnalysis.calculate_atr_series(
        high.tolist(), low.tolist(), raw_close.tolist(), 14,
    ))
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
