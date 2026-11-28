import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.chart_vix_market import ChartVixMarket, VIX_ID, vix_symbol, aggregate, DAY
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.infra.market_data.exchange import MarketDataError


def stamp(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def row(day, open=20, high=24, low=18, close=22):
    return [stamp(day), open, high, low, close, 0]


class DailyIndex:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    async def get_history_async(self, **query):
        self.calls.append(query)
        rows = [value for value in self.rows if query['start_date'] <= datetime.fromtimestamp(value[0]/1000, timezone.utc).date().isoformat() <= query['end_date']]
        return SimpleNamespace(data=[SimpleNamespace(as_row=lambda value=value: value) for value in rows], source='cboe')


def test_vix_symbol_retains_saved_identity_and_uses_index_points():
    info = vix_symbol()
    assert info.id == VIX_ID and info.symbol == 'US_VIX'
    assert info.metadata['display_symbol'] == 'VIX'
    assert info.metadata['name_zh'] == '恐慌指数'
    assert info.currency == 'PTS' and info.exchange == 'CBOE'
    assert info.timeframes == ['1m','5m','15m','30m','1h','4h','1d','1w','1M']
    market = ChartWorkspaceMarket(None, None)
    market._static_symbols()
    assert market.catalog[VIX_ID] == info


def test_four_hour_groups_match_workspace_utc_replay_boundaries_across_dst():
    for day in ('2026-03-06','2026-03-09'):
        start=stamp(day+'T08:00:00')
        rows=[[start+i*3600000,20+i,25+i,18+i,22+i,0] for i in range(8)]
        result=aggregate(rows,'4h')
        assert [bar[0] for bar in result]==[start,start+4*3600000]
        assert result[0][1:5]==[20,28,18,25]


@pytest.mark.asyncio
@pytest.mark.parametrize(('period', 'expected'), [
    ('1w', [[stamp('2024-01-29'),20,30,17,26,0], [stamp('2024-02-05'),27,29,25,28,0]]),
    ('1M', [[stamp('2024-01-01'),20,24,18,22,0], [stamp('2024-02-01'),23,30,17,28,0]]),
])
async def test_weekly_monthly_ohlc_respect_holidays_and_calendar(period, expected):
    index = DailyIndex([row('2024-01-31'), row('2024-02-01',23,30,17,26), row('2024-02-05',27,29,25,28)])
    market = ChartVixMarket(index)
    result = await market.bars(period, 20, None, stamp('2024-02-10'))
    assert [[bar.time,bar.open,bar.high,bar.low,bar.close,bar.volume] for bar in result.bars] == expected
    assert result.source == 'cboe'
    assert all(query['timeframe']=='1d' for query in index.calls)


@pytest.mark.asyncio
async def test_historical_partial_week_never_contains_later_days():
    market = ChartVixMarket(DailyIndex([row('2024-02-05'), row('2024-02-06',23,30,17,26), row('2024-02-07',100,200,90,150)]))
    result = await market.bars('1w', 1, None, stamp('2024-02-07')-1)
    assert len(result.bars)==1 and result.bars[0].close==26 and result.bars[0].high==30
    assert market.index.calls[0]['end_date']=='2024-02-06'


@pytest.mark.asyncio
async def test_intraday_pages_use_real_provider_and_obey_limits_and_retention(monkeypatch):
    now = stamp('2026-11-27T12:00:00')
    monkeypatch.setattr('app.services.chart_vix_market.time.time', lambda: now/1000)
    calls=[]

    class Client:
        def history(self, interval, start, end):
            calls.append((interval,start,end))
            return [[start+i*60_000,20,24,18,22,0] for i in range(1500)]

    market=ChartVixMarket(None, client=Client())
    result=await market.bars('1m',1000,now-2*DAY,now)
    assert len(result.bars)==1000 and result.source=='yahoo-finance'
    assert result.bars[0].time==now-2*DAY
    assert all(bar.closeTime==bar.time+60_000 for bar in result.bars)
    assert (await market.bars('1m',1000,stamp('2024-01-01'),stamp('2024-01-08'))).bars==[]
    assert len(calls)==1
    assert result.symbol.metadata['history_start']==now-29*DAY


@pytest.mark.asyncio
async def test_concurrent_intraday_reads_share_work_and_cancelled_visitor_does_not_cancel_it(monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()
    calls=[]

    async def run(operation):
        calls.append(True)
        started.set()
        await release.wait()
        return operation()

    monkeypatch.setattr('app.services.chart_index_market.run_external_io',run)
    client=SimpleNamespace(history=lambda *_: [row('2026-11-25')])
    market=ChartVixMarket(None,client=client)
    first=asyncio.create_task(market._intraday('1m',1,2))
    second=asyncio.create_task(market._intraday('1m',1,2))
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await second == [row('2026-11-25')]
    assert await market._intraday('1m',1,2) == [row('2026-11-25')]
    assert len(calls)==1
    await market.close()


@pytest.mark.asyncio
async def test_quote_uses_intraday_timestamp_and_previous_session_close(monkeypatch):
    now=stamp('2026-11-27T12:00:00')
    monkeypatch.setattr('app.services.chart_vix_market.time.time',lambda:now/1000)
    market=ChartVixMarket(None)

    async def history(interval,*_):
        return [row('2026-11-25',close=20),row('2026-11-27',close=23)] if interval=='1d' else [row('2026-11-27T11:40:00',close=24)]

    market._intraday=history
    quote=await market.quote()
    assert quote.price==24 and quote.change==4 and quote.change_pct==pytest.approx(20)
    assert quote.updated_at==stamp('2026-11-27T11:40:00')
    assert 'Yahoo' in quote.basis


@pytest.mark.asyncio
async def test_current_day_forward_poll_does_not_request_an_inverted_daily_history_range(monkeypatch):
    now=stamp('2026-11-27T16:00:00')
    monkeypatch.setattr('app.services.chart_vix_market.time.time',lambda:now/1000)
    index=DailyIndex([])
    market=ChartVixMarket(index,client=SimpleNamespace(history=lambda *_:[row('2026-11-27',high=26,close=25)]))
    result=await market.bars('1d',1000,stamp('2026-11-27'),now)
    assert len(result.bars)==1 and result.bars[0].close==25 and not result.bars[0].closed
    assert index.calls==[]
    await market.close()


def test_yahoo_adapter_rejects_an_etf_identity(monkeypatch):
    import httpx
    from app.infra.market_data.vix import VixIntradayClient
    payload={'chart':{'result':[{'meta':{'symbol':'VIXY','instrumentType':'ETF'}}]}}
    client=VixIntradayClient(httpx.MockTransport(lambda _:httpx.Response(200,json=payload)))
    try:
        with pytest.raises(MarketDataError, match='不是 VIX'):
            client.history('1m',stamp('2026-11-25'),stamp('2026-11-26'))
    finally:
        client.close()


def test_native_yahoo_feed_folds_live_sample_into_its_candle_and_excludes_future_observations():
    import httpx
    from app.infra.market_data.vix import VixIntradayClient
    first = stamp('2026-11-25T14:00:00')
    payload={'chart':{'result':[{'meta':{'symbol':'^VIX','instrumentType':'INDEX','exchangeTimezoneName':'America/Chicago'},
        'timestamp':[first//1000, first//1000+67, first//1000+3600], 'indicators':{'quote':[
        {'open':[20,23,100], 'high':[22,23,200], 'low':[19,23,99], 'close':[21,23,150]}]}}]}}
    client=VixIntradayClient(httpx.MockTransport(lambda _:httpx.Response(200,json=payload)))
    try:
        assert client.history('5m', first, first+300_000)==[[first,20,23,19,23,0]]
    finally:
        client.close()


@pytest.mark.asyncio
async def test_cache_has_a_bar_budget_and_failed_fetches_are_retryable():
    calls=[]
    def history(*args):
        calls.append(args)
        if len(calls)==1:
            raise MarketDataError('temporary failure')
        return [row('2026-11-25') for _ in range(10_000)]
    market=ChartVixMarket(None,client=SimpleNamespace(history=history))
    with pytest.raises(MarketDataError):
        await market._intraday('1m',1,2)
    await market._intraday('1m',1,2)
    for number in range(3,8):
        await market._intraday('1m',number,number+1)
    assert sum(len(value[1]) for value in market._cache.values())<=32_000
    assert len(market._tasks)==0
    await market.close()


def test_native_thirty_minutes_are_aggregated_from_fifteen_and_connections_close():
    import httpx
    from app.infra.market_data.vix import VixIntradayClient
    first=stamp('2026-11-25T14:00:00')
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json={'chart':{'result':[{
            'meta':{'symbol':'^VIX','instrumentType':'INDEX','dataGranularity':'15m'},
            'timestamp':[first//1000,first//1000+900],
            'indicators':{'quote':[{'open':[20,21],'high':[22,25],'low':[19,18],'close':[21,24]}]}}]}})
    client=VixIntradayClient(httpx.MockTransport(respond))
    assert client.history('30m',first,first+1800000)==[[first,20,25,18,24,0]]
    assert requests[0].url.params['interval']=='15m'
    connection=client._client
    client.close()
    assert connection.is_closed


def test_yahoo_failure_tries_second_host_and_never_becomes_an_empty_page():
    import httpx
    from app.infra.market_data.vix import VixIntradayClient
    hosts=[]
    def respond(request):
        hosts.append(request.url.host)
        return httpx.Response(503,text='unavailable')
    client=VixIntradayClient(httpx.MockTransport(respond))
    try:
        with pytest.raises(MarketDataError,match='暂不可用'):
            client.history('1m',stamp('2026-11-25'),stamp('2026-11-26'))
        assert hosts==['query1.finance.yahoo.com','query2.finance.yahoo.com']
    finally:
        client.close()


def test_http_vix_chart_and_replay_keep_units_periods_and_closed_bar_cutoff(monkeypatch):
    from contextlib import asynccontextmanager
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.routers.chart_workspace import services
    now=stamp('2026-11-27T12:00:00')
    monkeypatch.setattr('app.services.chart_vix_market.time.time',lambda:now/1000)
    market=ChartWorkspaceMarket(None,DailyIndex([row('2026-11-25'),row('2026-11-26')]))
    async def resolve(_): return vix_symbol()
    market.resolve=resolve
    market.indices.client=SimpleNamespace(history=lambda *_:[row('2026-11-27T10:00:00'),row('2026-11-27T11:00:00')])
    app=create_app('api')
    @asynccontextmanager
    async def lifespan(_):
        yield
        await market.close()
    app.router.lifespan_context=lifespan
    app.dependency_overrides[services]=lambda:SimpleNamespace(market=market)
    with TestClient(app) as client:
        response=client.get('/api/v1/chart-workspace/bars',params={'symbol':VIX_ID,'timeframe':'1h','limit':10,'end':now})
        assert response.status_code==200
        payload=response.json()
        assert payload['symbol']['currency']=='PTS' and payload['symbol']['metadata']['quote_unit']=='points'
        assert len(payload['bars'])==2
        replay=client.get('/api/v1/chart-workspace/replay/bars',params={'symbol':VIX_ID,'timeframe':'1h','limit':10,'end':stamp('2026-11-27T11:30:00')})
        assert replay.status_code==200
        assert [bar['time'] for bar in replay.json()['bars']]==[stamp('2026-11-27T10:00:00')]
