from __future__ import annotations

from typing import Any

import pandas as pd

from .contracts import FactorDefinition
from .math_utils import FactorMath


class FactorDetailService:
    def __init__(self, math: FactorMath) -> None:
        self.math = math

    def analyze_factor(
        self,
        *,
        definition: FactorDefinition,
        frame: pd.DataFrame,
        primary_horizon: int,
        forward_horizons: list[int],
        max_lag_bars: int,
    ) -> dict[str, Any] | None:
        raw_column = f"raw::{definition.factor_id}"
        feature_column = f"feature::{definition.factor_id}"
        if raw_column not in frame.columns or feature_column not in frame.columns:
            return None
        base = frame[["timestamp", "close", raw_column, feature_column, *[f"label::{h}" for h in forward_horizons if f"label::{h}" in frame.columns]]].copy()
        base = base.rename(columns={raw_column: "raw_factor", feature_column: "feature"})
        base["feature"] = self.math.clean_feature(base["feature"])
        base = base.dropna(subset=["feature", f"label::{primary_horizon}"])
        if len(base) < int(self.math.cleaning["min_sample_size"]):
            return None

        forward_metrics = []
        primary_metric = None
        for horizon in forward_horizons:
            label_column = f"label::{horizon}"
            if label_column not in base.columns:
                continue
            metric = self.math.build_forward_metric(
                horizon=horizon,
                timestamps=base["timestamp"],
                feature=base["feature"],
                target=base[label_column],
                include_target_stats=True,
            )
            if metric is None:
                continue
            forward_metrics.append(metric)
            if horizon == primary_horizon:
                primary_metric = metric

        if not primary_metric:
            return None

        primary_target = base[f"label::{primary_horizon}"]
        lag_profile = self.math.build_lag_profile(base["feature"], primary_target, max_lag_bars)
        best_lag = max(lag_profile, key=lambda item: abs(item["correlation"])) if lag_profile else {"lag": 0, "correlation": 0.0}
        rolling_corr = self.math.build_rolling_corr(base["timestamp"], base["feature"], primary_target)
        quantiles = self.math.build_quantiles(base["feature"], primary_target)
        turnover = self.math.bucket_turnover(base["feature"])
        stability = self.math.rolling_stability(primary_metric["correlation"], rolling_corr)
        normalized = self.math.build_normalized_series(
            base.assign(future_return=primary_target),
            feature_column="feature",
            limit=240,
        )
        score = self.math.score_factor(
            correlation=primary_metric["correlation"],
            rank_correlation=primary_metric["rank_correlation"],
            best_lag_correlation=best_lag["correlation"],
            stability=stability,
            quantile_spread=primary_metric["quantile_spread"],
            turnover=turnover,
            ic_ir=primary_metric["ic_ir"],
        )
        detail = {
            "factor_id": definition.factor_id,
            "name": definition.name,
            "category": definition.category,
            "unit": definition.unit,
            "feature_mode": definition.feature_mode,
            "description": definition.description,
            "sample_range": {
                "start": base["timestamp"].iloc[0].isoformat(),
                "end": base["timestamp"].iloc[-1].isoformat(),
            },
            "sample_size": int(len(base)),
            "latest_raw_value": self.math.to_float(base["raw_factor"].iloc[-1]),
            "latest_feature_value": self.math.to_float(base["feature"].iloc[-1]),
            "target_mean": primary_metric["target_mean"],
            "target_std": primary_metric["target_std"],
            "correlation": primary_metric["correlation"],
            "rank_correlation": primary_metric["rank_correlation"],
            "best_lag": int(best_lag["lag"]),
            "best_lag_correlation": self.math.to_float(best_lag["correlation"]),
            "stability": stability,
            "quantile_spread": primary_metric["quantile_spread"],
            "hit_rate": primary_metric["hit_rate"],
            "turnover": turnover,
            "ic_mean": primary_metric["ic_mean"],
            "ic_std": primary_metric["ic_std"],
            "ic_ir": primary_metric["ic_ir"],
            "ic_t_stat": primary_metric["ic_t_stat"],
            "forward_metrics": forward_metrics,
            "lag_profile": lag_profile,
            "rolling_correlation": rolling_corr,
            "quantiles": quantiles,
            "normalized_series": normalized,
        }
        scorecard = {
            "factor_id": definition.factor_id,
            "name": definition.name,
            "category": definition.category,
            "feature_mode": definition.feature_mode,
            "sample_size": int(len(base)),
            "latest_value": detail["latest_raw_value"],
            "correlation": primary_metric["correlation"],
            "rank_correlation": primary_metric["rank_correlation"],
            "best_lag": int(best_lag["lag"]),
            "best_lag_correlation": self.math.to_float(best_lag["correlation"]),
            "stability": stability,
            "quantile_spread": primary_metric["quantile_spread"],
            "hit_rate": primary_metric["hit_rate"],
            "turnover": turnover,
            "ic_ir": primary_metric["ic_ir"],
            "direction": "positive" if primary_metric["correlation"] >= 0 else "negative",
            "score": score,
        }
        analysis_frame = base[["timestamp", "close", "feature", *[f"label::{h}" for h in forward_horizons]]].copy()
        return {"scorecard": scorecard, "detail": detail, "analysis_frame": analysis_frame}
