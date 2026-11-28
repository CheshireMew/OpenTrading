from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

import pandas as pd
import pytest
from datetime import date
from app.domain.market.session_history import daily_session_prices, SessionHistoryCoverage

from app.domain.market.constants import KLINE_SYMBOL_MAX_LENGTH
from app.domain.market.index_catalog import INDEX_CATALOG, get_index_instrument, get_supported_index_symbols
from app.domain.market.index_fetch import IndexFetchResult
from app.services.market.index_data_service import IndexDataService
from app.services.market.index_history_sources import IndexHistorySources
from app.infra.market_data.index_source_catalog import get_index_source_binding


def ohlcv_row(point) -> list[float]:
    return [
        point.timestamp,
        point.open,
        point.high,
        point.low,
        point.close,
        point.volume,
    ]


class FakeKlineStore:
    def __init__(self, cached: list[list[float]] | None = None) -> None:
        self.cached = list(cached or [])
        self.saved: list[tuple[str, str, list[list[float]]]] = []

    def get_range(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> list[list[float]]:
        return [
            row
            for row in self.cached
            if start_ts <= row[0] <= end_ts
        ]

    def save(self, symbol: str, timeframe: str, klines: list[list[float]]) -> None:
        self.saved.append((symbol, timeframe, klines))


class FakeIndexHistorySources:
    def __init__(self, rows_by_window: dict[tuple[str, str], list[list[float]]]) -> None:
        self.rows_by_window = rows_by_window
        self.calls: list[tuple[str, str]] = []

    def fetch_history(self, instrument, start_dt, end_dt):
        key = (start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))
        self.calls.append(key)
        return types.SimpleNamespace(
            data=self.rows_by_window.get(key, []),
            source="fake_source",
            is_close_only=False,
        )

    def fetch_pricing_history(self, instrument, start_dt, end_dt):
        raise AssertionError("pricing history should not be used in this test")

    def fetch_usd_fx_rates(self, currency, start_dt, end_dt):
        return {}

    def has_pricing_source(self, instrument):
        return True


class FakeResponse:
    def __init__(self, payload=None, text: str = "") -> None:
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def test_missing_trading_day_is_not_a_holiday():
    def row(day):
        return [int(datetime(2024, 1, day, tzinfo=timezone.utc).timestamp() * 1000), 100, 100, 100, 100, 10]
    source = FakeIndexHistorySources({})
    result = IndexDataService(FakeKlineStore([row(2), row(4), row(5)]), source).get_history(
        symbol="US_SP500", timeframe="1d", start_date="2024-01-01", end_date="2024-01-07")
    assert result.coverage.complete is False
    assert result.coverage.missing_sessions == ["2024-01-03"]
    assert result.coverage.non_trading_dates == ["2024-01-01", "2024-01-06", "2024-01-07"]
    assert source.calls == [("2024-01-03", "2024-01-03")]


def test_verified_weekend_can_be_filled_but_missing_session_cannot():
    coverage = SessionHistoryCoverage(complete=True, calendar="XNYS", start_date="2024-01-05", end_date="2024-01-08",
        expected_sessions=["2024-01-05", "2024-01-08"], non_trading_dates=["2024-01-06", "2024-01-07"], error=None)
    result = daily_session_prices({"2024-01-05": 100, "2024-01-08": 105}, coverage, date(2024, 1, 5), date(2024, 1, 8))
    assert list(result.values()) == [100, 100, 100, 105]
    with pytest.raises(ValueError, match="2024-01-08"):
        daily_session_prices({"2024-01-05": 100}, coverage, date(2024, 1, 5), date(2024, 1, 8))


def test_pre1970_holidays_and_confirmed_hk_weather_closures_are_not_missing_candles():
    from app.infra.market_calendar import session_dates
    _,sessions,holidays=session_dates('US',date(1957,7,3),date(1957,7,5))
    assert sessions==['1957-07-03','1957-07-05'] and holidays==['1957-07-04']
    _,sessions,holidays=session_dates('HK',date(2023,9,1),date(2023,9,8))
    assert '2023-09-01' not in sessions and '2023-09-08' not in sessions
    assert '2023-09-01' in holidays and '2023-09-08' in holidays


