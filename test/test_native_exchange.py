from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.infra.market_data.exchange import ExchangeGateway, MarketDataError, okx_interval
from app.infra.market_data.indicators import tech_calculator
from app.services.market.exchange_kline_fetcher import ExchangeKlineFetcher
from app.services.market.symbol_routing import MarketSymbolRouting


def candle(stamp, close=102):
    return [str(stamp), "100", "103", "99", str(close), "10", stamp + 59_999]


@pytest.mark.parametrize(("timeframe", "expected"), [("6h", "6Hutc"), ("12h", "12Hutc"), ("1d", "1Dutc"), ("1w", "1Wutc"), ("1M", "1Mutc")])
def test_okx_long_periods_retain_utc_candle_boundaries(timeframe, expected):
    assert okx_interval(timeframe) == expected


@pytest.mark.parametrize(("venue", "symbol", "host", "path", "query"), [
    ("binance", "PAXG/USDT", "api.binance.com", "/api/v3/klines", {"symbol": "PAXGUSDT", "interval": "1h", "startTime": "0", "limit": "250"}),
    ("binanceusdm", "BTC/USDT:USDT", "fapi.binance.com", "/fapi/v1/klines", {"symbol": "BTCUSDT", "interval": "1h", "startTime": "0", "limit": "250"}),
    ("okx", "OKB/USDT", "www.okx.com", "/api/v5/market/history-candles", {"instId": "OKB-USDT", "bar": "1H", "after": "900000000", "before": "-1", "limit": "100"}),
])
def test_native_requests_do_not_download_market_metadata(venue, symbol, host, path, query):
    requests = []

    def respond(request):
        requests.append(request)
        rows = [candle(60_000), candle(0), candle(60_000, 103)]
        return httpx.Response(200, json={"code": "0", "data": rows} if venue == "okx" else rows)

    with ExchangeGateway(venue, transport=httpx.MockTransport(respond)) as gateway:
        rows, attempts = gateway.fetch_ohlcv(symbol, "1h", since=0, limit=250)
        assert attempts == 1
        assert rows == [[0, 100, 103, 99, 102, 10], [60_000, 100, 103, 99, 103, 10]]
        assert len(requests) == 1
        assert (requests[0].url.host, requests[0].url.path) == (host, path)
        assert dict(requests[0].url.params) == query
    assert gateway._client is None


def test_threads_reuse_one_connection_pool_and_shutdown_closes_it():
    with ExchangeGateway("binance", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[candle(0)]))) as gateway:
        gateway._request_interval = 0

        def fetch(_):
            rows, _ = gateway.fetch_ohlcv("BTC/USDT", "1m")
            return id(gateway.client), rows

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(fetch, range(12)))
        assert len({identity for identity, _ in results}) == 1
        client = gateway.client
    assert client.is_closed
    with pytest.raises(RuntimeError, match="已关闭"):
        gateway.fetch_ohlcv("BTC/USDT", "1m")


def test_retry_is_bounded_and_empty_history_is_not_a_failure():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=[])

    with ExchangeGateway("binance", transport=httpx.MockTransport(respond)) as gateway:
        gateway.retry_delay = gateway._request_interval = 0
        assert gateway.fetch_ohlcv("BTC/USDT", "1m", max_retries=2) == ([], 2)
        assert len(calls) == 2


@pytest.mark.parametrize(("status", "payload", "attempts", "error"), [
    (400, {"code": -1121}, 1, httpx.HTTPStatusError),
    (503, None, 2, httpx.HTTPStatusError),
    (200, {"unexpected": "response"}, 2, MarketDataError),
    (200, [[0, 1, 2, 0, "NaN", 1]], 2, MarketDataError),
])
def test_upstream_failure_is_never_reported_as_history_genesis(status, payload, attempts, error):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, json=payload)

    with ExchangeGateway("binance", transport=httpx.MockTransport(respond)) as gateway:
        gateway.retry_delay = gateway._request_interval = 0
        with pytest.raises(error):
            gateway.fetch_ohlcv("BTC/USDT", "1m", max_retries=2)
        assert len(requests) == attempts


def test_okx_history_continues_past_its_smaller_page_limit():
    stamps, requests = [i * 60_000 for i in range(250)], []

    def respond(request):
        params = request.url.params
        requests.append(params)
        selected = [stamp for stamp in reversed(stamps) if int(params["before"]) < stamp < int(params["after"])][:int(params["limit"])]
        return httpx.Response(200, json={"code": "0", "data": [candle(stamp) for stamp in selected]})

    with ExchangeGateway("okx", transport=httpx.MockTransport(respond)) as gateway:
        gateway._request_interval = 0
        routing = SimpleNamespace(fetch_symbol=lambda _: "OKB/USDT", gateway_for_symbol=lambda _: gateway)
        rows = ExchangeKlineFetcher(routing).fetch_gap("OKB/USDT", "1m", 0, stamps[-1] + 60_000)
        assert [row[0] for row in rows] == stamps
        assert len(requests) == 3
        assert {params["limit"] for params in requests} == {"100"}


