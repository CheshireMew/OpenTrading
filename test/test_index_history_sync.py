from datetime import datetime, timezone

from app.domain.market.candles import candle_end_ms, current_candle_open_ms, utc_datetime
from app.domain.market.index_catalog import INDEX_CATALOG
from app.domain.market.index_fetch import IndexFetchResult
from app.domain.market.index_history_policy import live_start_ms
from app.services.market.index_history_sync import IndexHistorySync


class Store:
    def __init__(self):
        self.rows={}

    def get_range(self,symbol,period,start,end):
        return [row for stamp,row in sorted(self.rows.get((symbol,period),{}).items()) if start<=stamp<=end]

    def save(self,symbol,period,rows):
        self.rows.setdefault((symbol,period),{}).update({row[0]:row for row in rows})


def test_sync_excludes_cached_and_downloaded_back_series_and_preserves_real_ohlc():
    launch=live_start_ms('HK_HSTECH')
    storage=INDEX_CATALOG['HK_HSTECH'].storage_symbol
    real=[launch,100,110,90,105,0]
    close_only=[launch+86400000,106,106,106,106,0]
    repaired=[launch+86400000,105,111,99,106,0]
    store=Store()
    store.save(storage,'1d',[[launch-86400000,90,90,90,90,0],real,close_only])
    class Source:
        def fetch_history(self,instrument,start,end):
            assert int(start.timestamp()*1000)==launch
            return IndexFetchResult(data=[[launch-86400000,1,2,1,2,0],
                [launch,105,105,105,105,0],repaired],source='free')
    service=IndexHistorySync(store=store,sources=Source())
    end=datetime(2020,7,30,tzinfo=timezone.utc)
    result=service.sync('HK_HSTECH',timeframes=['1d','1w','1M'],end=end)
    assert result['periods']['1d']['rows']==2
    assert result['periods']['1d']['repaired']==1
    assert result['periods']['1d']['first'].startswith('2020-07-27')
    assert store.get_range(storage,'1d',launch,launch+86400000)==[real,repaired]
    repeated=service.sync('HK_HSTECH',timeframes=['1d'],end=end)
    assert repeated['periods']['1d']['added']==repeated['periods']['1d']['repaired']==0


def test_sync_saves_source_and_derived_periods_but_never_the_delayed_tail(monkeypatch):
    now=int(datetime(2026,11,28,12,tzinfo=timezone.utc).timestamp()*1000)
    monkeypatch.setattr('app.services.market.index_history_sync.time.time',lambda:now/1000)
    store=Store()
    calls=[]
    class Client:
        def history(self,symbol,period,start,end):
            calls.append((symbol,period,start,end))
            return [[start+i*3600000,100+i,110+i,90+i,105+i,0] for i in range(8)] + [[now-60000,1,2,1,2,0]]
    result=IndexHistorySync(store=store,client=Client()).sync('US_DXY',timeframes=['1h','4h'],
        start=utc_datetime(now-2*86400000))
    assert result['status']=='saved' and len(calls)==1 and calls[0][1]=='60m'
    assert result['periods']['1h']['rows']==8 and result['periods']['4h']['rows']==2
    for (_,period),rows in store.rows.items():
        assert all(candle_end_ms(stamp,period)<=now-900000 for stamp in rows)


def test_pre1970_monthly_boundaries_and_index_history_work_on_windows():
    launch=live_start_ms('US_SP500')
    assert utc_datetime(launch).date().isoformat()=='1957-03-04'
    month=current_candle_open_ms(launch,'1M')
    assert utc_datetime(month).date().isoformat()=='1957-03-01'
    assert utc_datetime(candle_end_ms(month,'1M')).date().isoformat()=='1957-04-01'
