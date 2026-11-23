import pytest
from datetime import datetime, timezone
from app.services.market.history_query_service import MarketHistoryQueryService
from app.services.market.history_range_coordinator import OhlcvRangeResult

from app.services.market.query_app_service import MarketQueryAppService


class FakeMarketDataService:
    def __init__(self) -> None:
        self.calls = []

    def get_history_data(self, symbol, timeframe, end_ts, limit):
        self.calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "end_ts": end_ts,
                "limit": limit,
            }
        )
        return [[1717000000000, 1.0, 2.0, 0.5, 456.0, 1000.0]]


class FakeRealtimeService:
    pass


@pytest.mark.asyncio
async def test_live_tail_reads_cached_history_without_exchange_fetch():
    market_data_service = FakeMarketDataService()
    service = MarketQueryAppService(
        market_data_service=market_data_service,
        realtime_service=FakeRealtimeService(),
    )

    response = (await service.get_live_kline_tail(symbol="BTC/USDT", timeframe="1h", limit=16)).model_dump()

    assert response["current_price"] is None
    assert response["status"] == "stale"
    assert response["timestamp"].startswith("2024-")
    assert response["queried_at"] != response["timestamp"]
    assert len(market_data_service.calls) == 1
    assert market_data_service.calls[0]["symbol"] == "BTC/USDT"
    assert market_data_service.calls[0]["timeframe"] == "1h"
    assert market_data_service.calls[0]["limit"] == 16
    assert isinstance(market_data_service.calls[0]["end_ts"], int)


@pytest.mark.asyncio
async def test_bounded_history_uses_utc_and_does_not_extend_old_signals_to_today():
    calls = []
    class History:
        def load_ohlcv_range(self, symbol, timeframe, start, end, **kwargs):
            calls.append((start, end))
            return OhlcvRangeResult([], [])
    await MarketHistoryQueryService(market_data_service=History()).get_full_history(
        symbol="BTC/USDT", timeframe="1h", start_date="2020-01-01", end_date="2020-01-02")
    assert calls == [(datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2020, 1, 2, 23, 59, 59, 999000, tzinfo=timezone.utc))]
