from __future__ import annotations

from typing import Any, Callable

from app.application.errors import InvalidRequestError
from app.application.model_contracts import TradeSetupModelOutput
from app.contracts.dto.market_insight import MarketIndicatorResponse
from app.domain.market.prompt_engine import PromptEngine
from app.domain.market.trade_setup import TradeSetupEngine, TradeSetupRequest, TradeSetupResult
from app.services.market.indicator_service import IndicatorService
from app.services.market.query_app_service import MarketQueryAppService
from app.infra.executor import run_database, run_external_io


class MarketInsightAppService:
    def __init__(
        self,
        *,
        indicator_service: IndicatorService,
        market_query_service: MarketQueryAppService,
        llm_client_factory: Callable[[], Any | None] | None = None,
    ) -> None:
        self.indicator_service = indicator_service
        self.market_query_service = market_query_service
        self.llm_client_factory = llm_client_factory or (lambda: None)
        self.trade_setup_engine = TradeSetupEngine()

    def get_indicators(
        self,
        category: str | None,
        days: int,
    ) -> list[MarketIndicatorResponse]:
        return self.indicator_service.get_indicators(category=category, days=days)

    async def get_indicators_async(
        self,
        category: str | None,
        days: int,
    ) -> list[MarketIndicatorResponse]:
        return await run_database(lambda: self.get_indicators(category=category, days=days))

    async def get_trade_setup(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        account_size: float,
        style: str,
        strategy: str,
        mode: str,
    ) -> TradeSetupResult:
        if mode not in {"rules", "ai"}:
            raise InvalidRequestError("无效判断方式。可选: rules, ai")

        snapshot = await self.market_query_service.load_snapshot(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        kline_data = snapshot.kline_data
        indicators = snapshot.indicators
        request = TradeSetupRequest(
            symbol=symbol,
            timeframe=timeframe,
            account_size=account_size,
            style=style,
            strategy=strategy,
            mode=mode,
        )
        if mode == "rules":
            return self.trade_setup_engine.build_rules(
                request,
                kline_data,
                indicators,
            )

        llm_client = await run_external_io(self.llm_client_factory)
        if not llm_client:
            return self.trade_setup_engine.build_ai(
                request,
                kline_data,
                None,
                model_error_code="model_client_unavailable",
            )
        prompt = PromptEngine.build_trade_setup_prompt(
            symbol,
            timeframe,
            kline_data,
            indicators,
            account_size,
            style,
            strategy,
        )
        model_result = await llm_client.analyze(
            prompt,
            response_model=TradeSetupModelOutput,
            purpose="trade_setup",
        )
        ai_payload = model_result.output.model_dump(mode="json") if model_result.succeeded else None
        return self.trade_setup_engine.build_ai(
            request,
            kline_data,
            ai_payload,
            model_error_code=model_result.error_code,
        )
