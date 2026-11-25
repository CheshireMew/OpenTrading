from __future__ import annotations

import asyncio
import threading
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql

import app.lifecycle as lifecycle_module
import app.main as main_module
import app.services.tools.app_service as tools_app_module
from app.application.errors import InvalidRequestError
from app.contracts.tools import SimulateDcaCommand
from app.infra.cache import CacheService
from app.infra.persistence.data_retention import cleanup_old_data
from app.infra.persistence.market.kline_store import KlineStore
from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
from app.infra.persistence.market.binance_market_research_store import BinanceMarketResearchStore
from app.infra.market_data.binance_api import BinanceApiSupport
from app.services.market.binance_market_intel_service import BinanceMarketIntelService
from app.services.market.binance_market_page_state import BinanceMarketPageState
from app.services.market.history_query_service import MarketHistoryQueryService
from app.services.market.history_range_coordinator import HistoryRangeCoordinator
from app.services.tools.app_service import ToolsAppService
from app.services.tools.dca_service import DCAService
from app.services.tools.pair_compare_service import PairCompareService
from app.services.market.history_range_coordinator import OhlcvRangeResult
from app.services.chart_workspace_market import ChartWorkspaceMarket
from config.settings import AppSettings


def test_daily_compare_reads_native_closed_candles_without_five_minute_fanout():
    calls = []
    def history(symbol, timeframe, start, end):
        calls.append((symbol, timeframe, start, end))
        assert timeframe == "1d"
        rows = [[int((start + timedelta(days=index)).timestamp() * 1000), 100, 102, 99, 101, 10]
                for index in range((end - start).days)]
        return OhlcvRangeResult(rows, [])
    service = PairCompareService(SimpleNamespace(load_ohlcv_range=history), object())
    result = service.compare_pairs("BTC", "ETH", days=90, timeframe="1d")
    assert "error" not in result
    assert len(calls) == 2
    assert len(result["data_a"]) == len(result["data_b"]) == 90
    assert result["statistics"]["aligned_points"] == 90
    assert int(calls[0][3].timestamp() * 1000) % 86_400_000 == 0


@pytest.mark.parametrize("timeframe,expected", [("1w", ("2024-01-29", "2024-02-05")),
                                              ("1M", ("2024-01-01", "2024-02-01"))])
def test_compare_native_calendar_windows_are_aligned(timeframe, expected):
    start, end = PairCompareService._closed_history_window(3, timeframe, now=datetime(2024, 2, 7, tzinfo=timezone.utc))
    assert tuple(datetime.fromtimestamp(value.timestamp(), timezone.utc).date().isoformat() for value in (start, end)) == expected


@pytest.mark.parametrize("strategy,warmup", [("standard", 0), ("value_averaging", 0), ("fear_greed", 0),
                                            ("rsi_dynamic", 16), ("ema_deviation", 201), ("ahr999", 201)])
