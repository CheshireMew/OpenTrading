from __future__ import annotations
from app.contracts.dto.market_insight import MarketIndicatorResponse
from app.services.market.indicator_service import IndicatorService
from app.infra.executor import run_database

class MarketInsightAppService:
    def __init__(self, *, indicator_service: IndicatorService):
        self.indicator_service = indicator_service

    def get_indicators(self, category: str | None, days: int) -> list[MarketIndicatorResponse]:
        return self.indicator_service.get_indicators(category=category, days=days)

    async def get_indicators_async(self, category: str | None, days: int) -> list[MarketIndicatorResponse]:
        return await run_database(lambda: self.get_indicators(category, days))
