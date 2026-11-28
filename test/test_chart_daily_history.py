"""Daily macro-market charts reuse real providers and the existing history cache."""
import asyncio
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.domain.market.history.models import PriceBar
from app.domain.market.index_fetch import IndexFetchResult
from app.infra.market_data.providers import ProviderFetch, YFinanceProvider
from app.services.chart_daily_history import ChartDailyHistory, daily_chart_symbols
from app.services.chart_workspace_market import ChartWorkspaceMarket
from app.contracts.chart_workspace import ChartSymbol
from app.services.market.history.catalog import resolve_instrument
from app.services.market.index_data_service import IndexDataService
from app.services.market_data_runtime import MarketDataRuntime
from config.settings import AppSettings
from test.test_index_data_service import FakeKlineStore


def stamp(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


@pytest.mark.asyncio
async def test_forward_daily_page_crosses_a_long_exchange_holiday():
    class Index:
        async def get_history_async(self, *, start_date, end_date, **kwargs):
            row = SimpleNamespace(as_row=lambda: [stamp('2024-10-08'), 100, 103, 99, 102, 10])
            return SimpleNamespace(data=[row] if start_date <= '2024-10-08' <= end_date else [],
                                   source='fixture', is_close_only=False, native_currency='CNY', price_basis='index')

    market = ChartWorkspaceMarket(None, Index())
    info = ChartSymbol(id='index:index:CN_SSE_COMP', symbol='CN_SSE_COMP', name='Shanghai Composite',
                       exchange='SSE', market='index', currency='CNY', timeframes=['1d'])

    async def resolve(_):
        return info

    market.resolve = resolve
    try:
        result = await market.bars(info.id, '1d', limit=1, start=stamp('2024-10-01'), end=stamp('2024-10-10'))
        assert [bar.time for bar in result.bars] == [stamp('2024-10-08')]
    finally:
        await market.close()


@pytest.fixture
def daily_runtime(installed_database_runtime, tmp_path):
    settings = AppSettings(_env_file=None, DATABASE_URL=installed_database_runtime.database_url,
                           MARKET_DATA_DIR=tmp_path / "market-history")
    return MarketDataRuntime(installed_database_runtime, settings)


@pytest.fixture
def provider_fetch(monkeypatch):
    calls = []

    def fetch(self, instrument, provider_symbol, start, end):
        calls.append((instrument.canonical_code, provider_symbol, start, end))
        bars = tuple(PriceBar(
            datetime.combine(day, datetime.min.time(), timezone.utc),
            open=100 + offset, high=103 + offset, low=99 + offset, close=102 + offset,
            adjusted_close=102 + offset, volume=None if instrument.asset_class == "fx" else 200,
        ) for offset in range((end - start).days + 1)
            if (day := start + timedelta(days=offset)).weekday() < 5)
        return ProviderFetch("yfinance", provider_symbol, {"dates": [bar.observation_date.isoformat() for bar in bars]}, bars)

    monkeypatch.setattr(YFinanceProvider, "fetch", fetch)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["GC1.COMEX", "EUR/USD"])
async def test_chart_reuses_cli_daily_snapshot_and_paginates_from_the_start(daily_runtime, provider_fetch, symbol):
    first, last = date(2024, 1, 2), date(2024, 1, 5)
    service = daily_runtime.prices
    acquired = service.history(symbol, start=first, end=last, include_analytics=False)
    assert acquired["status"] in {"ok", "partial"}
    history = ChartDailyHistory(daily_runtime)
    market = ChartWorkspaceMarket(None, None, daily_history=history)
    info = next(item for item in daily_chart_symbols() if item.symbol == symbol)
    market.catalog, market.catalog_at = {info.id: info}, time.time()
    try:
        result = await market.bars(info.id, "1d", limit=2, start=stamp("2024-01-02"), end=stamp("2024-01-05"))
        assert [bar.time for bar in result.bars] == [stamp("2024-01-02"), stamp("2024-01-03")]
        assert result.source == "yfinance" and not result.symbol.close_only
        assert all(bar.high > bar.low and bar.closed for bar in result.bars)
        assert result.symbol.metadata["snapshot_hash"] == acquired["artifact"]["snapshot_hash"]
        assert len(provider_fetch) == 1
        with pytest.raises(ValueError, match="不支持"):
            await market.bars(info.id, "1h")
        again = service.history(symbol, start=first, end=last, include_analytics=False)
        assert again["source"]["attempts"][-1]["status"] == "cache"
        assert len(provider_fetch) == 1
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_daily_chart_excludes_unclosed_dates_and_reports_last_two_trading_sessions(daily_runtime, provider_fetch, monkeypatch):
    import app.services.chart_workspace_market as module
    now = stamp("2024-01-08") + 12 * 3_600_000
    monkeypatch.setattr(module.time, "time", lambda: now / 1000)
    market = ChartWorkspaceMarket(None, None, daily_history=ChartDailyHistory(daily_runtime))
    info = next(item for item in daily_chart_symbols() if item.symbol == "EUR/USD")
    market.catalog, market.catalog_at = {info.id: info}, now / 1000
    try:
        bars = await market.bars(info.id, "1d", 2, end=now)
        assert [bar.time for bar in bars.bars] == [stamp("2024-01-04"), stamp("2024-01-05")]
        assert all(bar.closeTime <= now and bar.closed for bar in bars.bars)
        quote = (await market.quotes([info.id]))[0]
        assert quote.error is None and quote.change == 1 and quote.updated_at == stamp("2024-01-05")
        assert len(provider_fetch) == 1
    finally:
        await market.close()