def test_dca_fetches_only_its_strategy_warmup_and_requested_days(strategy, warmup):
    calls = []
    def history(symbol, timeframe, start, end):
        calls.append((timeframe, start, end))
        size = int((end - start).total_seconds() // 3600) + 1
        rows = [[int((start + timedelta(hours=index)).timestamp() * 1000), 100, 101, 99, 100, 10]
                for index in range(size)]
        return OhlcvRangeResult(rows, [])
    sentiments = SimpleNamespace(get_sentiment_history=lambda *args: {})
    service = DCAService(SimpleNamespace(load_ohlcv_range=history), sentiments, object())
    result = service.calculate_dca(symbol="BTC/USDT", start_date_str="2026-01-01", end_date_str="2026-01-03",
                                   daily_investment=100, timezone="UTC", strategy=strategy)
    assert "error" not in result
    assert result["total_days"] == 3
    assert calls[0][0] == "1h"
    assert calls[0][1] == datetime(2026, 1, 1, tzinfo=timezone.utc) - timedelta(days=warmup)
    assert calls[0][2] == datetime(2026, 1, 4, tzinfo=timezone.utc) - timedelta(milliseconds=1)


def test_complete_history_tail_does_not_read_or_compose_smaller_periods(installed_database_runtime, monkeypatch):
    store = KlineStore(database_runtime=installed_database_runtime)
    start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [[start + index * 86_400_000, 100, 101, 99, 100, 10] for index in range(8)]
    store.save("ETH/USDT", "1d", rows)
    original = store._exact
    reads = []
    def exact(session, symbol, timeframe, *args, **kwargs):
        reads.append(timeframe)
        assert timeframe == "1d", "complete daily history caused a smaller-period read"
        return original(session, symbol, timeframe, *args, **kwargs)
    monkeypatch.setattr(store, "_exact", exact)
    assert store.get_before("ETH/USDT", "1d", start + 8 * 86_400_000, 5) == rows[-5:]
    assert reads == ["1d"]
    # A real hole is filled from the lower period instead of returning early
    # merely because the direct-row count happens to satisfy the limit.
    monkeypatch.setattr(store, "_exact", original)
    store.save("ETH/USDT", "1d", [[start + 9 * 86_400_000, 100, 101, 99, 100, 10]])
    hourly = [[start + 8 * 86_400_000 + hour * 3_600_000, 100, 101, 99, 100, 10] for hour in range(24)]
    store.save("ETH/USDT", "1h", hourly)
    filled = store.get_before("ETH/USDT", "1d", start + 10 * 86_400_000, 5)
    assert [row[0] for row in filled] == [start + day * 86_400_000 for day in range(5, 10)]


@pytest.mark.asyncio
async def test_large_cache_codec_runs_outside_the_api_event_loop(monkeypatch):
    import app.infra.cache_service as module
    cache = CacheService(AppSettings(_env_file=None))
    owner = threading.get_ident()
    original_encode, original_decode = module._serialize, module._deserialize
    def encode(value):
        assert threading.get_ident() != owner
        return original_encode(value)
    def decode(value):
        assert threading.get_ident() != owner
        return original_decode(value)
    monkeypatch.setattr(module, "_serialize", encode)
    monkeypatch.setattr(module, "_deserialize", decode)
    payload = {"history": ["x" * 20_000]}
    assert await cache.aset("large", payload)
    tick = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(tick.set_result, True)
    result = await cache.aget("large")
    assert tick.done() and result == payload
    result["history"].append("local-edit")
    assert await cache.aget("large") == payload


@pytest.mark.asyncio
async def test_tool_retries_share_running_work_without_cancelling_other_clients():
    entered, release = threading.Event(), threading.Event()
    calls = []
    def calculate(**kwargs):
        calls.append(kwargs)
        entered.set()
        assert release.wait(5)
        return {"history": [], "ok": True}
    service = ToolsAppService(SimpleNamespace(calculate_dca=calculate), object())
    command = SimulateDcaCommand(start_date=date(2026, 1, 1))
    first = asyncio.create_task(service.simulate_dca(command))
    second = asyncio.create_task(service.simulate_dca(command))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert await second == {"history": [], "ok": True}
        assert len(calls) == 1
        assert await service.simulate_dca(command) == {"history": [], "ok": True}
        assert len(calls) == 2
    finally:
        release.set()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.asyncio
async def test_chart_catalog_publishes_each_venue_without_waiting_for_optional_sources(monkeypatch):
    from app.routers.chart_workspace import chart_symbols

    release_usdm, release_okx = asyncio.Event(), asyncio.Event()
    row = {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "TRADING",
           "contractType": "PERPETUAL", "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.01"}]}
    async def spot(*args, **kwargs):
        return {"symbols": [row]}
    async def usdm(*args, **kwargs):
        await release_usdm.wait()
        return {"symbols": [row]}
    async def okx(*args, **kwargs):
        await release_okx.wait()
        return {"tickSz": "0.01", "lotSz": "1"}
    service = ChartWorkspaceMarket(SimpleNamespace(spot=SimpleNamespace(client=SimpleNamespace(get_json=spot)),
        usdm=SimpleNamespace(client=SimpleNamespace(get_json=usdm))), object())
    monkeypatch.setattr(service.http, "okx_symbol", okx)
    try:
        catalog = await asyncio.wait_for(service.symbols(), 1)
        assert "binance:spot:BTCUSDT" in {info.id for info in catalog}
        assert not release_okx.is_set() and not release_usdm.is_set()
        assert (await asyncio.wait_for(service.resolve("binance:spot:BTCUSDT"), 1)).market == "spot"
        waiting = asyncio.create_task(chart_symbols(symbol="okx:spot:OKB-USDT", service=SimpleNamespace(market=service)))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert not service._catalog_tasks["okx:spot"].cancelled()
        release_okx.set()
        assert (await asyncio.wait_for(service.resolve("okx:spot:OKB-USDT"), 1)).exchange == "okx"
        catalog = await chart_symbols(symbol="okx:spot:OKB-USDT", service=SimpleNamespace(market=service))
        assert "okx:spot:OKB-USDT" in {info.id for info in catalog}
        # An unrelated venue can still be pending after the requested one resolves.
        assert not release_usdm.is_set()
        release_usdm.set()
        assert (await asyncio.wait_for(service.resolve("binance:usdm:BTCUSDT"), 1)).market == "usdm"
        async def unavailable(*args, **kwargs):
            raise TimeoutError("controlled stale refresh")
        monkeypatch.setattr(service.binance.spot.client, "get_json", unavailable)
        service._catalog_checked["binance:spot"] = (0, True)
        assert (await asyncio.wait_for(service.resolve("binance:spot:BTCUSDT"), 1)).market == "spot"
        refresh = service._catalog_tasks["binance:spot"]
        await refresh
        assert service._catalog_checked["binance:spot"][1] is False
        assert (await service.resolve("binance:spot:BTCUSDT")).market == "spot"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_memory_cache_never_uses_network_and_is_entry_bounded(monkeypatch):
    def unexpected_connection(*args, **kwargs):
        pytest.fail("Memory cache must not open a network connection")

    monkeypatch.setattr("socket.socket.connect", unexpected_connection)
    cache = CacheService(AppSettings(CACHE_MEMORY_MAX_ENTRIES=2))
    for _ in range(3):
        assert cache.get("missing") is None
        assert await cache.aget("missing") is None
    assert cache.runtime_backend == "memory"
    assert cache.set("sync:first", {"value": 1}, ttl=30)
    assert cache.get("sync:first") == {"value": 1}
    assert await cache.aset("async:second", {"value": 2}, ttl=30)
    assert await cache.aget("async:second") == {"value": 2}
    assert cache.set("sync:third", {"value": 3}, ttl=30)
    assert cache.local_entry_count == 2
    assert cache.get("sync:first") is None
    assert await cache.adelete_prefix("async:") == 1
    assert cache.delete("sync:third")
    assert cache.local_entry_count == 0


