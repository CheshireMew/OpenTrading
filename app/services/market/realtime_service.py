from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
from app.domain.market.prompt_engine import MarketIndicators, PromptEngine
from app.domain.market.technical_analysis import TechnicalAnalysis
from app.domain.market.candles import RecentCandles
from app.services.market.market_data_service import MarketDataService


@dataclass(slots=True)
class MarketSnapshot:
    kline_data: list[list[float]]
    indicators: MarketIndicators
    observed_at_ms: int | None = None
    source: str = "unavailable"

    def fresh(self) -> bool:
        return RecentCandles(self.kline_data, self.observed_at_ms, self.source).fresh(
            int(datetime.now(timezone.utc).timestamp() * 1000), settings.MARKET_QUOTE_MAX_AGE_SECONDS)


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
        candles = market_data_service.get_recent_candle_snapshot(symbol, timeframe, limit=limit)
        kline_data = candles.rows
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
        indicators: MarketIndicators = {
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
        return MarketSnapshot(kline_data=kline_data, indicators=indicators, observed_at_ms=candles.observed_at_ms, source=candles.source)

    def build_response(
        self,
        symbol: str,
        timeframe: str | None,
        kline_data: list[list[float]],
        indicators: MarketIndicators,
        ai_analysis: Any = None,
        include_type: bool = False,
        observed_at_ms: int | None = None,
        source: str = "unavailable",
    ) -> RealtimeResponse:
        closes = [x[4] for x in kline_data]
        now = datetime.now(timezone.utc)
        fresh = RecentCandles(kline_data, observed_at_ms, source).fresh(int(now.timestamp() * 1000), settings.MARKET_QUOTE_MAX_AGE_SECONDS)
        observed = datetime.fromtimestamp(observed_at_ms / 1000, timezone.utc).isoformat() if observed_at_ms is not None else None
        return build_realtime_response(
            symbol=symbol,
            timestamp=observed,
            current_price=closes[-1] if fresh else None,
            indicators=indicators if fresh else {key: None for key in ("ema", "rsi", "macd", "atr")},
            ai_analysis=ai_analysis if fresh else None,
            rows=kline_data,
            timeframe=timeframe,
            include_type=include_type,
            status="fresh" if fresh else "stale" if observed is not None else "unavailable",
            source=source, queried_at=now.isoformat(),
            valid_until=datetime.fromtimestamp(observed_at_ms / 1000 + settings.MARKET_QUOTE_MAX_AGE_SECONDS, timezone.utc).isoformat() if observed_at_ms is not None else None,
        )

    async def maybe_run_ai(
        self,
        llm_client: Any,
        symbol: str,
        kline_data: list[list[float]],
        indicators: MarketIndicators,
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
