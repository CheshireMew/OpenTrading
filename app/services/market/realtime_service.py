from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.application.model_contracts import MarketAnalysisModelOutput
from app.contracts.dto.market_history import RealtimeResponse
from app.contracts.market_history import build_realtime_response
from config import settings
from app.domain.market.constants import (
    DEFAULT_ATR_PERIOD,
    DEFAULT_VOLATILITY_PERIOD,
    periods_per_year_for_timeframe,
)
from app.domain.market.prompt_engine import PromptEngine
from app.domain.market.technical_analysis import TechnicalAnalysis
from app.services.market.market_data_service import MarketDataService


@dataclass(slots=True)
class MarketSnapshot:
    kline_data: list[list[float]]
    indicators: dict[str, Any]


class RealtimeService:
    def compute_market_snapshot(
        self,
        market_data_service: MarketDataService,
        symbol: str,
        timeframe: str,
        limit: int,
        *,
        atr_period: int = DEFAULT_ATR_PERIOD,
        volatility_period: int = DEFAULT_VOLATILITY_PERIOD,
    ) -> MarketSnapshot | None:
        kline_data = market_data_service.get_recent_candles(symbol, timeframe, limit=limit)
        if not kline_data:
            return None

        closes = [x[4] for x in kline_data]
        highs = [x[2] for x in kline_data]
        lows = [x[3] for x in kline_data]
        atr = TechnicalAnalysis.calculate_atr(highs, lows, closes, atr_period)
        atr_pct = TechnicalAnalysis.calculate_atr_pct(highs, lows, closes, atr_period)
        realized_volatility = TechnicalAnalysis.calculate_realized_volatility(closes, period=volatility_period)
        annualized_volatility = TechnicalAnalysis.calculate_annualized_volatility(
            closes,
            period=volatility_period,
            periods_per_year=periods_per_year_for_timeframe(timeframe),
        )
        macd = TechnicalAnalysis.calculate_macd(
            closes, settings.MACD_FAST, settings.MACD_SLOW, settings.MACD_SIGNAL
        )
        indicators = {
            "ema": TechnicalAnalysis.calculate_ema(closes, settings.EMA_PERIOD),
            "rsi": TechnicalAnalysis.calculate_rsi(closes, settings.RSI_PERIOD),
            "macd": {
                "dif": macd[0] if macd and macd[0] is not None else None,
                "dea": macd[1] if macd and macd[1] is not None else None,
                "histogram": macd[2] if macd and macd[2] is not None else None,
            }
            if macd
            else None,
            "atr": atr,
            "atr_pct": atr_pct,
            "realized_volatility_pct": realized_volatility * 100.0
            if realized_volatility is not None
            else None,
            "annualized_volatility_pct": annualized_volatility * 100.0
            if annualized_volatility is not None
            else None,
        }
        return MarketSnapshot(kline_data=kline_data, indicators=indicators)

    def build_response(
        self,
        symbol: str,
        timeframe: str | None,
        kline_data: list[list[float]],
        indicators: dict[str, Any],
        ai_analysis: Any = None,
        include_type: bool = False,
    ) -> RealtimeResponse:
        closes = [x[4] for x in kline_data]
        return build_realtime_response(
            symbol=symbol,
            timestamp=datetime.now().isoformat(),
            current_price=closes[-1],
            indicators=indicators,
            ai_analysis=ai_analysis,
            rows=kline_data,
            timeframe=timeframe,
            include_type=include_type,
        )

    async def maybe_run_ai(
        self,
        llm_client: Any,
        symbol: str,
        kline_data: list[list[float]],
        indicators: dict[str, Any],
    ) -> Any:
        if not llm_client:
            return None
        prompt = PromptEngine.build_analysis_prompt(
            symbol,
            kline_data,
            indicators,
        )
        result = await llm_client.analyze(
            prompt,
            response_model=MarketAnalysisModelOutput,
            purpose="realtime_market_analysis",
        )
        if result.succeeded:
            return result.output.model_dump(mode="json")
        return {
            "status": result.status,
            "error_code": result.error_code,
        }