def test_memory_cache_expires_entries_and_rejects_oversized_values(monkeypatch):
    cache = CacheService(AppSettings(CACHE_MEMORY_MAX_BYTES=64))
    clock = [100.0]
    monkeypatch.setattr("app.infra.cache_memory.time.monotonic", lambda: clock[0])
    assert cache.set("short", {"value": 1}, ttl=2)
    clock[0] = 101.0
    assert cache.get("short") == {"value": 1}
    clock[0] = 102.0
    assert cache.get("short") is None
    assert cache.local_entry_count == 0
    assert cache.local_byte_size == 0
    assert not cache.set("oversized", "x" * 100)
    assert cache.get("oversized") is None


@pytest.mark.asyncio
async def test_local_cache_is_byte_bounded_and_returns_fresh_values():
    cache = CacheService(
        AppSettings(CACHE_MEMORY_MAX_ENTRIES=100, CACHE_MEMORY_MAX_BYTES=420)
    )
    original = {"history": ["x" * 150]}
    await cache.aset("first", original, ttl=30)
    original["history"].append("mutated")
    first_read = await cache.aget("first")
    assert first_read == {"history": ["x" * 150]}
    first_read["history"].append("mutated again")
    assert await cache.aget("first") == {"history": ["x" * 150]}

    await cache.aset("second", {"history": ["y" * 250]}, ttl=30)
    assert cache.local_byte_size <= 420
    assert cache.local_entry_count == 1


@pytest.mark.asyncio
async def test_dca_rejects_oversized_custom_date_range_before_calculation(monkeypatch):
    calculator = MagicMock()
    service = ToolsAppService(calculator, pair_compare_service=object())
    monkeypatch.setattr(
        tools_app_module,
        "now_in_timezone",
        lambda _timezone: datetime(2026, 8, 24, tzinfo=timezone.utc),
    )

    with pytest.raises(InvalidRequestError, match="3650"):
        await service.simulate_dca(
            SimulateDcaCommand(
                symbol="BTC/USDT",
                start_date=date(2010, 1, 1),
                timezone="UTC",
            )
        )

    calculator.calculate_dca.assert_not_called()


@pytest.mark.asyncio
async def test_binance_client_reuses_connection_and_deduplicates_inflight_request():
    request_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"ok": True}, request=request)

    class MemoryCache:
        def __init__(self):
            self.values = {}

        async def aget(self, key):
            return self.values.get(key)

        async def aset(self, key, value, ttl=300):
            self.values[key] = value
            return True

    client = BinanceApiSupport(
        base_url="https://example.test",
        cache_namespace="test",
        cache_service=MemoryCache(),
    )
    shared_http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._client = shared_http_client

    results = await asyncio.gather(*(client.get_json("/ticker") for _ in range(12)))
    assert results == [{"ok": True}] * 12
    assert request_count == 1
    assert await client.get_json("/ticker") == {"ok": True}
    assert request_count == 1
    await client.aclose()
    assert shared_http_client.is_closed