def test_holiday_only_calendar_range_is_complete_without_fetching():
    source = FakeIndexHistorySources({})
    result = IndexDataService(FakeKlineStore(), source).get_history(
        symbol="CN_CSI300", timeframe="1d", start_date="2026-10-01", end_date="2026-10-07")
    assert result.coverage.complete and not result.coverage.expected_sessions
    assert len(result.coverage.non_trading_dates) == 7
    assert source.calls == []


def test_benchmark_currency_history_remains_available_without_fred(monkeypatch):
    requests = []

    def fetch_rates(url, **kwargs):
        requests.append((url, kwargs["params"]))
        return FakeResponse(payload={"rates": {
            "2024-01-02": {"USD": 0.128},
            "2024-01-03": {"USD": 0.129},
            "2024-01-04": {},
        }})

    monkeypatch.setattr("app.infra.market_data.index_history_fx.requests.get", fetch_rates)
    rates = IndexHistorySources().fetch_usd_fx_rates("HKD", datetime(2024, 1, 1), datetime(2024, 1, 5))
    assert rates == {"2024-01-02": 0.128, "2024-01-03": 0.129}
    assert requests == [("https://api.frankfurter.app/2024-01-01..2024-01-05", {"from": "HKD", "to": "USD"})]


def test_index_catalog_contains_core_us_cn_hk_indexes():
    assert get_supported_index_symbols() == [
        "US_SP500",
        "US_NASDAQ_COMP",
        "US_NASDAQ100",
        "US_DOW",
        "US_RUSSELL2000",
        "US_VIX",
        "US_DXY",
        "CN_CSI300",
        "CN_CSI_A500",
        "CN_SSE50",
        "CN_CSI500",
        "CN_CSI1000",
        "CN_SSE_COMP",
        "CN_SZSE_COMPONENT",
        "CN_CHINEXT",
        "CN_STAR50",
        "HK_HSI",
        "HK_HSTECH",
        "HK_HSCEI",
    ]

    assert get_index_source_binding("CN_CSI300").eastmoney_secid == "1.000300"
    assert get_index_source_binding("CN_CSI300").sohu_code == "zs_000300"
    assert get_index_source_binding("CN_CSI300").baostock_code == "sh.000300"
    assert get_index_source_binding("CN_CSI_A500").sina_cn_symbol == "sh000510"
    assert get_index_instrument("CN_CSI_A500").pricing_symbol == "sh560610"
    assert "恒生" in get_index_instrument("HK_HSI").aliases
    assert get_index_source_binding("HK_HSI").sina_hk_symbol == "HSI"
    assert get_index_instrument("HK_HSI").pricing_symbol == "02800"
    assert "标普500" in get_index_instrument("US_SP500").aliases
    assert get_index_source_binding("US_SP500").eastmoney_secid == "100.SPX"
    assert get_index_source_binding("US_NASDAQ100").sina_us_symbol == ".NDX"
    assert get_index_instrument("US_NASDAQ100").pricing_symbol == "QQQ"
    assert get_index_source_binding("HK_HSTECH").eastmoney_secid == "124.HSTECH"


def test_index_storage_symbols_fit_kline_cache_contract():
    storage_symbols: list[str] = []
    for instrument in INDEX_CATALOG.values():
        storage_symbols.append(instrument.storage_symbol)
        if instrument.pricing_storage_symbol:
            storage_symbols.append(instrument.pricing_storage_symbol)

    assert max(len(symbol) for symbol in storage_symbols) <= KLINE_SYMBOL_MAX_LENGTH


