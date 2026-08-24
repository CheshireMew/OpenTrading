from __future__ import annotations

from datetime import datetime, timedelta

from app.contracts.dto.market_insight import DliLiquidityResponse
from app.domain.market.dli_catalog import DLI_SOURCE_IDS
from app.application.persistence_ports import IndicatorRepositoryPort
from app.services.market.dli_payload import DliPayloadBuilder
from app.services.market.dli_scoring import DliScoreEngine
from app.services.market.dli_series import DliSeriesBuilder


class DliLiquidityService:
    def __init__(
        self,
        repository: IndicatorRepositoryPort,
        *,
        series_builder: DliSeriesBuilder | None = None,
        score_engine: DliScoreEngine | None = None,
        payload_builder: DliPayloadBuilder | None = None,
    ) -> None:
        self.repository = repository
        self.series_builder = series_builder or DliSeriesBuilder()
        self.score_engine = score_engine or DliScoreEngine()
        self.payload_builder = payload_builder or DliPayloadBuilder()

    def build(self, *, days: int = 365, change_days: int = 30) -> DliLiquidityResponse:
        display_days = max(30, min(days, 3650))
        change_window_days = max(1, min(change_days, 365))
        now = datetime.now()
        model_cutoff = now - timedelta(days=3650)
        display_cutoff = now - timedelta(days=display_days)

        source_history = self.repository.get_history_points(list(DLI_SOURCE_IDS), start_date=model_cutoff)
        history_map = self.series_builder.with_derived_indicators(source_history)
        points_map = self.series_builder.points_map(history_map)
        meta_map = {item["id"]: item for item in self.repository.list_active_meta("Macro")}

        current = self.score_engine.composite_at(now, points_map, change_days=change_window_days)
        raw_history = self.score_engine.composite_history(
            points_map,
            start_date=now - timedelta(days=1825),
            end_date=now,
            change_days=change_window_days,
        )
        raw_values = [item["score"] for item in raw_history if item.get("score") is not None]
        thresholds = self.score_engine.thresholds(raw_history)
        raw_score = current["score"]
        score_percentile = self.score_engine.score_percentile(raw_score, raw_values)
        state, tone = self.score_engine.state(score_percentile, thresholds["p20"], thresholds["p50"], thresholds["p80"])
        display_history = [
            {
                "date": item["date"].isoformat(),
                "score": round(percentile, 2),
                "state": self.score_engine.state(percentile, thresholds["p20"], thresholds["p50"], thresholds["p80"])[0],
            }
            for item in raw_history
            for percentile in [self.score_engine.score_percentile(item["score"], raw_values)]
            if percentile is not None
            if item["date"] >= display_cutoff
        ]
        updated_at = self.series_builder.latest_update(history_map)

        return DliLiquidityResponse.model_validate({
            "score": None if score_percentile is None else round(score_percentile),
            "raw_score": None if raw_score is None else round(raw_score, 4),
            "score_percentile": None if score_percentile is None else round(score_percentile, 2),
            "state": state,
            "tone": tone,
            "updated_at": updated_at.isoformat() if updated_at else None,
            "coverage": current["coverage"],
            "methodology": "pressure_z_composite_percentile_v3",
            "thresholds": thresholds,
            "components": current["components"],
            "history": display_history,
            "indicators": self.payload_builder.indicator_payloads(history_map, meta_map, display_cutoff, as_of=now),
            "alerts": self.score_engine.alerts(current["components"], change_days=change_window_days),
        })
