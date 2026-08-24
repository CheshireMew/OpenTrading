from __future__ import annotations

from datetime import datetime, timedelta

from app.contracts.dto.market_insight import MarketIndicatorResponse
from app.application.persistence_ports import IndicatorRepositoryPort


INDICATOR_DISPLAY_FACTORS = {
    # Mempool returns hashrate as H/s while the market indicator contract exposes EH/s.
    "HASHRATE": 1 / 1_000_000_000_000_000_000,
    # Bitcoin difficulty is a raw dimensionless target value; the UI contract exposes trillions.
    "DIFFICULTY": 1 / 1_000_000_000_000,
}


def _to_display_value(indicator_id: str, value: float) -> float:
    return value * INDICATOR_DISPLAY_FACTORS.get(indicator_id, 1.0)


class IndicatorService:
    def __init__(self, repository: IndicatorRepositoryPort) -> None:
        self.repository = repository

    def get_indicators(
        self,
        category: str | None,
        days: int,
    ) -> list[MarketIndicatorResponse]:
        cutoff_date = datetime.now() - timedelta(days=days)
        metas = self.repository.list_active_meta(category)
        history_map = self.repository.get_history_points([meta["id"] for meta in metas], start_date=cutoff_date)

        result: list[MarketIndicatorResponse] = []
        for meta in metas:
            history = [
                {"date": item["date"], "value": _to_display_value(meta["id"], item["value"])}
                for item in history_map.get(meta["id"], [])
            ]
            result.append(
                MarketIndicatorResponse(
                    indicator_id=meta["id"],
                    name=meta["name"],
                    category=meta["category"],
                    unit=meta["unit"],
                    current_value=history[-1]["value"] if history else None,
                    last_updated=history[-1]["date"] if history else None,
                    history=history,
                )
            )
        return result