@pytest.fixture
def legacy_daily_sources():
    # Isolate normalization from unrelated live sources, including fallbacks.
    from app.infra.market_data.index_history_http import EastmoneyIndexHistoryProvider
    def create(name):
        sources=IndexHistorySources()
        sources.providers=({'eastmoney':EastmoneyIndexHistoryProvider().fetch_history,
            'sina_hk':sources.sina.fetch_hk_history,'sina_cn':sources.sina.fetch_cn_history,
            'sina_us':sources.sina.fetch_us_history}[name],)
        return sources
    return create


def test_eastmoney_history_is_normalized_and_cached(monkeypatch, legacy_daily_sources):
    service = IndexDataService(kline_store=FakeKlineStore(),history_sources=legacy_daily_sources('eastmoney'))

    def fake_get(*args, **kwargs):
        return FakeResponse(
            payload={
                "data": {
                    "klines": [
                        "2024-01-02,1.0,2.0,3.0,0.5,100,1000",
                        "2024-01-03,2.0,2.5,2.8,1.8,120,1200",
                    ]
                }
            }
        )

    monkeypatch.setattr("app.infra.market_data.index_history_http.requests.get", fake_get)

    result = service.get_history(
        symbol="CN_CSI300",
        timeframe="1d",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )

    assert result.source == "eastmoney"
    assert result.is_close_only is False
    assert result.count == 2
    assert ohlcv_row(result.data[0]) == [
        int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
        1.0,
        3.0,
        0.5,
        2.0,
        100.0,
    ]
    assert service.kline_store.saved[0][0] == "index:CN:CSI300"


