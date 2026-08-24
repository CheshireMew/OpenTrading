from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.domain.market.timeframes import timeframe_to_timedelta
from app.services.persistence_ports import IndicatorRepositoryPort
from app.services.market.market_data_service import MarketDataService

from .contracts import DERIVED_FACTORS, FactorDefinition
from .math_utils import FactorMath


class FactorFrameBuilder:
    def __init__(
        self,
        *,
        market_data_service: MarketDataService,
        indicator_repository: IndicatorRepositoryPort,
        math: FactorMath,
    ) -> None:
        self.market_data_service = market_data_service
        self.indicator_repository = indicator_repository
        self.math = math

    def rows_to_frame(self, rows: list[dict], forward_horizons: list[int]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()
        factor_ids: set[str] = set()
        for row in rows:
            factor_ids.update((row.get("feature_values") or {}).keys())
            factor_ids.update((row.get("raw_values") or {}).keys())

        records = []
        for row in rows:
            payload = {
                "timestamp": row["timestamp"],
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            for factor_id in factor_ids:
                payload[f"raw::{factor_id}"] = self.math.to_optional_float((row.get("raw_values") or {}).get(factor_id))
                payload[f"feature::{factor_id}"] = self.math.to_optional_float((row.get("feature_values") or {}).get(factor_id))
            for horizon in forward_horizons:
                payload[f"label::{horizon}"] = self.math.to_optional_float((row.get("labels") or {}).get(str(horizon)))
            records.append(payload)
        return pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)

    def build_price_frame(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        forward_horizons: list[int],
    ) -> pd.DataFrame:
        rows = self.market_data_service.load_ohlcv_range(
            symbol,
            timeframe,
            start_date,
            end_date,
        ).require_complete(symbol=symbol, timeframe=timeframe)
        if not rows:
            return pd.DataFrame()
        frame = pd.DataFrame(rows, columns=["timestamp_ms", "open", "high", "low", "close", "volume"])
        frame["timestamp"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True).dt.tz_localize(None)
        frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
        frame["close_return_1"] = frame["close"].pct_change()
        frame["close_return_5"] = frame["close"].pct_change(5)
        frame["volume_change_1"] = frame["volume"].pct_change()
        frame["realized_vol_20"] = frame["close_return_1"].rolling(20).std()
        frame["range_pct"] = (frame["high"] - frame["low"]) / frame["close"].replace(0, pd.NA)
        frame["ma20"] = frame["close"].rolling(20).mean()
        frame["ma_gap_20"] = (frame["close"] / frame["ma20"]) - 1
        for horizon in forward_horizons:
            frame[f"future_return_{horizon}"] = frame["close"].shift(-horizon) / frame["close"] - 1
        return frame

    def build_raw_factor_frame(
        self,
        definitions: list[FactorDefinition],
        price_frame: pd.DataFrame,
        start_date: datetime,
    ) -> pd.DataFrame:
        frame = pd.DataFrame(index=price_frame["timestamp"])
        derived_ids = {item.factor_id for item in DERIVED_FACTORS}
        for definition in definitions:
            if definition.factor_id in derived_ids:
                frame[definition.factor_id] = self.derived_series(definition.factor_id, price_frame).values

        external_ids = [item.factor_id for item in definitions if item.source == "indicator"]
        history_points = self.indicator_repository.get_history_points(external_ids, start_date=start_date - timedelta(days=30))
        for definition in definitions:
            if definition.source != "indicator":
                continue
            rows = history_points.get(definition.factor_id, [])
            if not rows:
                continue
            indicator_frame = pd.DataFrame(rows)
            indicator_frame["timestamp"] = pd.to_datetime(indicator_frame["timestamp"], utc=True).dt.tz_localize(None)
            indicator_frame = indicator_frame.sort_values("timestamp").drop_duplicates("timestamp")
            series = indicator_frame.set_index("timestamp")["value"].astype(float)
            aligned = series.reindex(frame.index.union(series.index)).sort_index().ffill().reindex(frame.index)
            frame[definition.factor_id] = aligned.values
        return frame

    def build_live_factor_frame(
        self,
        *,
        definitions: list[FactorDefinition],
        symbol: str,
        timeframe: str,
        days: int,
        forward_horizons: list[int],
        end_date: datetime,
    ) -> pd.DataFrame:
        request_start = end_date - timedelta(days=days)
        fetch_start = request_start - (timeframe_to_timedelta(timeframe) * 60)
        price_frame = self.build_price_frame(symbol, timeframe, fetch_start, end_date, forward_horizons)
        raw_factor_frame = self.build_raw_factor_frame(definitions, price_frame, fetch_start)
        frame = price_frame.loc[price_frame["timestamp"] >= request_start, ["timestamp", "close", "volume"]].copy().reset_index(drop=True)
        for definition in definitions:
            raw_series = raw_factor_frame.get(definition.factor_id)
            if raw_series is None:
                continue
            feature_series = self.math.transform_feature(raw_series, definition.feature_mode)
            frame[f"feature::{definition.factor_id}"] = self.math.aligned_series(price_frame["timestamp"], feature_series, frame["timestamp"]).to_numpy()
        for horizon in forward_horizons:
            frame[f"label::{horizon}"] = self.math.aligned_series(
                price_frame["timestamp"],
                price_frame[f"future_return_{horizon}"],
                frame["timestamp"],
            ).to_numpy()
        return frame

    def apply_blend_weights(
        self,
        frame: pd.DataFrame,
        blend: dict,
        forward_horizons: list[int],
    ) -> pd.DataFrame:
        selected = list(blend.get("selected_factors") or [])
        if not selected:
            return pd.DataFrame()
        result = frame[["timestamp", "close", *[f"label::{h}" for h in forward_horizons if f"label::{h}" in frame.columns]]].copy()
        result["composite_score"] = 0.0
        for item in selected:
            factor_id = item["factor_id"]
            column = f"feature::{factor_id}"
            if column not in frame.columns:
                continue
            result["composite_score"] += self.math.zscore(frame[column]) * float(item.get("weight", 0.0))
        result["composite_score"] = self.math.clean_feature(result["composite_score"])
        result = result.sort_values("timestamp").reset_index(drop=True)
        return result

    def derived_series(self, factor_id: str, price_frame: pd.DataFrame) -> pd.Series:
        mapping = {
            "DERIVED_CLOSE_RETURN_1": price_frame["close_return_1"],
            "DERIVED_CLOSE_RETURN_5": price_frame["close_return_5"],
            "DERIVED_VOLUME_CHANGE_1": price_frame["volume_change_1"],
            "DERIVED_REALIZED_VOL_20": price_frame["realized_vol_20"],
            "DERIVED_RANGE_PCT": price_frame["range_pct"],
            "DERIVED_MA_GAP_20": price_frame["ma_gap_20"],
        }
        return mapping[factor_id].astype(float)
