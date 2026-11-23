from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
import math
from statistics import NormalDist
from typing import Any

import numpy as np

from app.domain.market.liquidity_definitions import (
    GROUP_DESCRIPTIONS,
    GROUP_WEIGHTS,
    SCORED_DEFINITIONS,
    SCORED_IDS,
    LiquidityIndicatorDefinition,
    PRESSURE_PERCENTILES,
)


class LiquidityScoreEngine:
    def composite_history(
        self,
        points_map: dict[str, list[tuple[datetime, float]]],
        *,
        start_date: datetime,
        end_date: datetime,
        change_days: int,
    ) -> list[dict[str, Any]]:
        prepared = self._prepare_points(points_map)
        return self._composite_history_prepared(
            points_map,
            prepared,
            start_date=start_date,
            end_date=end_date,
            change_days=change_days,
        )

    def composite_snapshot_and_history(
        self,
        points_map: dict[str, list[tuple[datetime, float]]],
        *,
        as_of: datetime,
        history_start: datetime,
        change_days: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Build current state and history from one normalized numerical projection."""

        prepared = self._prepare_points(points_map)
        current = self._composite_prepared_at(as_of, prepared, change_days=change_days)
        history = self._composite_history_prepared(
            points_map,
            prepared,
            start_date=history_start,
            end_date=as_of,
            change_days=change_days,
        )
        return current, history

    def _composite_history_prepared(
        self,
        points_map: dict[str, list[tuple[datetime, float]]],
        prepared: dict[str, tuple[np.ndarray, np.ndarray, list[datetime]]],
        *,
        start_date: datetime,
        end_date: datetime,
        change_days: int,
    ) -> list[dict[str, Any]]:
        raw_dates = sorted(
            {
                timestamp
                for indicator_id in SCORED_IDS
                for timestamp, _value in points_map.get(indicator_id, [])
                if start_date <= timestamp <= end_date
            }
        )
        output = []
        for item in self._weekly_sample_dates(raw_dates):
            composite = self._composite_prepared_at(
                item, prepared, change_days=change_days,
            )
            if composite["score"] is not None:
                output.append({"date": item, "score": composite["score"]})
        return output

    def composite_at(
        self,
        as_of: datetime,
        points_map: dict[str, list[tuple[datetime, float]]],
        *,
        change_days: int,
    ) -> dict[str, Any]:
        return self._composite_prepared_at(
            as_of, self._prepare_points(points_map), change_days=change_days,
        )

    @staticmethod
    def _prepare_points(
        points_map: dict[str, list[tuple[datetime, float]]],
    ) -> dict[str, tuple[np.ndarray, np.ndarray, list[datetime]]]:
        output: dict[str, tuple[np.ndarray, np.ndarray, list[datetime]]] = {}
        for indicator_id, raw in points_map.items():
            ordered = sorted(raw)
            dates = [item[0] for item in ordered]
            output[indicator_id] = (
                np.fromiter((item.timestamp() for item in dates), dtype=np.float64),
                np.fromiter((item[1] for item in ordered), dtype=np.float64),
                dates,
            )
        return output

    def _composite_prepared_at(
        self,
        as_of: datetime,
        prepared: dict[str, tuple[np.ndarray, np.ndarray, list[datetime]]],
        *,
        change_days: int,
    ) -> dict[str, Any]:
        components = [
            self._indicator_score_prepared(
                definition,
                prepared.get(
                    definition.indicator_id,
                    (np.array([], dtype=float), np.array([], dtype=float), []),
                ),
                as_of,
                change_days=change_days,
            )
            for definition in SCORED_DEFINITIONS
        ]
        valid = [item for item in components if item["z_score"] is not None]
        if not valid:
            return {"score": None, "coverage": 0.0, "components": components}
        available_group_weight = sum(
            GROUP_WEIGHTS[group] * self._available_group_coverage(valid, group)
            for group in GROUP_WEIGHTS
        )
        score = 0.0
        effective_weights: dict[str, float] = {}
        for group, group_weight in GROUP_WEIGHTS.items():
            group_items = [item for item in valid if item["group"] == group]
            group_coverage = self._available_group_coverage(valid, group)
            if not group_items or available_group_weight <= 0 or group_coverage <= 0:
                continue
            effective_group = group_weight * group_coverage / available_group_weight * 100.0
            raw_group_weight = sum(item["weight"] for item in group_items)
            for item in group_items:
                effective = effective_group * item["weight"] / raw_group_weight
                effective_weights[item["indicator_id"]] = effective
                score += item["z_score"] * effective / 100.0
        for item in components:
            effective = effective_weights.get(item["indicator_id"], 0.0)
            item["effective_weight"] = round(effective, 4)
            item["contribution"] = None if item["z_score"] is None else round(item["z_score"] * effective / 100.0, 4)
        return {
            "score": score,
            "coverage": round(available_group_weight, 2),
            "components": sorted(components, key=lambda item: abs(item["contribution"] or 0.0), reverse=True),
        }

    def _indicator_score_prepared(
        self,
        definition: LiquidityIndicatorDefinition,
        prepared: tuple[np.ndarray, np.ndarray, list[datetime]],
        as_of: datetime,
        *,
        change_days: int,
    ) -> dict[str, Any]:
        timestamps, values, dates = prepared
        end = int(np.searchsorted(timestamps, as_of.timestamp(), side="right"))
        base = {
            "indicator_id": definition.indicator_id,
            "name": definition.name,
            "short_label": definition.short_label,
            "group": definition.group_id,
            "group_label": definition.group_label,
            "group_description": GROUP_DESCRIPTIONS.get(definition.group_id),
            "weight": definition.raw_weight,
            "effective_weight": 0.0,
            "polarity": definition.polarity,
            "current_value": None,
            "score": None,
            "z_score": None,
            "percentile": None,
            "contribution": None,
            "change_pct": None,
            "last_updated": None,
            "data_lag_days": None,
            "missing_reason": None,
        }
        if end < 3:
            base["missing_reason"] = "insufficient_history"
            return base
        current_date = dates[end - 1]
        current_value = float(values[end - 1])
        window_start = int(np.searchsorted(
            timestamps, (as_of - timedelta(days=3650)).timestamp(), side="left",
        ))
        sample = values[window_start:end]
        if len(sample) < 3:
            base["missing_reason"] = "insufficient_window"
            return base
        if definition.group_id == "risk":
            risk_start = int(np.searchsorted(
                timestamps, (as_of - timedelta(days=730)).timestamp(), side="left",
            ))
            percentile = self._pressure_percentile(
                current_value, values[risk_start:end], definition.polarity,
            )
            z_score = self._percentile_to_z(percentile)
            indicator_score = percentile
        else:
            z_score = self._pressure_z(current_value, sample, definition.polarity)
            percentile = self._pressure_percentile(current_value, sample, definition.polarity)
            indicator_score = self._z_to_score(z_score)
        target = (current_date - timedelta(days=change_days)).timestamp()
        previous_index = int(np.searchsorted(timestamps[:end], target, side="right")) - 1
        previous = float(values[max(0, previous_index)])
        change = None if previous == 0 else (current_value - previous) / abs(previous) * 100.0
        base.update(
            {
                "current_value": current_value,
                "score": round(max(0.0, min(100.0, indicator_score)), 4),
                "z_score": round(z_score, 4),
                "percentile": round(percentile, 4),
                "change_pct": None if change is None else round(change, 4),
                "last_updated": current_date.isoformat(),
                "data_lag_days": max(0, (as_of.date() - current_date.date()).days),
            }
        )
        return base

    @staticmethod
    def thresholds(series: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "p20": PRESSURE_PERCENTILES["support"],
            "p50": PRESSURE_PERCENTILES["neutral"],
            "p80": PRESSURE_PERCENTILES["pressure"],
            "source": "rolling_5y_percentile",
            "sample_size": sum(item.get("score") is not None for item in series),
        }

    @staticmethod
    def score_percentile(score: float | None, values: list[float]) -> float | None:
        if score is None or not values:
            return None
        return LiquidityScoreEngine.score_percentile_sorted(score, sorted(values))

    @staticmethod
    def score_percentile_sorted(
        score: float | None,
        sorted_values: list[float],
    ) -> float | None:
        if score is None or not sorted_values:
            return None
        left = bisect_left(sorted_values, score)
        right = bisect_right(sorted_values, score)
        return max(
            0.0,
            min(100.0, (left + 0.5 * (right - left)) / len(sorted_values) * 100.0),
        )

    @staticmethod
    def state(score: float | None) -> tuple[str, str]:
        if score is None:
            return "等待数据", "neutral"
        if score <= PRESSURE_PERCENTILES["support"]:
            return "流动性宽松", "support"
        if score < PRESSURE_PERCENTILES["neutral"]:
            return "中性偏松", "support"
        if score < PRESSURE_PERCENTILES["pressure"]:
            return "中性偏紧", "pressure"
        return "流动性收紧", "pressure"

    @staticmethod
    def alerts(components: list[dict[str, Any]], *, change_days: int) -> list[str]:
        valid = [item for item in components if item.get("score") is not None]
        if not valid:
            return ["尚无足够宏观历史，完成数据刷新后才能生成美元流动性评分。"]
        output = []
        for item in valid[:4]:
            direction = "收紧压力" if item["score"] >= 50 else "流动性缓和"
            change = "--" if item["change_pct"] is None else f"{item['change_pct']:+.2f}%"
            output.append(
                f"{item['name']}当前指向{direction}，压力贡献 {(item.get('contribution') or 0.0):+.2f}，"
                f"{change_days} 日变化 {change}。"
            )
        return output

    def _indicator_score(
        self,
        definition: LiquidityIndicatorDefinition,
        points: list[tuple[datetime, float]],
        as_of: datetime,
        *,
        change_days: int,
    ) -> dict[str, Any]:
        base = {
            "indicator_id": definition.indicator_id,
            "name": definition.name,
            "short_label": definition.short_label,
            "group": definition.group_id,
            "group_label": definition.group_label,
            "group_description": GROUP_DESCRIPTIONS.get(definition.group_id),
            "weight": definition.raw_weight,
            "effective_weight": 0.0,
            "polarity": definition.polarity,
            "current_value": None,
            "score": None,
            "z_score": None,
            "percentile": None,
            "contribution": None,
            "change_pct": None,
            "last_updated": None,
            "data_lag_days": None,
            "missing_reason": None,
        }
        if len(points) < 3:
            base["missing_reason"] = "insufficient_history"
            return base
        points = sorted(points)
        current_date, current_value = points[-1]
        sample = [value for item_date, value in points if item_date >= as_of - timedelta(days=3650)]
        if len(sample) < 3:
            base["missing_reason"] = "insufficient_window"
            return base
        if definition.group_id == "risk":
            risk_sample = [value for item_date, value in points if item_date >= as_of - timedelta(days=730)]
            percentile = self._pressure_percentile(current_value, risk_sample, definition.polarity)
            z_score = self._percentile_to_z(percentile)
            indicator_score = percentile
        else:
            z_score = self._pressure_z(current_value, sample, definition.polarity)
            percentile = self._pressure_percentile(current_value, sample, definition.polarity)
            indicator_score = self._z_to_score(z_score)
        change = self._change_pct(points, lookback_days=change_days)
        base.update(
            {
                "current_value": current_value,
                "score": round(max(0.0, min(100.0, indicator_score)), 4),
                "z_score": round(z_score, 4),
                "percentile": round(percentile, 4),
                "change_pct": None if change is None else round(change, 4),
                "last_updated": current_date.isoformat(),
                "data_lag_days": max(0, (as_of.date() - current_date.date()).days),
            }
        )
        return base

    @staticmethod
    def _weekly_sample_dates(dates: list[datetime]) -> list[datetime]:
        sampled: list[datetime] = []
        seen: set[tuple[int, int]] = set()
        for item in reversed(dates):
            key = item.isocalendar()[:2]
            if key not in seen:
                seen.add(key)
                sampled.append(item)
        return list(reversed(sampled))

    @staticmethod
    def _points_until(points: list[tuple[datetime, float]], as_of: datetime) -> list[tuple[datetime, float]]:
        return [item for item in points if item[0] <= as_of]

    @staticmethod
    def _available_group_coverage(valid: list[dict[str, Any]], group: str) -> float:
        definitions = [item for item in SCORED_DEFINITIONS if item.group_id == group]
        available = {item["indicator_id"] for item in valid if item.get("z_score") is not None}
        total = sum(item.raw_weight for item in definitions)
        return 0.0 if total <= 0 else sum(item.raw_weight for item in definitions if item.indicator_id in available) / total

    @staticmethod
    def _pressure_z(current: float, sample: Any, polarity: str) -> float:
        values = np.asarray(sample, dtype=float)
        center = float(np.median(values))
        mad = float(np.median(np.abs(values - center)))
        denominator = 1.4826 * mad
        if denominator <= 0:
            denominator = float(np.std(values)) if len(values) > 1 else 0.0
        if denominator <= 0:
            return 0.0
        output = (current - center) / denominator
        if polarity == "lower_tightens":
            output *= -1
        return max(-4.0, min(4.0, output))

    @staticmethod
    def _pressure_percentile(current: float, sample: Any, polarity: str) -> float:
        values = np.asarray(sample, dtype=float)
        if len(values) <= 1:
            return 50.0
        below = int(np.count_nonzero(values < current))
        equal = int(np.count_nonzero(values == current))
        output = (below + 0.5 * equal) / len(values) * 100.0
        if polarity == "lower_tightens":
            output = 100.0 - output
        return max(0.0, min(100.0, output))

    @staticmethod
    def _z_to_score(value: float) -> float:
        return 0.5 * (1.0 + math.erf(value / (1.35 * math.sqrt(2.0)))) * 100.0

    @staticmethod
    def _percentile_to_z(value: float) -> float:
        probability = max(0.001, min(0.999, value / 100.0))
        return max(-4.0, min(4.0, NormalDist().inv_cdf(probability)))

    @staticmethod
    def _change_pct(points: list[tuple[datetime, float]], *, lookback_days: int) -> float | None:
        if len(points) < 2:
            return None
        current_date, current = points[-1]
        target = current_date - timedelta(days=lookback_days)
        previous = None
        for item_date, value in points:
            if item_date <= target:
                previous = value
            else:
                break
        if previous is None:
            previous = points[0][1]
        if previous == 0:
            return None
        return (current - previous) / abs(previous) * 100.0