def test_sina_hk_history_is_normalized_and_cached(monkeypatch, legacy_daily_sources):
    service = IndexDataService(kline_store=FakeKlineStore(),history_sources=legacy_daily_sources('sina_hk'))

    fake_akshare = types.SimpleNamespace(
        stock_hk_index_daily_sina=lambda symbol: pd.DataFrame([
            {"date": "2024-01-02", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000},
            {"date": "2024-01-03", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 1100},
        ])
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    result = service.get_history(
        symbol="HK_HSI",
        timeframe="1d",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )

    assert result.source == "sina_hk"
    assert result.is_close_only is False
    assert result.count == 2
    assert ohlcv_row(result.data[0]) == [
        int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
        10.0,
        12.0,
        9.0,
        11.0,
        1000.0,
    ]
    assert service.kline_store.saved[0][0] == "index:HK:HSI"


def test_sina_cn_history_is_normalized_and_cached(monkeypatch, legacy_daily_sources):
    service = IndexDataService(kline_store=FakeKlineStore(),history_sources=legacy_daily_sources('sina_cn'))

    fake_akshare = types.SimpleNamespace(
        stock_zh_index_daily=lambda symbol: pd.DataFrame([
            {"date": "2025-01-02", "open": 20, "high": 23, "low": 19, "close": 22, "volume": 2000},
            {"date": "2025-01-03", "open": 22, "high": 24, "low": 21, "close": 23, "volume": 2100},
        ])
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    result = service.get_history(
        symbol="CN_CSI_A500",
        timeframe="1d",
        start_date="2025-01-01",
        end_date="2025-01-10",
    )

    assert result.source == "sina_cn"
    assert result.is_close_only is False
    assert result.count == 2
    assert ohlcv_row(result.data[0]) == [
        int(datetime(2025, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
        20.0,
        23.0,
        19.0,
        22.0,
        2000.0,
    ]
    assert service.kline_store.saved[0][0] == "index:CN:CSI_A500"


def test_sina_us_history_is_normalized_and_cached(monkeypatch, legacy_daily_sources):
    service = IndexDataService(kline_store=FakeKlineStore(),history_sources=legacy_daily_sources('sina_us'))

    fake_akshare = types.SimpleNamespace(
        index_us_stock_sina=lambda symbol: pd.DataFrame([
            {"date": "2024-01-02", "open": 30, "high": 33, "low": 29, "close": 32, "volume": 3000},
            {"date": "2024-01-03", "open": 32, "high": 34, "low": 31, "close": 33, "volume": 3100},
        ])
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    result = service.get_history(
        symbol="US_NASDAQ100",
        timeframe="1d",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )

    assert result.source == "sina_us"
    assert result.is_close_only is False
    assert result.count == 2
    assert ohlcv_row(result.data[0]) == [
        int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
        30.0,
        33.0,
        29.0,
        32.0,
        3000.0,
    ]
    assert service.kline_store.saved[0][0] == "index:US:NASDAQ100"


def test_pricing_history_uses_proxy_etf_source(monkeypatch):
    service = IndexDataService(kline_store=FakeKlineStore())

    fake_akshare = types.SimpleNamespace(
        stock_hk_daily=lambda symbol, adjust='': pd.DataFrame([
            {"date": "2024-01-02", "open": 20, "high": 21, "low": 19, "close": 20.5, "volume": 2000},
            {"date": "2024-01-03", "open": 20.5, "high": 21.5, "low": 20.1, "close": 21.0, "volume": 2100},
        ])
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)
    monkeypatch.setattr(service.history_sources, "fetch_usd_fx_rates", lambda *args, **kwargs: {
        "2024-01-02": 0.128,
        "2024-01-03": 0.129,
    })

    result = service.get_pricing_history(
        symbol="HK_HSI",
        timeframe="1d",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )

    assert result.price_basis == "proxy_etf"
    assert result.source == "sina_hk_etf:usd"
    assert result.pricing_symbol == "02800"
    assert result.pricing_currency == "USD"
    assert result.native_currency == "HKD"
    assert result.count == 2
    assert ohlcv_row(result.data[0]) == [
        int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
        2.56,
        2.688,
        2.432,
        2.624,
        2000.0,
    ]
    assert service.kline_store.saved[0][0] == "proxy:HK:HSI:02800"


def test_close_only_history_is_normalized_and_cached(monkeypatch):
    close_only_row = [
        int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
        13.2,
        13.2,
        13.2,
        13.2,
        0.0,
    ]
    history_sources = FakeIndexHistorySources({
        ("2024-01-02", "2024-01-10"): [close_only_row],
    })
    service = IndexDataService(kline_store=FakeKlineStore(), history_sources=history_sources)

    def fake_fetch_history(instrument, start_dt, end_dt):
        key = (start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))
        history_sources.calls.append(key)
        return types.SimpleNamespace(
            data=history_sources.rows_by_window.get(key, []),
            source="close_only_fixture",
            is_close_only=True,
        )

    history_sources.fetch_history = fake_fetch_history

    result = service.get_history(
        symbol="US_VIX",
        timeframe="1d",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )

    assert result.source == "close_only_fixture"
    assert result.is_close_only is True
    assert [ohlcv_row(item) for item in result.data] == [close_only_row]
    assert service.kline_store.saved[0][0] == "index:US:VIX"


def test_cached_close_only_index_history_keeps_close_only_flag():
    cached_rows = [
        [
            int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
            13.2,
            13.2,
            13.2,
            13.2,
            0.0,
        ]
    ]
    service = IndexDataService(kline_store=FakeKlineStore(cached=cached_rows))

    result = service.get_history(
        symbol="US_VIX",
        timeframe="1d",
        start_date="2024-01-02",
        end_date="2024-01-02",
    )

    assert result.source == "cache"
    assert result.is_close_only is True
    assert [ohlcv_row(item) for item in result.data] == cached_rows


def test_cached_history_is_used_before_upstream_fetch(monkeypatch):
    cached_rows = [
        [
            int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000),
            1.0,
            2.0,
            0.5,
            1.5,
            100.0,
        ],
        [
            int(datetime(2024, 1, 3, tzinfo=timezone.utc).timestamp() * 1000),
            1.5,
            2.2,
            1.2,
            2.0,
            120.0,
        ],
    ]
    service = IndexDataService(kline_store=FakeKlineStore(cached=cached_rows))

    def fail_fetch(*args, **kwargs):
        raise AssertionError("should not fetch upstream when cache already covers the range")

    monkeypatch.setattr(service.history_sources, "fetch_history", fail_fetch)

    result = service.get_history(
        symbol="CN_CSI300",
        timeframe="1d",
        start_date="2024-01-02",
        end_date="2024-01-03",
    )

    assert result.source == "cache"
    assert result.is_close_only is False
    assert result.count == 2
    assert [ohlcv_row(item) for item in result.data] == cached_rows


def test_index_history_repairs_middle_gap():
    base_ts = int(datetime(2024, 1, 2, tzinfo=timezone.utc).timestamp() * 1000)
    one_day_ms = 24 * 60 * 60 * 1000
    cached_rows = [
        [base_ts, 1.0, 2.0, 0.5, 1.5, 100.0],
        [base_ts + (2 * one_day_ms), 2.0, 3.0, 1.5, 2.5, 110.0],
    ]
    missing_row = [base_ts + one_day_ms, 1.6, 2.4, 1.2, 2.1, 105.0]
    history_sources = FakeIndexHistorySources({
        ("2024-01-03", "2024-01-03"): [missing_row],
    })
    service = IndexDataService(
        kline_store=FakeKlineStore(cached=cached_rows),
        history_sources=history_sources,
    )

    result = service.get_history(
        symbol="CN_CSI300",
        timeframe="1d",
        start_date="2024-01-02",
        end_date="2024-01-04",
    )

    assert history_sources.calls == [("2024-01-03", "2024-01-03")]
    assert [row.timestamp for row in result.data] == [
        cached_rows[0][0],
        missing_row[0],
        cached_rows[1][0],
    ]


def test_gap_repair_never_downgrades_cached_full_ohlc_to_a_close_only_row():
    stamp=int(datetime(2024,1,2,tzinfo=timezone.utc).timestamp()*1000)
    full=[stamp+86400000,100,110,90,105,0]
    sources=FakeIndexHistorySources({('2024-01-02','2024-01-04'):[
        [stamp,10,12,9,11,0],[stamp+86400000,105,105,105,105,0],
        [stamp+2*86400000,11,13,10,12,0]]})
    result=IndexDataService(FakeKlineStore([full]),sources).get_history(symbol='US_SP500',
        timeframe='1d',start_date='2024-01-02',end_date='2024-01-04')
    assert result.data[1].as_row()==full


def test_verified_weekends_do_not_trigger_redundant_hydration():
    def row(day):
        return [int(datetime(2024, 1, day, tzinfo=timezone.utc).timestamp() * 1000), 10, 11, 9, 10, 0]

    sources = FakeIndexHistorySources({("2024-01-06", "2024-01-14"): []})
    service = IndexDataService(kline_store=FakeKlineStore([row(5), row(8), row(9), row(10), row(11), row(12), row(15)]), history_sources=sources)
    result = service.get_history(symbol="HK_HSTECH", timeframe="1d", start_date="2024-01-05", end_date="2024-01-15")
    assert sources.calls == []
    assert result.coverage.complete
    assert result.count == 7


def test_open_ended_index_history_excludes_the_unclosed_daily_bar():
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day = today.strftime("%Y-%m-%d")
    stamp = int(today.timestamp() * 1000)
    updated = [stamp, 10, 15, 9, 14, 1]
    sources = FakeIndexHistorySources({(day, day): [updated]})
    service = IndexDataService(kline_store=FakeKlineStore([[stamp, 10, 11, 9, 10, 0]]), history_sources=sources)
    result = service.get_history(symbol="HK_HSTECH", timeframe="1d", start_date=day)
    assert sources.calls == []
    assert result.data == []


def test_hstech_uses_published_history_and_keeps_sina_fallback(monkeypatch):
    from app.domain.market.index_fetch import IndexFetchResult
    from app.infra.market_data.index_history_http import EastmoneyIndexHistoryProvider
    from app.infra.market_data.index_history_sina import SinaIndexHistoryProvider
    from app.infra.market_data.index_history_tencent import TencentIndexHistoryProvider

    calls = []
    def tencent(self, *args):
        calls.append("tencent")
        return IndexFetchResult(data=[], source="tencent")
    def eastmoney(self, *args):
        calls.append("eastmoney")
        return IndexFetchResult(data=[], source="eastmoney")
    def sina(self, *args):
        calls.append("sina")
        return IndexFetchResult(data=[[int(datetime(2024,1,2,tzinfo=timezone.utc).timestamp()*1000), 10, 11, 9, 10, 0]], source="sina_hk")
    monkeypatch.setattr(EastmoneyIndexHistoryProvider, "fetch_history", eastmoney)
    monkeypatch.setattr(SinaIndexHistoryProvider, "fetch_hk_history", sina)
    monkeypatch.setattr(TencentIndexHistoryProvider, "fetch_history", tencent)
    sources = IndexHistorySources()
    day = datetime(2024,1,2,tzinfo=timezone.utc)
    result = sources.fetch_history(INDEX_CATALOG["HK_HSTECH"], day, day)
    assert calls == ["tencent", "sina"]
    assert result.source == "sina_hk"


def test_partial_sources_merge_real_rows_and_replace_missing_ohlc_only():
    first=int(datetime(2024,1,2,tzinfo=timezone.utc).timestamp()*1000)
    def source_a(*_):
        return IndexFetchResult(data=[[first,10,12,9,11,0],[first+86400000,12,12,12,12,0]],source='a')
    def source_b(*_):
        return IndexFetchResult(data=[[first,100,120,90,110,0],[first+86400000,11,13,10,12,0]],source='b')
    sources=IndexHistorySources()
    sources.providers=(source_a,source_b)
    result=sources.fetch_history(INDEX_CATALOG['US_SP500'],datetime(2024,1,2,tzinfo=timezone.utc),datetime(2024,1,3,tzinfo=timezone.utc))
    assert result.data==[[first,10,12,9,11,0],[first+86400000,11,13,10,12,0]]
    assert result.source=='a+b' and not result.is_close_only


def test_unsupported_old_calendar_does_not_stop_at_a_partial_source(monkeypatch):
    def unavailable_calendar(*_):
        raise ValueError('calendar does not cover this old range')
    monkeypatch.setattr('app.services.market.index_history_sources.session_dates',unavailable_calendar)
    old=int(datetime(1994,8,8,tzinfo=timezone.utc).timestamp()*1000)
    recent=int(datetime(2024,1,2,tzinfo=timezone.utc).timestamp()*1000)
    sources=IndexHistorySources()
    sources.providers=(lambda *_:IndexFetchResult(data=[[recent,10,12,9,11,0]],source='recent'),
        lambda *_:IndexFetchResult(data=[[old,5,7,4,6,0]],source='older'))
    result=sources.fetch_history(INDEX_CATALOG['HK_HSCEI'],datetime(1994,8,8,tzinfo=timezone.utc),datetime(2024,1,2,tzinfo=timezone.utc))
    assert [row[0] for row in result.data]==[old,recent] and result.source=='recent+older'


@pytest.mark.parametrize('symbol',['HK_HSTECH','CN_CSI_A500','US_VIX'])
def test_prelaunch_cache_never_leaks_into_published_history(symbol):
    from app.domain.market.index_history_policy import live_start_ms,utc_datetime
    launch=live_start_ms(symbol)
    valid=[launch,10,12,9,11,0]
    cache=FakeKlineStore([[launch-86400000,8,8,8,8,0],valid])
    sources=FakeIndexHistorySources({})
    start=utc_datetime(launch-86400000).date().isoformat()
    day=utc_datetime(launch).date().isoformat()
    result=IndexDataService(cache,sources).get_history(symbol=symbol,timeframe='1d',start_date=start,end_date=day)
    assert [row.as_row() for row in result.data]==[valid]
    assert result.coverage.start_date==day and sources.calls==[]
    before=IndexDataService(cache,sources).get_history(symbol=symbol,timeframe='1d',start_date=start,end_date=start)
    assert before.data==[] and sources.calls==[]
