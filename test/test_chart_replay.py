import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from app.contracts.chart_workspace import ChartBar, ChartBars, ChartSymbol
from app.routers.chart_workspace import chart_replay_bars
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.public_site import public_route
from app.services.market.history_range_coordinator import HistoryRangeCoordinator


@pytest.mark.asyncio
async def test_replay_history_shares_concurrent_requests_and_excludes_future_and_forming_bars():
    market = ChartWorkspaceMarket(None, None)
    symbol = ChartSymbol(id="binance:spot:BTCUSDT", symbol="BTCUSDT", name="BTC", exchange="binance", market="spot", currency="USDT", timeframes=["1m"])
    calls = []
    release = asyncio.Event()

    async def bars(*args):
        calls.append(args)
        await release.wait()
        return ChartBars(symbol=symbol, timeframe="1m", source="fixture", bars=[
            ChartBar(time=0, open=100, high=105, low=95, close=102, closeTime=60000, closed=True),
            ChartBar(time=60000, open=102, high=108, low=101, close=107, closeTime=120000, closed=True),
            ChartBar(time=120000, open=107, high=108, low=100, close=105, closeTime=180000, closed=False),
        ])

    market.bars = bars
    first = asyncio.create_task(market.replay_bars(symbol.id, "1m", 1000, 0, 60000))
    second = asyncio.create_task(market.replay_bars(symbol.id, "1m", 1000, 0, 60000))
    await asyncio.sleep(0)
    release.set()
    try:
        a, b = await asyncio.gather(first, second)
        assert len(calls) == 1
        assert calls[0][-1] == 59999
        assert [bar.time for bar in a.bars] == [0]
        assert a == b
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_replay_route_validates_ranges_and_public_history_cache():
    class Market:
        async def replay_bars(self, *args):
            return SimpleNamespace(bars=[1])

    service = SimpleNamespace(market=Market())
    response = Response()
    await chart_replay_bars(response, "asset", "1m", 120000, 0, 1000, service)
    assert response.headers["cache-control"] == "public, max-age=86400"
    with pytest.raises(HTTPException) as error:
        await chart_replay_bars(Response(), "asset", "1m", 60000, 60000, 1000, service)
    assert error.value.status_code == 422
    assert public_route(SimpleNamespace(name="chart_replay_bars"))


@pytest.mark.asyncio
@pytest.mark.parametrize("cached_count", [0, 2])
async def test_replay_downloads_only_missing_minutes_near_the_start_and_reuses_them(cached_count):
    start, step = 1577836800000, 60000
    source = [[start + i * step, 100, 102, 99, 101, 2] for i in range(5)]

    class Store:
        def __init__(self):
            self.rows = {int(row[0]): row for row in source[:cached_count]}

        def get_range(self, symbol, timeframe, since, until):
            return [row for time, row in sorted(self.rows.items()) if since <= time <= until]

        def save(self, symbol, timeframe, rows):
            self.rows.update({int(row[0]): row for row in rows})

    store, requests = Store(), []
    market = ChartWorkspaceMarket(None, None)
    market.history_ranges = HistoryRangeCoordinator(store)
    symbol = ChartSymbol(id="binance:spot:BTCUSDT", symbol="BTCUSDT", name="BTC", exchange="binance", market="spot", currency="USDT", timeframes=["1m"])

    async def resolve(key):
        return symbol

    async def fetch(info, timeframe, limit, since, until):
        requests.append((since, until))
        return [row for row in source if since <= row[0] <= until][:limit]

    market.resolve, market._fetch_crypto_rows = resolve, fetch
    try:
        first = await market.replay_bars(symbol.id, "1m", 5, start, start + 5 * step)
        second = await market.replay_bars(symbol.id, "1m", 5, start, start + 5 * step)
        assert [bar.time for bar in first.bars] == [row[0] for row in source]
        assert second == first
        assert requests == [(start + cached_count * step, start + 5 * step - 1)]
    finally:
        await market.close()
