from __future__ import annotations

from typing import Any

import pandas as pd

from .math_utils import FactorMath


class FactorBlendService:
    def __init__(self, math: FactorMath) -> None:
        self.math = math

    def build_blend(
        self,
        *,
        factor_results: list[dict[str, Any]],
        primary_horizon: int,
        forward_horizons: list[int],
    ) -> dict[str, Any]:
        ranked = sorted(factor_results, key=lambda item: item["scorecard"]["score"], reverse=True)
        selected: list[dict[str, Any]] = []
        dropped: list[dict[str, Any]] = []
        feature_corr_threshold = 0.8
        min_sample_size = int(self.math.cleaning["min_sample_size"])

        for result in ranked:
            scorecard = result["scorecard"]
            if scorecard["sample_size"] < min_sample_size:
                dropped.append({"factor_id": scorecard["factor_id"], "name": scorecard["name"], "reason": "sample_too_small"})
                continue
            if scorecard["score"] < 12:
                dropped.append({"factor_id": scorecard["factor_id"], "name": scorecard["name"], "reason": "score_too_low"})
                continue
            if self._too_similar_to_selected(result, selected, min_sample_size, feature_corr_threshold, dropped):
                continue
            selected.append(result)
            if len(selected) >= 5:
                break

        if not selected:
            selected = ranked[: min(3, len(ranked))]

        composite_series, composite_meta = self._build_composite_series(selected, forward_horizons)
        if composite_series is None or composite_series.empty:
            return {
                "selected_factors": [],
                "dropped_factors": dropped,
                "weights": [],
                "forward_metrics": [],
                "quantiles": [],
                "normalized_series": [],
                "entry_threshold": 0.0,
                "exit_threshold": 0.0,
            }

        composite_series["composite_score"] = self.math.clean_feature(composite_series["composite_score"])
        composite_series = composite_series.dropna(subset=["composite_score", f"label::{primary_horizon}"])

        forward_metrics = []
        for horizon in forward_horizons:
            label_column = f"label::{horizon}"
            metric = self.math.build_forward_metric(
                horizon=horizon,
                timestamps=composite_series["timestamp"],
                feature=composite_series["composite_score"],
                target=composite_series[label_column],
                min_sample_size=min_sample_size,
            )
            if metric is None:
                continue
            forward_metrics.append(metric)

        primary_quantiles = self.math.build_quantiles(composite_series["composite_score"], composite_series[f"label::{primary_horizon}"])
        normalized = self.math.build_normalized_series(
            composite_series.rename(columns={f"label::{primary_horizon}": "future_return", "composite_score": "feature"}),
            feature_column="feature",
            limit=240,
        )
        return {
            "selected_factors": composite_meta,
            "dropped_factors": dropped,
            "weights": composite_meta,
            "forward_metrics": forward_metrics,
            "quantiles": primary_quantiles,
            "normalized_series": normalized,
            "entry_threshold": self.math.to_float(composite_series["composite_score"].quantile(0.7)),
            "exit_threshold": self.math.to_float(composite_series["composite_score"].quantile(0.45)),
            "score_std": self.math.to_float(composite_series["composite_score"].std()),
            "score_mean": self.math.to_float(composite_series["composite_score"].mean()),
        }

    def _too_similar_to_selected(
        self,
        result: dict[str, Any],
        selected: list[dict[str, Any]],
        min_sample_size: int,
        threshold: float,
        dropped: list[dict[str, Any]],
    ) -> bool:
        scorecard = result["scorecard"]
        for chosen in selected:
            merged = pd.merge(
                chosen["analysis_frame"][["timestamp", "feature"]],
                result["analysis_frame"][["timestamp", "feature"]],
                on="timestamp",
                how="inner",
                suffixes=("_left", "_right"),
            ).dropna()
            if len(merged) < min_sample_size:
                continue
            corr = abs(self.math.safe_corr(merged["feature_left"], merged["feature_right"]))
            if corr >= threshold:
                dropped.append(
                    {
                        "factor_id": scorecard["factor_id"],
                        "name": scorecard["name"],
                        "reason": f"too_similar_to_{chosen['scorecard']['factor_id']}",
                    }
                )
                return True
        return False

    def _build_composite_series(
        self,
        selected: list[dict[str, Any]],
        forward_horizons: list[int],
    ) -> tuple[pd.DataFrame | None, list[dict[str, Any]]]:
        weights: list[tuple[dict[str, Any], float]] = []
        weight_base = 0.0
        for item in selected:
            scorecard = item["scorecard"]
            raw_weight = scorecard["score"] * max(scorecard["stability"], 0.2) * max(abs(scorecard["correlation"]), 0.05)
            signed_weight = raw_weight if scorecard["direction"] == "positive" else -raw_weight
            weights.append((item, signed_weight))
            weight_base += abs(signed_weight)
        normalized_weights = {
            item["scorecard"]["factor_id"]: (signed_weight / weight_base if weight_base else 0.0)
            for item, signed_weight in weights
        }

        composite_series = None
        composite_meta = []
        for item in selected:
            factor_id = item["scorecard"]["factor_id"]
            feature_frame = item["analysis_frame"][["timestamp", "close", "feature", *[f"label::{h}" for h in forward_horizons]]].copy()
            feature_frame = feature_frame.rename(columns={"feature": f"feature::{factor_id}"})
            if composite_series is None:
                composite_series = feature_frame
                composite_series["composite_score"] = 0.0
            else:
                composite_series = composite_series.merge(feature_frame, on=["timestamp", "close", *[f"label::{h}" for h in forward_horizons]], how="inner")
            composite_series["composite_score"] += self.math.zscore(composite_series[f"feature::{factor_id}"]) * normalized_weights.get(factor_id, 0.0)
            composite_meta.append(
                {
                    "factor_id": factor_id,
                    "name": item["scorecard"]["name"],
                    "category": item["scorecard"]["category"],
                    "score": item["scorecard"]["score"],
                    "correlation": item["scorecard"]["correlation"],
                    "stability": item["scorecard"]["stability"],
                    "turnover": item["scorecard"]["turnover"],
                    "weight": self.math.to_float(normalized_weights[factor_id]),
                }
            )
        return composite_series, composite_meta
