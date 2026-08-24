from __future__ import annotations

from dataclasses import asdict

from fastapi import Depends, Query

from app.contracts.frontend import FrontendContractRouter
from app.dependencies import get_market_insight_service
from app.contracts.dto.market_insight import (
    MarketIndicatorResponse,
    TradeSetupResponse,
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


@router.get("/trade-setup", response_model=TradeSetupResponse)
async def get_trade_setup(
    symbol: str = Query(..., description="交易对，如 BTC/USDT"),
    timeframe: str = Query("1h", description="时间周期，如 1h"),
    limit: int = Query(120, ge=30, le=settings.API_MAX_LIMIT),
    account_size: float = Query(1000, ge=0),
    style: str = Query("Scalping"),
    strategy: str = Query("最大收益"),
    mode: str = Query("rules", pattern="^(rules|ai)$"),
    service = Depends(get_market_insight_service),
):
    result = await service.get_trade_setup(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        account_size=account_size,
        style=style,
        strategy=strategy,
        mode=mode,
    )
    return TradeSetupResponse.model_validate(asdict(result))


