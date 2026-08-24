from __future__ import annotations

from typing import Any, Callable

from app.contracts.dto.market_history import RealtimeResponse
from app.exceptions import ServiceUnavailableError
from app.infra.executor import run_external_io
from app.services.market.app_service_support import validate_market_request
from app.services.market.market_data_service import MarketDataService
from app.services.market.realtime_service import MarketSnapshot, RealtimeService
from config import settings
from utils.logger import logger


class MarketRealtimeQueryService:
    def __init__(
        self,
        *,
        market_data_service: MarketDataService,
        realtime_service: RealtimeService,
        llm_client_factory: Callable[[], Any | None] | None = None,
    ) -> None:
        self.market_data_service = market_data_service
        self.realtime_service = realtime_service
        self.llm_client_factory = llm_client_factory or (lambda: None)

    async def load_snapshot(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> MarketSnapshot:
        validate_market_request(symbol, timeframe)
        result = await run_external_io(
            lambda: self.realtime_service.compute_market_snapshot(
                self.market_data_service,
                symbol,
                timeframe,
                limit,
            )
        )
        if not result:
            raise RuntimeError("获取数据失败")
        return result

    async def get_realtime(
        self,
        *,
        symbol: str,
        timeframe: str | None,
        limit: int | None,
    ) -> RealtimeResponse:
        resolved_timeframe = timeframe or settings.TIMEFRAME
        resolved_limit = limit or settings.LIMIT
        try:
            return await self._build_realtime_response(
                symbol=symbol,
                timeframe=resolved_timeframe,
                limit=resolved_limit,
                use_ai=True,
                include_type=False,
                ai_log_context="HTTP",
            )
        except Exception as exc:
            err_str = str(exc).lower()
            if "network" in err_str or "connection" in err_str or "timeout" in err_str:
                logger.error(f"实时行情连接失败: {exc}")
                raise ServiceUnavailableError("无法连接到交易所 (Network Error)") from exc
            raise
    async def get_realtime_ws_payload(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        use_ai: bool,
    ) -> RealtimeResponse:
        return await self._build_realtime_response(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            use_ai=use_ai,
            include_type=True,
            ai_log_context="WebSocket",
        )

    async def _build_realtime_response(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        use_ai: bool,
        include_type: bool,
        ai_log_context: str,
    ) -> RealtimeResponse:
        snapshot = await self.load_snapshot(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        kline_data = snapshot.kline_data
        indicators = snapshot.indicators
        ai_analysis = await self._run_ai_analysis(
            symbol=symbol,
            kline_data=kline_data,
            indicators=indicators,
            enabled=use_ai,
            log_context=ai_log_context,
        )
        return self.realtime_service.build_response(
            symbol,
            timeframe,
            kline_data,
            indicators,
            ai_analysis=ai_analysis,
            include_type=include_type,
        )

    async def _run_ai_analysis(
        self,
        *,
        symbol: str,
        kline_data: Any,
        indicators: Any,
        enabled: bool,
        log_context: str,
    ) -> Any | None:
        if not enabled:
            return None
        llm_client = self.llm_client_factory()
        if llm_client is None:
            return None
        try:
            return await self.realtime_service.maybe_run_ai(
                llm_client,
                symbol,
                kline_data,
                indicators,
            )
        except Exception as exc:
            logger.warning(f"{log_context} AI 分析失败: {exc}")
            return None
