from __future__ import annotations

from typing import Any

from .blend_service import FactorBlendService
from .detail_service import FactorDetailService
from .math_utils import FactorMath


class FactorAnalysisService:
    def __init__(self, math: FactorMath) -> None:
        self.detail_service = FactorDetailService(math)
        self.blend_service = FactorBlendService(math)

    def analyze_factor(self, **kwargs):
        return self.detail_service.analyze_factor(**kwargs)

    def build_blend(self, **kwargs):
        return self.blend_service.build_blend(**kwargs)

    def build_summary(
        self,
        *,
        dataset: dict[str, Any],
        symbol: str,
        timeframe: str,
        days: int,
        primary_horizon: int,
        max_lag_bars: int,
        factor_count: int,
        blend: dict[str, Any],
    ) -> dict[str, Any]:
        sample_range = (dataset.get("dataset_info") or {}).get("sample_range") or {}
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "days": days,
            "horizon_bars": primary_horizon,
            "max_lag_bars": max_lag_bars,
            "factor_count": factor_count,
            "dataset_id": dataset["id"],
            "forward_horizons": list(dataset.get("forward_horizons") or []),
            "sample_range": {
                "start": sample_range.get("start") or dataset["start_date"].isoformat(),
                "end": sample_range.get("end") or dataset["end_date"].isoformat(),
            },
            "target_label": f"未来 {primary_horizon} 根 K 线收益",
            "blend_factor_count": len(blend.get("selected_factors") or []),
        }