@pytest.mark.asyncio
async def test_catalog_contains_daily_assets_when_exchange_metadata_is_unavailable():
    market = ChartWorkspaceMarket(None, None, daily_history=SimpleNamespace())
    async def unavailable(*args):
        raise ValueError("exchange offline")
    market.http.okx_symbol = unavailable
    # close() must use the same optional-port lifecycle as production.
    async def close():
        pass
    market.daily_history.close = close
    try:
        symbols = {item.symbol: item for item in await market.symbols()}
        assert {"US_VIX", "US_DXY", "GC1.COMEX", "SI1.COMEX", "CL1.NYMEX", "EUR/USD", "USD/JPY"} <= symbols.keys()
        assert "美元指数" in symbols["US_DXY"].aliases
        assert "黄金期货" in symbols["GC1.COMEX"].aliases
        assert all(item.timeframes == ["1d"] for item in symbols.values() if item.market != "index")
        assert all(item.timeframes == ['1m','5m','15m','30m','1h','4h','1d','1w','1M'] for item in symbols.values() if item.market == "index")
        assert symbols["GC1.COMEX"].metadata["is_continuous"]
        assert symbols["EUR/USD"].market == "fx"
    finally:
        await market.close()


def test_dxy_mapping_is_separate_from_fred_and_keeps_ice_holiday_sessions(daily_runtime):
    instruments = resolve_instrument(daily_runtime.views.persistence, "美元指数")
    assert [item.canonical_code for item in instruments] == ["DXY.INDEX"]
    assert instruments[0].exchange == "ICEUS"
    rows = [[stamp(day), 103, 104, 102, 103.5, 0] for day in ("2024-02-19", "2024-02-20")]
    def fetch(*args):
        return IndexFetchResult(data=rows, source="yfinance")
    sources = SimpleNamespace(fetch_history=fetch)
    result = IndexDataService(FakeKlineStore(), sources).get_history(
        symbol="US_DXY", timeframe="1d", start_date="2024-02-19", end_date="2024-02-20")
    assert [bar.timestamp for bar in result.data] == [row[0] for row in rows]
    assert result.coverage.complete and result.coverage.calendar == "ICEUS"
    assert result.pricing_symbol is None


@pytest.mark.parametrize("day", ["2024-07-01", "2024-11-04"])
def test_yahoo_index_preserves_the_session_date_in_both_dst_offsets(monkeypatch, day):
    import sys
    import pandas as pd
    from app.services.market.index_history_sources import IndexHistorySources
    from app.infra.market_data.index_source_catalog import get_index_source_binding
    from app.infra.market_data.index_history_http import YFinanceIndexHistoryProvider

    requested = []
    frame = pd.DataFrame({"Open": [103.0], "High": [104.0], "Low": [102.0], "Close": [103.5], "Volume": [0]},
                         index=pd.DatetimeIndex([day], tz="America/New_York"))
    class Ticker:
        def __init__(self, symbol):
            requested.append(symbol)
        def history(self, **kwargs):
            return frame
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=Ticker))
    assert get_index_source_binding("US_DXY").yfinance_symbol == "DX-Y.NYB"
    sources = IndexHistorySources()
    # Exercise the SDK fallback without calling the native primary or network.
    sources.providers = (YFinanceIndexHistoryProvider().fetch_history,)
    result = IndexDataService(FakeKlineStore(), sources).get_history(
        symbol="US_DXY", timeframe="1d", start_date=day, end_date=day)
    assert [point.timestamp for point in result.data] == [stamp(day)]
    assert requested == ["DX-Y.NYB"] and result.source == "yfinance"
    assert result.coverage.complete


@pytest.mark.asyncio
async def test_concurrent_daily_requests_share_acquisition(daily_runtime, provider_fetch):
    history = ChartDailyHistory(daily_runtime)
    try:
        first, second = await asyncio.gather(*[
            history.snapshot("EUR/USD", date(2024, 1, 2), date(2024, 1, 5)) for _ in range(2)
        ])
        assert first.snapshot_hash == second.snapshot_hash and len(provider_fetch) == 1
    finally:
        await history.close()
