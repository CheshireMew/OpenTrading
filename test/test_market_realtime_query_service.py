import pytest
from types import SimpleNamespace
from datetime import datetime, timezone
from app.domain.market.candles import RecentCandles
from app.domain.market.prompt_engine import PromptEngine

from app.services.market.realtime_query_service import MarketRealtimeQueryService
from app.services.market.realtime_service import MarketSnapshot, RealtimeService


class RecordingRealtimeService:
    def __init__(self) -> None:
        self.calls = []

    def compute_market_snapshot(
        self,
        market_data_service,
        symbol,
        timeframe,
        limit,
    ):
        self.calls.append(
            {
                "market_data_service": market_data_service,
                "symbol": symbol,
                "timeframe": timeframe,
                "limit": limit,
            }
        )
        return MarketSnapshot(kline_data=[[1, 2, 3, 1, 2, 10]], indicators={})


class FakeMarketDataService:
    def get_recent_candles(self, symbol, timeframe, limit):
        return [
            [
                1710000000000 + index * 86_400_000,
                100.0 + index,
                103.0 + index,
                98.0 + index,
                101.0 + index,
                1000.0 + index,
            ]
            for index in range(limit)
        ]

    def get_recent_candle_snapshot(self, symbol, timeframe, limit):
        return RecentCandles(self.get_recent_candles(symbol, timeframe, limit), int(datetime.now(timezone.utc).timestamp() * 1000), "exchange")


@pytest.mark.asyncio
async def test_load_snapshot_delegates_request_without_indicator_period_overrides():
    realtime_service = RecordingRealtimeService()
    market_data_service = object()
    service = MarketRealtimeQueryService(
        market_data_service=market_data_service,
        realtime_service=realtime_service,
    )

    snapshot = await service.load_snapshot(symbol="BTC/USDT", timeframe="1d", limit=100)

    assert snapshot.kline_data
    assert realtime_service.calls == [
        {
            "market_data_service": market_data_service,
            "symbol": "BTC/USDT",
            "timeframe": "1d",
            "limit": 100,
        }
    ]


@pytest.mark.asyncio
async def test_get_realtime_uses_default_periods_with_real_snapshot_service():
    service = MarketRealtimeQueryService(
        market_data_service=FakeMarketDataService(),
        realtime_service=RealtimeService(),
    )

    response = (await service.get_realtime(symbol="BTC/USDT", timeframe="1d", limit=100)).model_dump()

    assert response["symbol"] == "BTC/USDT"
    assert response["timeframe"] == "1d"
    assert response["indicators"]["atr"] is not None
    assert response["indicators"]["realized_volatility_pct"] is not None


@pytest.mark.asyncio
async def test_real_indicator_snapshot_reaches_model_with_macd_dictionary():
    prompts = []

    class Model:
        async def analyze(self, prompt, **kwargs):
            prompts.append(prompt)
            return SimpleNamespace(succeeded=True, output=SimpleNamespace(model_dump=lambda **kwargs: {"signal": "HOLD"}))

    response = await MarketRealtimeQueryService(market_data_service=FakeMarketDataService(),
        realtime_service=RealtimeService(), llm_client_factory=Model).get_realtime(symbol="BTC/USDT", timeframe="1d", limit=100)
    assert len(prompts) == 1
    assert "DIF=" in prompts[0] and "DEA=" in prompts[0] and "Histogram=" in prompts[0]
    assert response.ai_analysis == {"signal": "HOLD"}


def test_prompt_handles_zero_and_partially_available_indicators():
    prompt = PromptEngine.build_analysis_prompt("BTC", [[0, 1, 1, 1, 1, 1]],
        {"ema": 0, "rsi": 0, "atr": 0, "macd": {"dif": 0, "dea": None, "histogram": None}})
    assert "RSI (14): 0.00" in prompt
    assert "DIF=0.00, DEA=N/A, Histogram=N/A" in prompt


@pytest.mark.asyncio
async def test_stale_realtime_candles_do_not_look_current_or_reach_ai():
    class StaleMarket(FakeMarketDataService):
        def get_recent_candle_snapshot(self, symbol, timeframe, limit):
            rows = self.get_recent_candles(symbol, timeframe, limit)
            return RecentCandles(rows, int(rows[-1][0]) + 86_400_000, "cached_history")
    service = MarketRealtimeQueryService(market_data_service=StaleMarket(), realtime_service=RealtimeService(),
        llm_client_factory=lambda: (_ for _ in ()).throw(AssertionError("stale data must not invoke a model")))
    response = await service.get_realtime(symbol="BTC/USDT", timeframe="1d", limit=100)
    assert response.status == "stale"
    assert response.current_price is None and response.indicators.rsi is None
    assert response.ai_analysis is None
    assert response.timestamp.startswith("2024-")
    assert response.queried_at != response.timestamp
    assert len(response.kline_data) == 100
