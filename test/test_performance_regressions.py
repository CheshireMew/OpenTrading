from __future__ import annotations

import asyncio
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
from app.infra.cache import RedisService
from app.infra.persistence.data_retention import cleanup_old_data
from app.infra.persistence.market.kline_store import KlineStore
from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
from app.infra.persistence.market.binance_market_research_store import BinanceMarketResearchStore
from app.services.market.binance_api_support import BinanceApiSupport
from app.services.market.binance_market_intel_service import BinanceMarketIntelService
from app.services.market.binance_market_page_state import BinanceMarketPageState
from app.services.market.history_query_service import MarketHistoryQueryService
from app.services.market.history_range_coordinator import HistoryRangeCoordinator
from app.services.tools.app_service import ToolsAppService
from config.settings import AppSettings


@pytest.mark.asyncio
async def test_async_cache_failure_does_not_block_event_loop_and_l1_is_bounded():
    cache = RedisService(
        AppSettings(
            DATABASE_URL="sqlite:///:memory:",
            REDIS_HOST="127.0.0.1",
            REDIS_PORT=1,
            REDIS_CONNECT_TIMEOUT=0.05,
            REDIS_SOCKET_TIMEOUT=0.05,
            REDIS_RETRY_INTERVAL=60,
            CACHE_MEMORY_MAX_ENTRIES=2,
        )
    )
    timer_fired = asyncio.Event()

    async def timer():
        await asyncio.sleep(0.02)
        timer_fired.set()

    timer_task = asyncio.create_task(timer())
    assert await cache.aget("missing") is None
    await asyncio.wait_for(timer_fired.wait(), timeout=0.2)
    await timer_task

    await cache.aset("one", {"value": 1}, ttl=30)
    await cache.aset("two", {"value": 2}, ttl=30)
    await cache.aset("three", {"value": 3}, ttl=30)
    assert cache.local_entry_count == 2
    assert await cache.aget("three") == {"value": 3}
    await cache.aclose()


@pytest.mark.asyncio
async def test_local_cache_is_byte_bounded_and_returns_fresh_values():
    cache = RedisService(
        AppSettings(
            DATABASE_URL="sqlite:///:memory:",
            REDIS_HOST="127.0.0.1",
            REDIS_PORT=1,
            REDIS_CONNECT_TIMEOUT=0.05,
            REDIS_SOCKET_TIMEOUT=0.05,
            REDIS_RETRY_INTERVAL=60,
            CACHE_MEMORY_MAX_ENTRIES=100,
            CACHE_MEMORY_MAX_BYTES=420,
        )
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
    await cache.aclose()


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
    assert max(parameter_counts) == 8_000


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
