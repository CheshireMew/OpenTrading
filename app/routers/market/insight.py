from __future__ import annotations


from fastapi import Depends, Query

from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_market_insight_service
from app.contracts.dto.market_insight import (
    MarketIndicatorResponse,
)
from config import settings


router = FrontendContractRouter(frontend_contract_target="market", tags=["Market Data"])


@router.get("/indicators", response_model=list[MarketIndicatorResponse])
async def get_market_indicators(
    category: str | None = Query(None, description="过滤分类, 如 Macro, Onchain, Sentiment, General"),
    days: int = Query(settings.INDICATORS_DEFAULT_DAYS, description="历史数据天数"),
    service = Depends(get_market_insight_service),
):
    return await service.get_indicators_async(category=category, days=days)


