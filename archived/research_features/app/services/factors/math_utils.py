from __future__ import annotations

import math
from typing import Any

import pandas as pd


class FactorMath:
    def __init__(self, cleaning: dict[str, Any]) -> None:
        self.cleaning = dict(cleaning)

    def transform_feature(self, series: pd.Series, mode: str) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce").astype(float)
        if mode == "pct_change":
            return numeric.pct_change().replace([float("inf"), float("-inf")], pd.NA)
        if mode == "difference":
            return numeric.diff()
        return numeric

    def clean_feature(self, series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce").astype(float)
        winsorize = float(self.cleaning["winsorize_zscore"])
        zscore = self.zscore(numeric)
        upper = numeric.mean() + numeric.std() * winsorize
        lower = numeric.mean() - numeric.std() * winsorize
        return numeric.mask(zscore > winsorize, upper).mask(zscore < -winsorize, lower)

    def build_lag_profile(self, feature: pd.Series, target: pd.Series, max_lag_bars: int) -> list[dict[str, Any]]:
        return [
            {"lag": lag, "correlation": self.safe_corr(feature, target.shift(-lag))}
            for lag in range(max_lag_bars + 1)
        ]

    def build_rolling_corr(self, timestamps: pd.Series, feature: pd.Series, target: pd.Series) -> list[dict[str, Any]]:
        window = max(20, min(int(self.cleaning["rolling_ic_window"]), len(feature) // 3))
        if len(feature) < window:
            return []
        frame = pd.DataFrame({"timestamp": timestamps, "feature": feature, "target": target}).dropna()
        rolling = frame["feature"].rolling(window).corr(frame["target"]).dropna()
        result = []
        for index, value in rolling.items():
            ts = frame.loc[index, "timestamp"]
            result.append({"date": ts.isoformat(), "value": self.to_float(value)})
        return result

    def build_forward_metric(
        self,
        *,
        horizon: int,
        timestamps: pd.Series,
        feature: pd.Series,
        target: pd.Series,
        include_target_stats: bool = False,
        min_sample_size: int | None = None,
    ) -> dict[str, Any] | None:
        sample_floor = int(min_sample_size or self.cleaning["min_sample_size"])
        horizon_frame = pd.DataFrame({"timestamp": timestamps, "feature": feature, "target": target}).dropna()
        if len(horizon_frame) < sample_floor:
            return None
        rolling_corr = self.build_rolling_corr(horizon_frame["timestamp"], horizon_frame["feature"], horizon_frame["target"])
        quantiles = self.build_quantiles(horizon_frame["feature"], horizon_frame["target"])
        metric = {
            "horizon": horizon,
            "sample_size": int(len(horizon_frame)),
            "correlation": self.safe_corr(horizon_frame["feature"], horizon_frame["target"]),
            "rank_correlation": self.safe_corr(horizon_frame["feature"].rank(), horizon_frame["target"].rank()),
            "ic_mean": self.to_float(pd.Series([item["value"] for item in rolling_corr]).mean() if rolling_corr else 0.0),
            "ic_std": self.to_float(pd.Series([item["value"] for item in rolling_corr]).std() if rolling_corr else 0.0),
            "ic_ir": self.information_ratio(rolling_corr),
            "ic_t_stat": self.t_stat(rolling_corr),
            "quantile_spread": self.quantile_spread(quantiles),
            "hit_rate": self.hit_rate(horizon_frame["feature"], horizon_frame["target"]),
        }
        if include_target_stats:
            metric["target_mean"] = self.to_float(horizon_frame["target"].mean())
            metric["target_std"] = self.to_float(horizon_frame["target"].std())
        return metric

    def rolling_stability(self, overall_corr: float, rolling: list[dict[str, Any]]) -> float:
        if not rolling or overall_corr == 0:
            return 0.0
        same_direction = sum(1 for item in rolling if self.sign(item["value"]) == self.sign(overall_corr))
        return round(same_direction / len(rolling), 4)

    def build_quantiles(self, feature: pd.Series, target: pd.Series) -> list[dict[str, Any]]:
        quantile_frame = pd.DataFrame({"feature": feature, "target": target}).dropna()
        if len(quantile_frame) < int(self.cleaning["min_sample_size"]):
            return []
        try:
            quantile_frame["bucket"] = pd.qcut(
                quantile_frame["feature"],
                q=int(self.cleaning["bucket_count"]),
                labels=False,
                duplicates="drop",
            )
        except ValueError:
            return []
        max_bucket = quantile_frame["bucket"].max()
        if pd.isna(max_bucket):
            return []
        result = []
        total_buckets = int(max_bucket) + 1
        for bucket in range(total_buckets):
            sliced = quantile_frame.loc[quantile_frame["bucket"] == bucket]
            if sliced.empty:
                continue
            result.append(
                {
                    "bucket": bucket + 1,
                    "label": f"Q{bucket + 1}",
                    "avg_future_return": self.to_float(sliced["target"].mean()),
                    "count": int(len(sliced)),
                }
            )
        return result

    def build_normalized_series(
        self,
        frame: pd.DataFrame,
        *,
        feature_column: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        sliced = frame.tail(limit).copy()
        if sliced.empty:
            return []
        sliced["price_z"] = self.zscore(sliced["close"])
        sliced["factor_z"] = self.zscore(sliced[feature_column])
        return [
            {
                "date": row.timestamp.isoformat(),
                "price_z": self.to_float(row.price_z),
                "factor_z": self.to_float(row.factor_z),
                "future_return": self.to_float(row.future_return),
            }
            for row in sliced.itertuples(index=False)
        ]

    def bucket_turnover(self, feature: pd.Series) -> float:
        turnover_frame = pd.DataFrame({"feature": feature}).dropna()
        if len(turnover_frame) < int(self.cleaning["min_sample_size"]):
            return 0.0
        try:
            turnover_frame["bucket"] = pd.qcut(
                turnover_frame["feature"],
                q=int(self.cleaning["bucket_count"]),
                labels=False,
                duplicates="drop",
            )
        except ValueError:
            return 0.0
        changed = turnover_frame["bucket"].ne(turnover_frame["bucket"].shift(1))
        if len(changed) <= 1:
            return 0.0
        return self.to_float(changed.iloc[1:].mean())

    def score_factor(
        self,
        *,
        correlation: float,
        rank_correlation: float,
        best_lag_correlation: float,
        stability: float,
        quantile_spread: float,
        turnover: float,
        ic_ir: float,
    ) -> float:
        score = 0.0
        score += min(abs(correlation) / 0.2, 1.0) * 25
        score += min(abs(rank_correlation) / 0.2, 1.0) * 10
        score += min(abs(best_lag_correlation) / 0.2, 1.0) * 15
        score += min(stability / 0.75, 1.0) * 18
        score += min(abs(quantile_spread) / 0.05, 1.0) * 12
        score += min(abs(ic_ir) / 1.5, 1.0) * 10
        score += max(0.0, 1 - min(turnover / 0.75, 1.0)) * 10
        return round(score, 2)

    def safe_corr(self, left: pd.Series, right: pd.Series) -> float:
        aligned = pd.concat([left, right], axis=1).dropna()
        if len(aligned) < 10:
            return 0.0
        if aligned.iloc[:, 0].nunique() <= 1 or aligned.iloc[:, 1].nunique() <= 1:
            return 0.0
        value = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
        return self.to_float(value)

    def hit_rate(self, feature: pd.Series, target: pd.Series) -> float:
        aligned = pd.concat([feature, target], axis=1).dropna()
        if aligned.empty:
            return 0.0
        return self.to_float((aligned.iloc[:, 0].apply(self.sign) == aligned.iloc[:, 1].apply(self.sign)).mean())

    def information_ratio(self, rolling: list[dict[str, Any]]) -> float:
        if not rolling:
            return 0.0
        values = pd.Series([item["value"] for item in rolling]).dropna()
        std = values.std()
        if std is None or pd.isna(std) or std == 0:
            return 0.0
        return self.to_float(values.mean() / std)

    def t_stat(self, rolling: list[dict[str, Any]]) -> float:
        if not rolling:
            return 0.0
        values = pd.Series([item["value"] for item in rolling]).dropna()
        if len(values) < 2:
            return 0.0
        std = values.std()
        if std is None or pd.isna(std) or std == 0:
            return 0.0
        return self.to_float(values.mean() / (std / math.sqrt(len(values))))

    def quantile_spread(self, quantiles: list[dict[str, Any]]) -> float:
        if len(quantiles) < 2:
            return 0.0
        return self.to_float(quantiles[-1]["avg_future_return"] - quantiles[0]["avg_future_return"])

    def zscore(self, series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce").astype(float)
        std = numeric.std()
        if std is None or pd.isna(std) or std == 0:
            return pd.Series([0.0] * len(numeric), index=numeric.index)
        return (numeric - numeric.mean()) / std

    def aligned_series(self, source_index: pd.Series, source_series: pd.Series, target_index: pd.Series) -> pd.Series:
        index = pd.Index(source_index)
        series = pd.Series(source_series.values, index=index)
        aligned = series.reindex(index.union(pd.Index(target_index))).sort_index().ffill().reindex(pd.Index(target_index))
        return aligned

    def sign(self, value: float | int | None) -> int:
        if value is None:
            return 0
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0

    def to_optional_float(self, value: Any) -> float | None:
        try:
            if pd.isna(value):
                return None
        except TypeError:
            pass
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return round(numeric, 6)

    def to_float(self, value: Any) -> float:
        optional = self.to_optional_float(value)
        return optional if optional is not None else 0.0
