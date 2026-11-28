from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.domain.market.index_catalog import INDEX_CATALOG
from app.infra.market_data.index_chart import IndexChartClient
from app.infra.market_data.index_source_catalog import get_index_source_binding
from app.services.chart_index_catalog import PERIODS
from app.services.chart_index_market import ChartIndexMarket, aggregate
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.infra.market_data.index_history_tencent import TencentIndexHistoryProvider


def stamp(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def test_all_existing_indices_have_localized_point_based_identities_and_real_index_feeds():
    market = ChartWorkspaceMarket(None, None)
    market._static_symbols()
    assert len(INDEX_CATALOG) == 19
    for instrument in INDEX_CATALOG.values():
        info = market.catalog[f'index:index:{instrument.symbol}']
        assert info.timeframes == PERIODS and info.currency == 'PTS'
        assert info.metadata['quote_unit'] == 'points' and info.metadata['name_zh'] in info.aliases
        assert info.metadata['icon_url'].endswith(info.metadata['display_symbol'].lower()+'.svg')
        assert info.metadata['has_volume'] is False
        assert instrument.pricing_currency in {None, 'USD', 'CNY', 'HKD'}
    assert get_index_source_binding('HK_HSTECH').yfinance_symbol == 'HSTECH.HK'


@pytest.mark.parametrize('symbol', list(INDEX_CATALOG))
def test_native_hourly_feed_preserves_the_verified_vendor_identity_and_candle_offset(symbol):
    ticker = get_index_source_binding(symbol).yfinance_symbol
    half_hour = symbol not in {'US_VIX', 'US_DXY'}
    start = stamp('2026-11-25T14:00:00') + (1_800_000 if half_hour else 0)
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'chart': {'result': [{
            'meta': {'symbol': ticker, 'instrumentType': 'INDEX', 'dataGranularity': '60m'},
            'timestamp': [start//1000, start//1000+1500],
            'indicators': {'quote': [{'open': [100, 103], 'high': [105, 103], 'low': [99, 103], 'close': [102, 103]}]},
        }]}})
    client = IndexChartClient(httpx.MockTransport(respond))
    try:
        assert client.history(symbol, '60m', start, start+3_600_000) == [[start, 100, 105, 99, 103, 0]]
        assert requests[0].url.path.endswith('/'+ticker)
    finally:
        client.close()


def test_four_hour_aggregation_does_not_move_hourly_observations_into_an_earlier_window():
    start = stamp('2026-11-25T12:30:00')
    rows = [[start+i*3_600_000, 100+i, 110+i, 90+i, 105+i, 0] for i in range(8)]
    result = aggregate(rows, '4h', 1_800_000)
    assert result == [[start,100,113,90,108,0], [start+4*3_600_000,104,117,94,112,0]]


