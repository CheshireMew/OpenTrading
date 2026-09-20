from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.application.errors import InvalidRequestError
from app.application.persistence_ports import TradeSignalRepositoryPort
from app.application.model_contracts import TradeSetupModelOutput
from app.contracts.dto.market_insight import MarketIndicatorResponse
from app.domain.market.prompt_engine import PromptEngine
from app.domain.market.trade_setup import TradeSetupEngine, TradeSetupRequest, TradeSetupResult
from app.services.market.indicator_service import IndicatorService
from app.services.market.query_app_service import MarketQueryAppService
from app.infra.executor import run_database, run_external_io
from utils.logger import logger


class MarketInsightAppService:
    def __init__(
        self,
        *,
        indicator_service: IndicatorService,
        market_query_service: MarketQueryAppService,
        llm_client_factory: Callable[[], Any | None] | None = None,
        trade_signal_repository: TradeSignalRepositoryPort | None = None,
    ) -> None:
        self.indicator_service = indicator_service
        self.market_query_service = market_query_service
        self.llm_client_factory = llm_client_factory or (lambda: None)
        self.trade_signal_repository = trade_signal_repository
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
            result = self.trade_setup_engine.build_rules(
                request,
                kline_data,
                indicators,
            )
            await self._record_trade_signal(result, request=request, kline_data=kline_data, indicators=indicators)
            return result

        llm_client = await run_external_io(self.llm_client_factory)
        if not llm_client:
            result = self.trade_setup_engine.build_ai(
                request,
                kline_data,
                None,
                model_error_code="model_client_unavailable",
            )
            await self._record_trade_signal(result, request=request, kline_data=kline_data, indicators=indicators)
            return result
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
        result = self.trade_setup_engine.build_ai(
            request,
            kline_data,
            ai_payload,
            model_error_code=model_result.error_code,
        )
        await self._record_trade_signal(result, request=request, kline_data=kline_data, indicators=indicators)
        return result

    async def _record_trade_signal(
        self,
        result: TradeSetupResult,
        *,
        request: TradeSetupRequest,
        kline_data: list[list[float]],
        indicators: dict[str, Any],
    ) -> None:
        repository = self.trade_signal_repository
        if repository is None:
            return
        setup = result.setup
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expiry_days = {"Scalping": 1, "Intraday": 7, "Swing": 30}.get(request.style, 30)
        payload = {
            "symbol": result.symbol.upper(),
            "timeframe": result.timeframe,
            "source": result.source,
            "mode": request.mode,
            "signal_status": result.status,
            "side": setup.side if setup else None,
            "entry": setup.entry if setup else None,
            "target": setup.target if setup else None,
            "stop": setup.stop if setup else None,
            "risk_reward": setup.risk_reward if setup else None,
            "confidence": setup.confidence if setup else None,
            "risk_amount": setup.risk_amount if setup else None,
            "style": setup.style if setup else request.style,
            "strategy": setup.strategy if setup else request.strategy,
            "reason": result.reason,
            "error_code": result.error_code,
            "current_price": result.current_price,
            "entry_time": setup.entry_time if setup else (int(kline_data[-1][0]) if kline_data else None),
            "market_snapshot": {
                "indicators": indicators,
                "klines": kline_data[-120:],
                "accountSize": request.account_size,
                "generatedAt": result.timestamp,
            },
            "outcome_status": "pending" if setup is not None else "unavailable",
            "forward_returns": {},
            "expires_at": now + timedelta(days=expiry_days),
        }
        try:
            await run_database(lambda: repository.create_signal(payload))
        except Exception:
            logger.exception("Trade signal could not be persisted")