def test_indicator_upsert_is_batched_and_updates_existing_points(installed_database_runtime):
    repository = MarketIndicatorRepository(database_runtime=installed_database_runtime)
    started_at = datetime(2025, 1, 1)
    points = [
        {
            "indicator_id": "PERF_TEST",
            "timestamp": started_at + timedelta(minutes=index),
            "value": float(index),
        }
        for index in range(1000)
    ]
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(installed_database_runtime.engine, "before_cursor_execute", record_statement)
    try:
        repository.upsert_points(points, {"PERF_TEST": ("Performance", "Tech", "")})
        assert len(statements) <= 8
        statements.clear()
        repository.upsert_points(
            [{**point, "value": point["value"] + 1.0} for point in points],
            {"PERF_TEST": ("Performance", "Tech", "")},
        )
        assert len(statements) <= 6
        history = repository.get_history_points(["PERF_TEST"])
        assert len(history["PERF_TEST"]) == 1000
        assert history["PERF_TEST"][0]["value"] == 1.0
    finally:
        event.remove(installed_database_runtime.engine, "before_cursor_execute", record_statement)


def test_large_kline_upsert_is_batched(installed_database_runtime):
    store = KlineStore(database_runtime=installed_database_runtime)
    rows = [
        [
            1_700_000_000_000 + index * 60_000,
            100.0,
            101.0,
            99.0,
            100.5,
            10.0,
        ]
        for index in range(13_584)
    ]
    insert_count = 0

    def count_inserts(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal insert_count
        if statement.lstrip().upper().startswith("INSERT INTO KLINES"):
            insert_count += 1

    event.listen(installed_database_runtime.engine, "before_cursor_execute", count_inserts)
    try:
        store.save("BTC/USDT", "1m", rows)
    finally:
        event.remove(installed_database_runtime.engine, "before_cursor_execute", count_inserts)

    assert insert_count == 14
    assert len(store.get_range("BTC/USDT", "1m", rows[0][0], rows[-1][0])) == len(rows)


def test_postgresql_kline_upsert_never_builds_a_giant_statement():
    class CaptureSession:
        def __init__(self):
            self.bind = SimpleNamespace(dialect=postgresql.dialect())
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)

        def rollback(self):
            raise AssertionError("batched PostgreSQL compilation should not roll back")

    rows = [
        [1_700_000_000_000 + index * 60_000, 100, 101, 99, 100, 1]
        for index in range(13_584)
    ]
    session = CaptureSession()
    KlineStore(database_runtime=object())._save_with_session(
        session,
        "BTC/USDT",
        "1m",
        rows,
    )

    parameter_counts = [
        len(statement.compile(dialect=postgresql.dialect()).params)
        for statement in session.statements
    ]
    assert len(session.statements) == 14
    assert max(parameter_counts) == 9_000  # Nine stored fields, including finalized.


def test_history_persistence_opens_bounded_transactions():
    batches = []
    coordinator = HistoryRangeCoordinator(store=object())
    coordinator._persist(
        "BTC/USDT",
        "1m",
        [[index, 1, 1, 1, 1, 1] for index in range(2_501)],
        lambda _symbol, _timeframe, rows: batches.append(rows),
    )

    assert [len(batch) for batch in batches] == [1_000, 1_000, 501]


def test_retention_uses_index_and_deletes_in_bounded_batches(
    installed_database_runtime,
    monkeypatch,
):
    monkeypatch.setattr(tools_app_module.settings, "KLINE_RETENTION_BATCH_SIZE", 250)
    store = KlineStore(database_runtime=installed_database_runtime)
    old_start = int((datetime.now(timezone.utc) - timedelta(days=400)).timestamp() * 1000)
    short_rows = [
        [old_start + index * 60_000, 100, 101, 99, 100, 1]
        for index in range(1_200)
    ]
    store.save("BTC/USDT", "1m", short_rows)
    store.save("BTC/USDT", "1d", [short_rows[0]])
    delete_count = 0

    def count_deletes(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal delete_count
        if statement.lstrip().upper().startswith("DELETE FROM KLINES"):
            delete_count += 1

    event.listen(installed_database_runtime.engine, "before_cursor_execute", count_deletes)
    try:
        deleted = cleanup_old_data(installed_database_runtime)
    finally:
        event.remove(installed_database_runtime.engine, "before_cursor_execute", count_deletes)

    with installed_database_runtime.engine.connect() as connection:
        plan = connection.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT symbol, timeframe, timestamp FROM klines "
                "WHERE timeframe IN ('1m', '5m', '15m', '1h', '4h') "
                "AND timestamp < :cutoff ORDER BY timestamp, timeframe, symbol LIMIT 250"
            ),
            {"cutoff": old_start + 10_000_000_000},
        ).all()
        daily_count = connection.scalar(
            text("SELECT COUNT(*) FROM klines WHERE timeframe = '1d'")
        )

    assert deleted == 1_200
    assert delete_count == 5
    assert daily_count == 1
    assert any("ix_klines_timeframe_timestamp" in str(row) for row in plan)


