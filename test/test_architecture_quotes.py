import time
from types import SimpleNamespace

import pytest

from app.services.market.price_query_service import MarketPriceQueryService
from app.services.market.binance_market_snapshot_service import BinanceMarketSnapshotService


@pytest.mark.asyncio
async def test_stale_candle_is_not_a_current_quote_or_given_query_timestamp():
    service = MarketPriceQueryService(market_data_service=SimpleNamespace(get_history_data=lambda *args: [[1704067200000, 100, 100, 100, 100, 1]]))
    result = await service.get_current_price(symbol="BTC/USDT", timeframe="1d")
    assert result.current_price is None
    assert result.status == "stale"
    assert result.timestamp.startswith("2024-01-01")
    assert result.queried_at != result.timestamp


@pytest.mark.asyncio
async def test_stale_streams_fail_health_and_never_mix_futures_into_spot(monkeypatch):
    service = BinanceMarketSnapshotService()
    service._running = service._seed_completed = True
    service._seed_success_count = 1
    now = int(time.time() * 1000)
    await service._store.merge_tickers("spot_ticker", [{"symbol": "BTCUSDT", "last_price": 100, "close_time": now}])
    await service._store.merge_tickers("usdm_ticker", [{"symbol": "BTCUSDT", "last_price": 110, "close_time": now}])
    await service._store.merge_marks([{"symbol": "BTCUSDT", "mark_price": 111, "time": now}])
    assert await service.get_current_price("BTC/USDT") == 100
    assert await service.get_current_price("binance:usdm:BTCUSDT") == 111
    assert service.health_snapshot()["status"] == "ready"
    monkeypatch.setattr("app.services.market.binance_market_snapshot_store.time.time", lambda: now / 1000 + 180)
    assert service.health_snapshot()["status"] == "stale"
    assert await service.get_current_price("BTC/USDT") is None
    snapshot = await service.get_market_page_snapshot_data()
    assert snapshot["load_errors"]
    assert snapshot["spot_ticker"]["items"] == []