@pytest.mark.asyncio
async def test_asian_daily_archives_supply_week_and_month_without_currency_or_etf_substitution():
    calls = []
    class Daily:
        async def get_history_async(self, **query):
            calls.append(query)
            rows = [[stamp('2025-01-31'),100,110,90,105,500], [stamp('2025-02-01'),106,120,99,115,400]]
            return SimpleNamespace(data=[SimpleNamespace(as_row=lambda row=row: row) for row in rows],
                source='eastmoney', native_currency='CNY', is_close_only=False)
    class Native:
        def history(self, *_): raise AssertionError('Historical Chinese daily data must use the long archive')
    market = ChartIndexMarket(Daily(), client=Native())
    try:
        result = await market.bars('CN_CSI_A500', '1M', 10, None, stamp('2025-02-05'))
        assert result.symbol.currency == 'PTS' and not result.symbol.close_only
        assert result.source == 'eastmoney' and len(result.bars) == 2
        assert [bar.close for bar in result.bars] == [105,115]
        assert all(call['symbol']=='CN_CSI_A500' and call['timeframe']=='1d' for call in calls)
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_old_close_only_pages_do_not_change_the_index_capability_or_invent_period_ohlc():
    old = [stamp('2020-07-28'),100,100,100,100,0]
    recent = [stamp('2020-08-03'),101,110,98,108,0]
    class Daily:
        async def get_history_async(self, **query):
            rows = [row for row in [old,recent] if query['start_date'] <= datetime.fromtimestamp(row[0]/1000,timezone.utc).date().isoformat() <= query['end_date']]
            return SimpleNamespace(data=[SimpleNamespace(as_row=lambda row=row:row) for row in rows],
                source='cache',is_close_only=rows==[old])
    market=ChartIndexMarket(Daily(),client=SimpleNamespace(history=lambda *_:[]))
    try:
        page=await market.bars('HK_HSTECH','1d',100,None,stamp('2020-07-30'))
        assert page.symbol.close_only is False
        assert page.bars[0].closeOnly is True
        mixed=await market.bars('HK_HSTECH','1d',100,None,stamp('2020-08-05'))
        assert mixed.symbol.close_only is False
        assert [bar.closeOnly for bar in mixed.bars]==[True,False]
        assert mixed.bars[-1].high==110 and mixed.bars[-1].low==98
        month=await market.bars('HK_HSTECH','1M',100,None,stamp('2020-08-05'))
        assert month.symbol.close_only is False
        assert month.bars[0].closeOnly is True
        assert month.bars[0].open==month.bars[0].high==month.bars[0].low==month.bars[0].close==100
        assert month.bars[1].high==110
        week=await market.bars('HK_HSTECH','1w',100,None,stamp('2020-08-05'))
        assert [bar.closeOnly for bar in week.bars]==[True,False]
        assert week.bars[-1].high==110
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_dollar_index_daily_pages_reuse_the_persistent_daily_service(monkeypatch):
    now = stamp('2026-11-27T12:00:00')
    monkeypatch.setattr('app.services.chart_index_market.time.time', lambda: now/1000)
    calls = []
    class Native:
        def history(self, *query):
            calls.append(query)
            return [[stamp('2026-11-25'),100,102,99,101,0], [stamp('2026-11-26'),101,103,100,102,0]]
    class Daily:
        async def get_history_async(self, **_):
            rows=Native().history('US_DXY','1d')
            return SimpleNamespace(data=[SimpleNamespace(as_row=lambda row=row: row) for row in rows],source='cache')
    saved = []
    store = SimpleNamespace(save=lambda *args: saved.append(args))
    market = ChartIndexMarket(Daily(), store=store, client=SimpleNamespace(history=lambda *_:[]))
    try:
        result = await market.bars('US_DXY', '1w', 10, None, now)
        assert result.source == 'cache' and result.symbol.currency == 'PTS'
        assert len(result.bars)==1 and result.bars[0].high == 103 and result.bars[0].low == 99
        assert calls[0][:2] == ('US_DXY','1d')
        assert saved == []  # The daily service owns persistence.
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_index_backward_daily_pages_do_not_skip_the_previous_session():
    days=['2024-02-05','2024-02-06','2024-02-07','2024-02-08']
    rows=[[stamp(day),100+i,110+i,90+i,105+i,0] for i,day in enumerate(days)]
    class Daily:
        async def get_history_async(self,**query):
            selected=[row for row in rows if query['start_date']<=datetime.fromtimestamp(row[0]/1000,timezone.utc).date().isoformat()<=query['end_date']]
            return SimpleNamespace(data=[SimpleNamespace(as_row=lambda row=row:row) for row in selected],source='cache')
    market=ChartIndexMarket(Daily(),client=SimpleNamespace(history=lambda *_:[]))
    try:
        end=stamp('2024-02-09')
        actual=[]
        while True:
            page=await market.bars('HK_HSTECH','1d',1,None,end)
            if not page.bars:
                break
            actual.extend(bar.time for bar in page.bars)
            end=page.bars[0].time-1
        assert actual==[row[0] for row in reversed(rows)]
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_index_caches_do_not_mix_symbols_and_share_one_global_bar_budget():
    calls = []
    class Native:
        def history(self, symbol, *_):
            calls.append(symbol)
            value = 100 if symbol == 'US_DXY' else 5000
            return [[stamp('2026-11-25'),value,value,value,value,0] for _ in range(10_000)]
    market = ChartIndexMarket(None, client=Native())
    try:
        assert (await market._history('US_DXY','1m',1,2))[0][4] == 100
        assert (await market._history('US_SP500','1m',1,2))[0][4] == 5000
        await market._history('US_DXY','1m',1,2)
        for number in range(4):
            await market._history('HK_HSI','1m',number,10)
        assert calls.count('US_DXY') == 1
        assert sum(len(value[1]) for value in market._cache.values()) <= 32_000
    finally:
        await market.close()


def test_tencent_daily_history_pages_backwards_and_keeps_older_observations(monkeypatch):
    from datetime import timedelta
    first = datetime(2020,1,1,tzinfo=timezone.utc)
    days = [(first+timedelta(days=i)).strftime('%Y-%m-%d') for i in range(670)]
    calls = []
    def respond(request):
        calls.append(request.url.params['param'])
        end = request.url.params['param'].split(',')[3]
        available = [day for day in days if day <= end]
        return httpx.Response(200,json={'code':0,'data':{'sh000300':{
            'qt':{'sh000300':['1','沪深300','000300']},
            'day':[[day,'100','103','105','99','999'] for day in available[-640:]],
        }}})
    factory = httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:factory(**kwargs,transport=httpx.MockTransport(respond)))
    result=TencentIndexHistoryProvider().fetch_history(INDEX_CATALOG['CN_CSI300'], get_index_source_binding('CN_CSI300'), first, first+timedelta(days=669))
    assert len(calls)==2 and len(result.data)==670 and result.source=='tencent'
    assert result.data[0]==[int(first.timestamp()*1000),100,105,99,103,0]
    assert calls[1].split(',')[3]==days[29]


def test_tencent_does_not_require_or_return_prelaunch_back_series(monkeypatch):
    payload={'code':0,'data':{'sh000510':{'qt':{'sh000510':['1','中证A500','000510']},
        'day':[['2024-09-23','100','103','105','99','999']]}}}
    factory=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:factory(**kwargs,transport=httpx.MockTransport(lambda _:httpx.Response(200,json=payload))))
    result=TencentIndexHistoryProvider().fetch_history(INDEX_CATALOG['CN_CSI_A500'],get_index_source_binding('CN_CSI_A500'),
        datetime(2004,1,1,tzinfo=timezone.utc),datetime(2024,9,23,tzinfo=timezone.utc))
    assert result.data==[[stamp('2024-09-23'),100,105,99,103,0]]