@pytest.mark.asyncio
async def test_api_lifespan_starts_and_stops_runtime(monkeypatch):
    events: list[str] = []

    class FakeDatabaseRuntime:
        def dispose(self):
            events.append("dispose")

    class FakeRuntime:
        def __init__(self):
            self.infra = SimpleNamespace(database_runtime=FakeDatabaseRuntime())

        async def start(self):
            events.append("start")

        async def shutdown(self):
            events.append("shutdown")

    monkeypatch.setattr(lifecycle_module, "_init_db", lambda *_args: events.append("database"))
    monkeypatch.setattr(lifecycle_module, "build_app_runtime_services", lambda _role=None: FakeRuntime())
    app = main_module.create_app(role="api")

    async with lifecycle_module.lifespan(app):
        events.append("inside")

    assert events == ["database", "start", "inside", "shutdown"]


@pytest.mark.asyncio
async def test_binance_page_state_has_bounded_configuration_cache():
    state = BinanceMarketPageState()
    for index in range(30):
        key = state.key(min_rise_pct=1.0 + index, limit=10, quote_asset="USDT")
        await state.register_request(key)

    requested = await state.requested_keys()
    assert len(requested) <= state._max_configs


def test_market_routes_reject_oversized_responses_and_batches(api_harness):
    client = api_harness["client"]
    oversized_history = client.get(
        "/api/v1/klines/latest",
        params={"symbol": "BTC/USDT", "timeframe": "1m", "limit": 5000},
    )
    oversized_prices = client.get(
        "/api/v1/price/current/batch",
        params=[*(('symbols', f'SYMBOL{index}/USDT') for index in range(51)), ('timeframe', '1d')],
    )
    oversized_batch = client.get(
        "/api/v1/full_history/batch",
        params=[*(('symbols', f'SYMBOL{index}/USDT') for index in range(11)), ('timeframe', '1d')],
    )

    assert oversized_history.status_code == 422
    assert oversized_prices.status_code == 422
    assert oversized_batch.status_code == 422


@pytest.mark.asyncio
async def test_full_history_rejects_excessive_point_range_before_fetching():
    service = MarketHistoryQueryService(market_data_service=object())

    with pytest.raises(ValueError, match="历史范围过大"):
        await service.get_full_history(
            symbol="BTC/USDT",
            timeframe="1m",
            start_date="2010-01-01",
        )


@pytest.mark.asyncio
async def test_binance_page_refresh_shares_expensive_enrichment_across_filters(
    installed_database_runtime,
    monkeypatch,
):
    service = BinanceMarketIntelService(
        research_store=BinanceMarketResearchStore(
            database_runtime=installed_database_runtime
        )
    )
    kline_calls = 0

    async def spot_tickers():
        return {
            "items": [
                {
                    "symbol": f"COIN{index}USDT",
                    "last_price": 10.0 + index,
                    "price_change_pct": 9.0 - index,
                    "quote_volume": 1_000_000.0 - index,
                }
                for index in range(3)
            ]
        }

    async def empty_items():
        return {"items": []}

    async def klines(**kwargs):
        nonlocal kline_calls
        kline_calls += 1
        return {
            "items": [
                {
                    "open_time": 1700000000000 + index * 900000,
                    "open": 10.0 + index * 0.01,
                    "high": 10.2 + index * 0.01,
                    "low": 9.9 + index * 0.01,
                    "close": 10.1 + index * 0.01,
                    "volume": 1000.0 + index,
                    "close_time": 1700000000000 + (index + 1) * 900000 - 1,
                }
                for index in range(80)
            ]
        }

    await service.snapshot_service.seed(
        spot_ticker_loader=spot_tickers,
        usdm_ticker_loader=empty_items,
        usdm_mark_loader=empty_items,
    )
    monkeypatch.setattr(service.spot, "get_klines", klines)
    await service.page.state.register_request((7.0, 10, "USDT"))
    await service.page.state.register_request((8.0, 5, "USDT"))

    await service.page.refresh_requested_payloads()

    assert kline_calls == 6
    for key in ((5.0, 24, "USDT"), (7.0, 10, "USDT"), (8.0, 5, "USDT")):
        cached, _ = await service.page.state.register_request(key)
        assert cached is not None