@pytest.mark.parametrize("since", [None, 0])
def test_okx_recent_and_forward_reads_honor_requested_depth(since):
    stamps, requests = [i * 60_000 for i in range(250)], []

    def respond(request):
        params = request.url.params
        requests.append(dict(params))
        selected = [stamp for stamp in reversed(stamps) if int(params.get("before", -1)) < stamp < int(params.get("after", 10**15))][:int(params["limit"])]
        return httpx.Response(200, json={"code": "0", "data": [candle(stamp) for stamp in selected]})

    with ExchangeGateway("okx", transport=httpx.MockTransport(respond)) as gateway:
        gateway._request_interval = 0
        rows, attempts = gateway.fetch_ohlcv("OKB/USDT", "1m", since=since, limit=200)
        assert [row[0] for row in rows] == (stamps[-200:] if since is None else stamps[:200])
        assert attempts == len(requests) == 2


def test_concurrent_symbol_routing_shares_one_gateway_per_venue():
    routing = MarketSymbolRouting(ExchangeGateway("binance"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        gateways = list(pool.map(lambda _: routing.gateway_for_symbol("BTC/USDT:PERPETUAL"), range(16)))
    assert len({id(gateway) for gateway in gateways}) == 1
    assert gateways[0].exchange_id == "binanceusdm"
    routing.close()
    assert gateways[0]._closed


@pytest.mark.asyncio
async def test_chart_and_replay_report_upstream_failures_as_retryable():
    from fastapi import HTTPException, Response
    from app.routers.chart_workspace import chart_bars, chart_replay_bars

    async def unavailable(*_):
        raise MarketDataError("upstream returned HTML")

    service = SimpleNamespace(market=SimpleNamespace(bars=unavailable, replay_bars=unavailable))
    for call in (chart_bars("binance:spot:PAXGUSDT", "1h", 100, None, None, service),
                 chart_replay_bars(Response(), "binance:spot:PAXGUSDT", "1h", 1_700_000_000_000, None, 100, service)):
        with pytest.raises(HTTPException) as caught:
            await call
        assert caught.value.status_code == 502
        assert "请重试" in caught.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("recovers", [True, False])
async def test_shared_async_client_does_not_turn_html_failures_into_empty_history(recovers):
    from app.infra.market_data.binance_api import BinanceApiSupport

    calls = []

    def respond(request):
        calls.append(request)
        if not recovers or len(calls) == 1:
            return httpx.Response(200, text="<html>upstream unavailable</html>")
        return httpx.Response(200, json=[candle(0)])

    client = BinanceApiSupport(base_url="https://api.binance.com", cache_namespace="native-test")
    client.max_retries, client.retry_delay = 2, 0
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        if recovers:
            assert await client.get_json("/api/v3/klines") == [candle(0)]
        else:
            with pytest.raises(MarketDataError):
                await client.get_json("/api/v3/klines")
        assert len(calls) == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_drawdown_pages_history_then_refreshes_only_unfinished_day(monkeypatch):
    day = 86_400_000
    today = int(datetime.now(timezone.utc).timestamp() * 1000) // day * day
    rows = [[today - (1100 - i) * day, 100, 500, 90, 100 + i % 101, 1] for i in range(1100)]
    rows.append([today, 100, 600, 90, 500, 1])
    calls, closed = [], []

    class Gateway:
        fetch_limit = 1000

        def __init__(self, venue):
            assert venue == "binance"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            closed.append(True)

        def fetch_ohlcv(self, symbol, timeframe, since, limit):
            calls.append(since)
            return [row for row in rows if row[0] >= since][:limit], 1

    monkeypatch.setattr(tech_calculator, "ExchangeGateway", Gateway)
    provider = tech_calculator.TechCalculatorProvider()
    assert (await provider._calculate_drawdown())["value"] == 0
    assert len(calls) == 2 and len(closed) == 1
    provider._expensive_cache.clear()
    rows[-1][4] = 150
    assert (await provider._calculate_drawdown())["value"] == -25
    assert len(calls) == 3 and calls[-1] == today
    assert len(closed) == 2
    assert provider._drawdown_peak == 200


@pytest.mark.asyncio
async def test_weekly_average_uses_native_data_and_reuses_result(monkeypatch):
    calls = []

    class Gateway:
        def __init__(self, venue):
            assert venue == "binance"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def fetch_ohlcv(self, symbol, timeframe, since, limit):
            calls.append((symbol, timeframe, limit))
            return [[i * 604_800_000, 1, 1, 1, i + 1, 1] for i in range(210)], 1

    monkeypatch.setattr(tech_calculator, "ExchangeGateway", Gateway)
    provider = tech_calculator.TechCalculatorProvider()
    result = await provider._calculate_200wma()
    assert result["value"] == 110.5
    assert await provider._calculate_200wma() == result
    assert calls == [("BTC/USDT", "1w", 250)]


@pytest.mark.asyncio
async def test_interrupted_drawdown_does_not_commit_a_partial_historical_peak(monkeypatch):
    calls, closed = [], []

    class Gateway:
        fetch_limit = 2

        def __init__(self, _):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            closed.append(True)

        def fetch_ohlcv(self, _symbol, _timeframe, since, limit):
            calls.append(since)
            if len(calls) % 2 == 0:
                raise TimeoutError("interrupted history")
            return [[since, 100, 300, 100, 200, 1], [since + 86_400_000, 100, 300, 100, 300, 1]], 1

    monkeypatch.setattr(tech_calculator, "ExchangeGateway", Gateway)
    provider = tech_calculator.TechCalculatorProvider()
    initial = provider._drawdown_since
    assert await provider._calculate_drawdown() is None
    assert provider._drawdown_since == initial and provider._drawdown_peak == 0
    assert await provider._calculate_drawdown() is None
    assert calls[0] == calls[2] == initial
    assert len(closed) == 2
