"""Downloaded index candles remain readable after restart and vendor expiry."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.infra.db.database import DatabaseRuntime
from app.infra.db.schema import Kline
from app.infra.persistence.data_retention import archive_batch
from app.infra.persistence.market.kline_store import KlineStore
from app.services.chart_index_catalog import RETENTION
from app.services.chart_index_market import ChartIndexMarket, DAY


def stamp(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()*1000)


def candle(at):
    return [at,100,110,90,105,0]


class Offline:
    def history(self, *_):
        raise AssertionError('Expired history must be read from durable storage without a source request')


@pytest.mark.asyncio
@pytest.mark.parametrize('timeframe', ['1m','5m','15m','30m','1h','4h'])
async def test_downloaded_candles_survive_restart_expiry_and_calendar_gaps(installed_database_runtime, monkeypatch, timeframe):
    now = stamp('2026-11-27T12:00:00')
    first = stamp('2026-11-24')
    duration = {'1m':60_000,'5m':300_000,'15m':900_000,'30m':1_800_000,'1h':3_600_000,'4h':14_400_000}[timeframe]
    rows = [candle(first+i*(3_600_000 if timeframe=='4h' else duration)) for i in range(8 if timeframe=='4h' else 2)]
    calls = []
    class Native:
        def history(self, *query):
            calls.append(query)
            return rows
    monkeypatch.setattr('app.services.chart_index_market.time.time',lambda:now/1000)
    store = KlineStore(database_runtime=installed_database_runtime)
    service = ChartIndexMarket(None,store,Native())
    initial = await service.bars('US_DXY',timeframe,100,first,now)
    assert initial.bars and len(calls)==1
    if timeframe=='4h':
        assert len(store.get_before('index:US:DXY','1h',now,100))==8
        assert len(store.get_before('index:US:DXY','4h',now,100))==2
    await service.close()

    # Construct another engine and owner: no HTTP or process cache is reused.
    now += 800*DAY
    restarted_runtime = DatabaseRuntime(database_url=installed_database_runtime.database_url,
        source='restart-test',archive_root=installed_database_runtime.archive_root)
    restarted = ChartIndexMarket(None,KlineStore(database_runtime=restarted_runtime),Offline())
    query_end = stamp('2026-11-27T12:00:00')+60*DAY
    try:
        result = await restarted.bars('US_DXY',timeframe,100,None,query_end)
        assert [bar.model_dump() for bar in result.bars]==[bar.model_dump() for bar in initial.bars]
        assert result.source=='cache'
        assert result.symbol.metadata['cached_history_start']==first
        assert result.symbol.metadata['history_start']==first
        assert result.symbol.metadata['upstream_history_start']==now-RETENTION[timeframe]*DAY
        # Backward pages skip empty calendar windows, without repeats or loss.
        tail = await restarted.bars('US_DXY',timeframe,1,None,query_end)
        older = await restarted.bars('US_DXY',timeframe,1,None,tail.bars[0].time-1)
        assert [older.bars[0].time,tail.bars[0].time]==[bar.time for bar in initial.bars]
        forward = await restarted.bars('US_DXY',timeframe,100,first,initial.bars[-1].closeTime)
        assert [bar.time for bar in forward.bars]==[bar.time for bar in initial.bars]
    finally:
        await restarted.close()
        restarted_runtime.dispose()


@pytest.mark.asyncio
async def test_watch_quote_minute_reads_are_saved_but_unconfirmed_tail_is_not(installed_database_runtime,monkeypatch):
    now=stamp('2026-11-27T12:00:00')
    monkeypatch.setattr('app.services.chart_index_market.time.time',lambda:now/1000)
    minute_rows=[candle(now-20*60_000),candle(now-19*60_000),candle(now-5*60_000)]
    daily_rows=[candle(stamp('2026-11-25')),candle(stamp('2026-11-26'))]
    client=SimpleNamespace(history=lambda _symbol,interval,*_:daily_rows if interval=='1d' else minute_rows)
    store=KlineStore(database_runtime=installed_database_runtime)
    service=ChartIndexMarket(None,store,client)
    try:
        quote=await service.quote('US_DXY')
        assert quote.updated_at==minute_rows[-1][0]
        assert store.get_before('index:US:DXY','1m',now,10)==minute_rows[:2]
        assert store.get_before('index:US:DXY','5m',now,10)==[]
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_expired_archived_minutes_are_still_readable_after_reconstruction(installed_database_runtime,monkeypatch):
    now=stamp('2026-11-27T12:00:00')
    first=stamp('2024-01-02T10:00:00')
    monkeypatch.setattr('app.services.chart_index_market.time.time',lambda:now/1000)
    store=KlineStore(database_runtime=installed_database_runtime)
    rows=[candle(first+i*60_000) for i in range(3)]
    store.save('index:US:VIX','1m',rows)
    assert archive_batch(installed_database_runtime,cutoff_ts=first+DAY,batch_size=100)==3
    with installed_database_runtime.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Kline))==0
    service=ChartIndexMarket(None,KlineStore(database_runtime=installed_database_runtime),Offline())
    try:
        result=await service.bars('US_VIX','1m',10,None,first+90*DAY)
        assert [bar.time for bar in result.bars]==[row[0] for row in rows]
        assert result.source=='cache'
    finally:
        await service.close()
