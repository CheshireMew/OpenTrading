from __future__ import annotations

import math
from datetime import datetime, timedelta
from statistics import NormalDist, median, pstdev
from typing import Any

from app.domain.market.dli_catalog import (
    DLI_SCORING_DEFINITIONS,
    DLI_SCORING_IDS,
    DliIndicatorDefinition,
    GROUP_DESCRIPTIONS,
    GROUP_WEIGHTS,
)
from app.domain.market.math import percentage_change


class DliScoreEngine:
    def composite_history(
        self,
        points_map: dict[str, list[tuple[datetime, float]]],
        *,
        start_date: datetime,
        end_date: datetime,
        change_days: int,
    ) -> list[dict[str, Any]]:
        raw_dates = sorted(
            {
                timestamp
                for indicator_id in DLI_SCORING_IDS
                for timestamp, _value in points_map.get(indicator_id, [])
                if start_date <= timestamp <= end_date
            }
        )
        series = []
        for date in self._weekly_sample_dates(raw_dates):
            composite = self.composite_at(date, points_map, change_days=change_days)
            if composite["score"] is not None:
                series.append({"date": date, "score": composite["score"]})
        return series

    def composite_at(
        self,
        as_of: datetime,
        points_map: dict[str, list[tuple[datetime, float]]],
        *,
        change_days: int,
    ) -> dict[str, Any]:
        components = []
        for definition in DLI_SCORING_DEFINITIONS:
            points = self._points_until(points_map.get(definition.id, []), as_of)
            components.append(self._indicator_score(definition, points, as_of, change_days=change_days))

        valid = [item for item in components if item["z_score"] is not None]
        if not valid:
            return {"score": None, "coverage": 0.0, "components": components}

        total_available_group_weight = sum(
            GROUP_WEIGHTS[group] * self._available_group_coverage(valid, group)
            for group in GROUP_WEIGHTS
        )
        score = 0.0
        effective_weights: dict[str, float] = {}
        for group, group_weight in GROUP_WEIGHTS.items():
            group_items = [item for item in valid if item["group"] == group]
            if not group_items or total_available_group_weight <= 0:
                continue
            group_coverage = self._available_group_coverage(valid, group)
            if group_coverage <= 0:
                continue
            effective_group_weight = group_weight * group_coverage / total_available_group_weight * 100.0
            group_raw_weight = sum(item["weight"] for item in group_items)
            if group_raw_weight <= 0:
                continue
            for item in group_items:
                effective_weight = effective_group_weight * item["weight"] / group_raw_weight
                effective_weights[item["indicator_id"]] = effective_weight
                score += item["z_score"] * effective_weight / 100.0

        for item in components:
            effective_weight = effective_weights.get(item["indicator_id"], 0.0)
            item["effective_weight"] = round(effective_weight, 4)
            item["contribution"] = None if item["z_score"] is None else round(item["z_score"] * effective_weight / 100.0, 4)

        original_available_weight = sum(
            GROUP_WEIGHTS[group] * self._available_group_coverage(valid, group)
            for group in GROUP_WEIGHTS
        )
        return {
            "score": score,
            "coverage": round(original_available_weight, 2),
            "components": sorted(
                components,
                key=lambda item: abs(item["contribution"] or 0.0),
                reverse=True,
            ),
        }

    @staticmethod
    def thresholds(series: list[dict[str, Any]]) -> dict[str, Any]:
        values = [item["score"] for item in series if item.get("score") is not None]
        return {"p20": 20.0, "p50": 50.0, "p80": 80.0, "source": "rolling_5y_percentile", "sample_size": len(values)}

    @staticmethod
    def score_percentile(score: float | None, values: list[float]) -> float | None:
        if score is None or not values:
            return None
        below = sum(1 for value in values if value < score)
        equal = sum(1 for value in values if value == score)
        percentile = ((below + 0.5 * equal) / len(values)) * 100.0
        return max(0.0, min(100.0, percentile))

    @staticmethod
    def state(score: float | None, p20: float, p50: float, p80: float) -> tuple[str, str]:
        if score is None:
            return "等待数据", "neutral"
        if score <= p20:
            return "流动性宽松", "support"
        if score < p50:
            return "中性偏松", "support"
        if score < p80:
            return "中性偏紧", "pressure"
        return "流动性收紧", "pressure"

    @staticmethod
    def alerts(components: list[dict[str, Any]], *, change_days: int = 30) -> list[str]:
        valid = [item for item in components if item.get("score") is not None]
        if not valid:
            return ["等待后台采集宏观指标后生成评分。"]
        alerts = []
        for item in valid[:4]:
            direction = "收紧压力" if item["score"] >= 50 else "流动性缓和"
            change = "--" if item["change_pct"] is None else f"{item['change_pct']:+.2f}%"
            contribution = item.get("contribution") or 0.0
            display_name = item.get("name") or item.get("short_label") or item["indicator_id"]
            alerts.append(
                f"{display_name}当前指向{direction}，DLI 压力贡献 {contribution:+.2f}，{change_days} 日变化 {change}。"
            )
        return alerts

    @staticmethod
    def _weekly_sample_dates(dates: list[datetime]) -> list[datetime]:
        sampled: list[datetime] = []
        seen_weeks: set[tuple[int, int]] = set()
        for date in reversed(dates):
            key = date.isocalendar()[:2]
            if key in seen_weeks:
                continue
            seen_weeks.add(key)
            sampled.append(date)
        return list(reversed(sampled))

    def _indicator_score(
        self,
        definition: DliIndicatorDefinition,
        points: list[tuple[datetime, float]],
        as_of: datetime,
        *,
        change_days: int,
    ) -> dict[str, Any]:
        base = {
            "indicator_id": definition.id,
            "name": definition.label,
            "short_label": definition.short_label,
            "group": definition.group,
            "group_label": definition.group_label,
            "group_description": GROUP_DESCRIPTIONS.get(definition.group),
            "weight": definition.weight,
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

        points = sorted(points, key=lambda item: item[0])
        current_date, current_value = points[-1]
        sample = [value for date, value in points if date >= as_of - timedelta(days=3650)]
        if len(sample) < 3:
            base["missing_reason"] = "insufficient_window"
            return base

        if definition.group == "risk":
            risk_sample = [value for date, value in points if date >= as_of - timedelta(days=730)]
            percentile = self._pressure_percentile(current_value, risk_sample, definition.polarity)
            z_score = self._percentile_to_z_score(percentile)
            score = percentile
        else:
            z_score = self._pressure_z_score(current_value, sample, definition.polarity)
            percentile = self._pressure_percentile(current_value, sample, definition.polarity)
            score = self._z_to_score(z_score)
        change_pct = self._change_pct(points, lookback_days=change_days)
        base.update(
            {
                "current_value": current_value,
                "score": round(max(0.0, min(100.0, score)), 4),
                "z_score": round(z_score, 4),
                "percentile": round(percentile, 4),
                "change_pct": None if change_pct is None else round(change_pct, 4),
                "last_updated": current_date.isoformat(),
                "data_lag_days": max(0, (as_of.date() - current_date.date()).days),
            }
        )
        return base

    @staticmethod
    def _points_until(points: list[tuple[datetime, float]], as_of: datetime) -> list[tuple[datetime, float]]:
        if not points:
            return []
        left = 0
        right = len(points)
        while left < right:
            mid = (left + right) // 2
            if points[mid][0] <= as_of:
                left = mid + 1
            else:
                right = mid
        return points[:left]

    @staticmethod
    def _available_group_coverage(valid: list[dict[str, Any]], group: str) -> float:
        definitions = [definition for definition in DLI_SCORING_DEFINITIONS if definition.group == group]
        if not definitions:
            return 0.0
        available = {item["indicator_id"] for item in valid if item.get("z_score") is not None}
        group_weight = sum(definition.weight for definition in definitions)
        if group_weight <= 0:
            return 0.0
        available_weight = sum(definition.weight for definition in definitions if definition.id in available)
        return available_weight / group_weight

    @staticmethod
    def _pressure_z_score(current: float, sample: list[float], polarity: str) -> float:
        center = median(sample)
        deviations = [abs(value - center) for value in sample]
        mad = median(deviations)
        denom = 1.4826 * mad
        if denom <= 0:
            denom = pstdev(sample) if len(sample) > 1 else 0.0
        if denom <= 0:
            return 0.0
        z_score = (current - center) / denom
        if polarity == "lower_tightens":
            z_score *= -1.0
        return max(-4.0, min(4.0, z_score))

    @staticmethod
    def _pressure_percentile(current: float, sample: list[float], polarity: str) -> float:
        if len(sample) <= 1:
            return 50.0
        below = sum(1 for value in sample if value < current)
        equal = sum(1 for value in sample if value == current)
        percentile = ((below + 0.5 * equal) / len(sample)) * 100.0
        if polarity == "lower_tightens":
            percentile = 100.0 - percentile
        return max(0.0, min(100.0, percentile))

    @staticmethod
    def _z_to_score(z_score: float) -> float:
        return 0.5 * (1.0 + math.erf(z_score / (1.35 * math.sqrt(2.0)))) * 100.0

    @staticmethod
    def _percentile_to_z_score(percentile: float) -> float:
        probability = max(0.001, min(0.999, percentile / 100.0))
        return max(-4.0, min(4.0, NormalDist().inv_cdf(probability)))

    @staticmethod
    def _change_pct(points: list[tuple[datetime, float]], *, lookback_days: int = 30) -> float | None:
        if len(points) < 2:
            return None
        current_date, current = points[-1]
        target_date = current_date - timedelta(days=lookback_days)
        previous = None
        for date, value in points:
            if date <= target_date:
                previous = value
            else:
                break
        if previous is None:
            previous = points[0][1]
        if previous == 0:
            return None
        return percentage_change(current, previous, absolute_baseline=True)
