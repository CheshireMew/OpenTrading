from datetime import datetime,timezone
from types import SimpleNamespace

import httpx
import pandas as pd

from app.domain.market.index_catalog import INDEX_CATALOG
from app.infra.market_data.index_source_catalog import get_index_source_binding
from app.infra.market_data.index_history_archives import NasdaqIndexHistoryProvider,DowJonesHistoryProvider


def test_official_nasdaq_history_keeps_real_closes_and_excludes_prelaunch_values(monkeypatch):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'aaData':[
            {'TimeStamp':'1985-01-30T00:00:00','Value':124,'PreviousClose':123},
            {'TimeStamp':'1985-01-31T00:00:00','Value':125,'High':0,'Low':0,'PreviousClose':124},
            {'TimeStamp':'1985-02-01T00:00:00','Value':124.63,'High':0,'Low':0,'PreviousClose':125}]})
    factory=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:factory(**kwargs,transport=httpx.MockTransport(respond)))
    result=NasdaqIndexHistoryProvider().fetch_history(INDEX_CATALOG['US_NASDAQ100'],get_index_source_binding('US_NASDAQ100'),
        datetime(1980,1,1,tzinfo=timezone.utc),datetime(1985,2,1,tzinfo=timezone.utc))
    assert len(calls)==1 and b'id=NDX' in calls[0].content and b'startDate=1985-01-31' in calls[0].content
    assert [row[1:5] for row in result.data]==[[125]*4,[124.63]*4] and result.is_close_only


def test_dow_archive_never_invents_open_from_its_partial_high_low_fields(monkeypatch):
    calls=[]
    factory=httpx.Client
    def respond(request):
        calls.append(request)
        return httpx.Response(200,content=b'recorded workbook')
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:factory(**kwargs,transport=httpx.MockTransport(respond)))
    def workbook(content,*,usecols):
        assert usecols==[0,1]
        return pd.DataFrame({'Date':['24-May-1896','27-May-1896','28-May-1896'],
            'Close':[40.94,40.58,40.2]})
    monkeypatch.setattr(pd,'read_excel',workbook)
    result=DowJonesHistoryProvider().fetch_history(INDEX_CATALOG['US_DOW'],get_index_source_binding('US_DOW'),
        datetime(1885,1,1,tzinfo=timezone.utc),datetime(1896,6,1,tzinfo=timezone.utc))
    assert len(calls)==1 and calls[0].url.path.endswith('DJIA1896.xls')
    assert [row[1:5] for row in result.data]==[[40.58]*4,[40.2]*4]
    assert result.is_close_only
