from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

import pandas as pd

from app.domain.market.timeframes import timeframe_to_timedelta

from .contracts import DATASET_SCHEMA_VERSION, DEFAULT_FORWARD_HORIZONS, FactorDefinition
from .frame_builder import FactorFrameBuilder
from .math_utils import FactorMath
from app.services.persistence_ports import FactorResearchRepositoryPort


class FactorDatasetService:
    def __init__(
        self,
        *,
        repository: FactorResearchRepositoryPort,
        frame_builder: FactorFrameBuilder,
        math: FactorMath,
    ) -> None:
        self.repository = repository
        self.frame_builder = frame_builder
        self.math = math

    def build_stored_blend_frame(self, run: dict[str, Any]) -> pd.DataFrame:
        forward_horizons = list((run.get("request") or {}).get("forward_horizons") or DEFAULT_FORWARD_HORIZONS)
        frame = self.frame_builder.rows_to_frame(self.repository.get_dataset_rows(run["dataset_id"]), forward_horizons)
        return self.frame_builder.apply_blend_weights(frame, run["blend"], forward_horizons)

    def build_live_blend_frame(
        self,
        *,
        run: dict[str, Any],
        definitions: list[FactorDefinition],
        end_date: datetime | None = None,
    ) -> pd.DataFrame:
        request_payload = dict(run.get("request") or {})
        request_end = end_date or datetime.now(timezone.utc).replace(tzinfo=None)
        forward_horizons = list(request_payload.get("forward_horizons") or DEFAULT_FORWARD_HORIZONS)
        frame = self.frame_builder.build_live_factor_frame(
            definitions=definitions,
            symbol=request_payload["symbol"],
            timeframe=request_payload["timeframe"],
            days=int(request_payload.get("days", 365)),
            forward_horizons=forward_horizons,
            end_date=request_end,
        )
        return self.frame_builder.apply_blend_weights(frame, run["blend"], forward_horizons)

    def load_or_build_dataset(
        self,
        *,
        symbol: str,
        timeframe: str,
        days: int,
        primary_horizon: int,
        forward_horizons: list[int],
        categories: list[str],
        definitions: list[FactorDefinition],
        cleaning: dict[str, Any],
    ) -> dict[str, Any]:
        end_date = datetime.now(timezone.utc).replace(tzinfo=None)
        start_date = end_date - timeframe_to_timedelta("1d") * days
        signature = self._dataset_signature(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            primary_horizon=primary_horizon,
            forward_horizons=forward_horizons,
            categories=categories,
            factor_ids=[item.factor_id for item in definitions],
            cleaning=cleaning,
        )
        existing = self.repository.get_dataset_by_signature(signature)
        if existing:
            return existing

        fetch_start = start_date - (timeframe_to_timedelta(timeframe) * 60)
        price_frame = self.frame_builder.build_price_frame(symbol, timeframe, fetch_start, end_date, forward_horizons)
        if price_frame.empty:
            raise ValueError("没有可用于因子研究的价格数据。")
        raw_factor_frame = self.frame_builder.build_raw_factor_frame(definitions, price_frame, fetch_start)

        dataset_frame = price_frame.loc[price_frame["timestamp"] >= start_date, ["timestamp", "close", "volume"]].copy()
        dataset_frame = dataset_frame.reset_index(drop=True)
        for definition in definitions:
            raw_series = raw_factor_frame.get(definition.factor_id)
            if raw_series is None:
                continue
            feature_series = self.math.transform_feature(raw_series, definition.feature_mode)
            dataset_frame[f"raw::{definition.factor_id}"] = self.math.aligned_series(price_frame["timestamp"], raw_series, dataset_frame["timestamp"]).to_numpy()
            dataset_frame[f"feature::{definition.factor_id}"] = self.math.aligned_series(price_frame["timestamp"], feature_series, dataset_frame["timestamp"]).to_numpy()
        for horizon in forward_horizons:
            dataset_frame[f"label::{horizon}"] = self.math.aligned_series(
                price_frame["timestamp"],
                price_frame[f"future_return_{horizon}"],
                dataset_frame["timestamp"],
            ).to_numpy()

        dataset_rows = []
        for row in dataset_frame.to_dict("records"):
            raw_values = {
                definition.factor_id: self.math.to_optional_float(row.get(f"raw::{definition.factor_id}"))
                for definition in definitions
            }
            feature_values = {
                definition.factor_id: self.math.to_optional_float(row.get(f"feature::{definition.factor_id}"))
                for definition in definitions
            }
            labels = {
                str(horizon): self.math.to_optional_float(row.get(f"label::{horizon}"))
                for horizon in forward_horizons
            }
            dataset_rows.append(
                {
                    "timestamp": row["timestamp"],
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "raw_values": raw_values,
                    "feature_values": feature_values,
                    "labels": labels,
                }
            )

        sample_rows = [
            row for row in dataset_rows
            if row["feature_values"] and row["labels"].get(str(primary_horizon)) is not None
        ]
        if len(sample_rows) < int(cleaning["min_sample_size"]):
            raise ValueError("可用因子样本不足，暂时无法完成研究。")

        return self.repository.create_dataset(
            signature=signature,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            primary_horizon=primary_horizon,
            forward_horizons=forward_horizons,
            factor_ids=[item.factor_id for item in definitions],
            categories=categories or [item.category for item in definitions],
            cleaning=cleaning,
            row_count=len(dataset_rows),
            dataset_info={
                "schema_version": DATASET_SCHEMA_VERSION,
                "sample_range": {
                    "start": dataset_rows[0]["timestamp"].isoformat(),
                    "end": dataset_rows[-1]["timestamp"].isoformat(),
                },
                "warmup_bars": 60,
            },
            rows=dataset_rows,
        )

    def _dataset_signature(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        primary_horizon: int,
        forward_horizons: list[int],
        categories: list[str],
        factor_ids: list[str],
        cleaning: dict[str, Any],
    ) -> str:
        payload = {
            "schema_version": DATASET_SCHEMA_VERSION,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "primary_horizon": primary_horizon,
            "forward_horizons": list(forward_horizons),
            "categories": sorted(set(categories)),
            "factor_ids": sorted(set(factor_ids)),
            "cleaning": cleaning,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
