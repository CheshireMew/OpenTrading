from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.contracts.data_health import DataRepairCommand
from app.infra.persistence.data_health_repository import DataHealthRepository
from app.infra.persistence.market.kline_store import KlineStore
from app.services.data_health_service import DataHealthService
from app.services.market.index_data_service import IndexDataService
from app.services.market.history_query_service import MarketHistoryQueryService
from app.services.market.history_range_coordinator import OhlcvRangeResult


@pytest.mark.parametrize(
    ("days", "end", "missing"),
    [([20, 23], 23, []), ([20, 24], 24, ["2026-11-23"])],
    ids=["weekend-is-complete", "missing-monday"],
)
def test_kline_health_uses_the_producers_trading_calendar(installed_database_runtime, days, end, missing):
    store = KlineStore(database_runtime=installed_database_runtime)
    rows = [[int(datetime(2026, 11, day, tzinfo=timezone.utc).timestamp() * 1000), 100, 101, 99, 100, 1] for day in days]
    store.save("index:US:SP500", "1d", rows)
    sources = SimpleNamespace(fetch_history=lambda *args: SimpleNamespace(data=[], source="offline", is_close_only=False))
    history = IndexDataService(store, sources).get_history(
        symbol="US_SP500", timeframe="1d", start_date="2026-11-20", end_date=f"2026-11-{end}",
    )
    assert history.coverage.missing_sessions == missing

    snapshot = DataHealthRepository(installed_database_runtime).snapshot()
    health = DataHealthService._kline_source(snapshot, datetime(2026, 11, 25))

    assert health.gapCount == len(missing)
    assert health.metadata["series"][0]["expectedCount"] == len(history.coverage.expected_sessions)
    assert health.status == ("stale" if missing else "ready")


def test_kline_health_counts_calendar_months(installed_database_runtime):
    store = KlineStore(database_runtime=installed_database_runtime)
    rows = [[int(datetime(2024, month, 1, tzinfo=timezone.utc).timestamp() * 1000), 100, 101, 99, 100, 1] for month in (2, 3)]
    store.save("ETH/USDT", "1M", rows)
    health = DataHealthService._kline_source(DataHealthRepository(installed_database_runtime).snapshot(), datetime(2024, 3, 2))
    assert health.metadata["series"][0]["expectedCount"] == 2
    assert health.gapCount == 0


@pytest.mark.parametrize("days,missing", [([24, 25, 26, 27, 28], 0), ([24, 25, 26, 28], 1)])
def test_dxy_health_counts_ice_sessions_on_us_stock_holidays(installed_database_runtime, days, missing):
    # ICE has a DXY session on Thanksgiving while the US stock market is closed.
    store = KlineStore(database_runtime=installed_database_runtime)
    rows = [[int(datetime(2025, 11, day, tzinfo=timezone.utc).timestamp() * 1000), 100, 101, 99, 100, 1]
            for day in days]
    store.save("index:US:DXY", "1d", rows)

    health = DataHealthService._kline_source(DataHealthRepository(installed_database_runtime).snapshot(), datetime(2025, 11, 29))

    assert health.metadata["series"][0]["expectedCount"] == 5
    assert health.gapCount == missing


def test_health_summary_uses_metadata_for_disjoint_cold_history(installed_database_runtime, monkeypatch, api_harness):
    from app.infra.persistence.data_retention import archive_batch
    from app.infra.persistence.market.kline_archive import KlineArchive

    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [[start + i * 60_000, 100, 101, 99, 100 + i / 100_000, 1] for i in range(20_000)]
    store.save("ETH/USDT", "1m", rows)
    for _ in range(5):
        assert archive_batch(runtime, cutoff_ts=rows[-1][0] + 1, batch_size=4000) == 4000

    def reject_payload_read(*args, **kwargs):
        raise AssertionError("health summary must not decode archived OHLCV payloads")

    monkeypatch.setattr(KlineArchive, "read_segment", reject_payload_read)
    summary = DataHealthRepository(runtime).snapshot()["klines"]
    assert summary == [{"symbol": "ETH/USDT", "timeframe": "1m", "count": 20_000, "first": start, "last": rows[-1][0]}]
    from app.dependencies import get_data_health_service
    from app.main import app
    from test.test_repair_contracts import export_fixture

    service = DataHealthService(repository=DataHealthRepository(runtime), database_verifier=lambda: None,
        market_query_service=object(), index_data_service=object(),
        binance_market_service=SimpleNamespace(snapshot_service=StubSnapshot()),
        research_alert_runtime=object(), trade_signal_runtime=object())
    app.dependency_overrides[get_data_health_service] = lambda: service
    response = api_harness["client"].get("/api/v1/data-health")
    assert response.status_code == 200, response.text
    value = response.json()
    source = next(row for row in value["sources"] if row["id"] == "klines")
    assert (source["recordCount"], source["gapCount"]) == (20_000, 0)
    export_fixture("health.json", value)


def test_health_summary_preserves_cold_corrections_flags_and_hot_overlap(installed_database_runtime):
    from sqlalchemy import text
    from app.infra.persistence.data_retention import archive_batch

    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [[start + i * 60_000, 100, 101, 99, 100, 1] for i in range(6)]
    store.save("ETH/USDT", "1m", rows)
    with runtime.session_scope() as session:
        session.execute(text("UPDATE klines SET finalized=0 WHERE timestamp=:ts"), {"ts": rows[0][0]})
    assert archive_batch(runtime, cutoff_ts=rows[-1][0] + 1, batch_size=6) == 6
    # A newer archived unconfirmed correction masks a previously finalized row.
    changed = [*rows[2]]
    changed[4] = 100.5
    store.save("ETH/USDT", "1m", [changed])
    with runtime.session_scope() as session:
        session.execute(text("UPDATE klines SET finalized=0 WHERE timestamp=:ts"), {"ts": rows[2][0]})
    assert archive_batch(runtime, cutoff_ts=rows[-1][0] + 1, batch_size=6) == 1
    # A finalized hot correction overlaps the older finalized cold row.
    changed = [*rows[3]]
    changed[4] = 100.75
    store.save("ETH/USDT", "1m", [changed])
    visible = store.get_range("ETH/USDT", "1m", start, rows[-1][0])
    summary = DataHealthRepository(runtime).snapshot()["klines"]
    assert len(visible) == 4
    assert summary == [{"symbol": "ETH/USDT", "timeframe": "1m", "count": len(visible), "first": visible[0][0], "last": visible[-1][0]}]


def test_overlap_summary_bounds_file_fan_in_and_recovers_after_a_read_failure(installed_database_runtime, monkeypatch):
    from sqlalchemy import text
    from app.infra.persistence.data_retention import archive_batch
    from app.infra.persistence.market.kline_archive import KlineArchive

    runtime = installed_database_runtime
    store = KlineStore(database_runtime=runtime)
    start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    for revision in range(5):
        rows = [[start + i * 60_000, 100, 101, 99, 100 + revision / 100, 1] for i in range(1000)]
        store.save("ETH/USDT", "1m", rows)
        assert archive_batch(runtime, cutoff_ts=rows[-1][0] + 1, batch_size=1000) == 1000
    original = KlineArchive._coverage_flags
    counters = {"active": 0, "maximum": 0, "rows": 0}

    def tracked(self, segment):
        counters["active"] += 1
        counters["maximum"] = max(counters["maximum"], counters["active"])
        try:
            for row in original(self, segment):
                counters["rows"] += 1
                yield row
        finally:
            counters["active"] -= 1

    monkeypatch.setattr(KlineArchive, "_coverage_flags", tracked)
    monkeypatch.setattr(KlineArchive, "read_segment", lambda *_args, **_kwargs: pytest.fail("No OHLCV payload needed"))
    result = DataHealthRepository(runtime).snapshot()["klines"]
    assert result[0]["count"] == 1000
    assert counters == {"active": 0, "maximum": 1, "rows": 5000}

    def broken(self, segment):
        for row in original(self, segment):
            yield row
            raise RuntimeError("Controlled projected-read failure")

    monkeypatch.setattr(KlineArchive, "_coverage_flags", broken)
    with pytest.raises(RuntimeError, match="Controlled projected-read failure"):
        DataHealthRepository(runtime).snapshot()
    monkeypatch.setattr(KlineArchive, "_coverage_flags", original)
    assert DataHealthRepository(runtime).snapshot()["klines"] == result
    with runtime.session_scope() as session:
        assert session.execute(text("SELECT name FROM sqlite_temp_master WHERE name='kline_health_coverage'")).first() is None


class StubSnapshot:
    def health_snapshot(self):
        return {"status": "ready", "seedSuccessCount": 3, "activeStreams": 3, "error": None}

    async def get_market_page_snapshot_data(self):
        return {
            "updated_at": int(datetime.now(timezone.utc).timestamp() * 1000),
            "spot_ticker": {"items": [{}]},
            "usdm_ticker": {"items": [{}]},
            "usdm_mark": {"items": [{}]},
        }


@pytest.mark.parametrize("days,windows", [(1000, 3), (3650, 9)])
def test_history_repair_segments_large_ranges_and_reports_partial_coverage(api_harness, days, windows):
    from app.dependencies import get_data_health_service
    from app.main import app
    from test.test_repair_contracts import export_fixture

    requests = []
    end_day = datetime.now(timezone.utc).date()
    first_day = end_day - timedelta(days=days)
    gap_start = int(datetime.combine(first_day, datetime.min.time(), timezone.utc).timestamp() * 1000)
    def hydrate(symbol, timeframe, start, end, **kwargs):
        requests.append((start, end))
        assert timeframe == "1h"
        assert int((end - start).total_seconds() / 3600) + 1 <= 10_000
        gaps = [(gap_start, gap_start + 3_600_000)] if len(requests) == 1 else []
        return OhlcvRangeResult([[int(end.timestamp() * 1000), 100, 101, 99, 100, 1]], gaps)
    service = DataHealthService(repository=object(), database_verifier=lambda: None,
        market_query_service=MarketHistoryQueryService(market_data_service=SimpleNamespace(load_ohlcv_range=hydrate)),
        index_data_service=object(), binance_market_service=object(),
        research_alert_runtime=object(), trade_signal_runtime=object())
    app.dependency_overrides[get_data_health_service] = lambda: service
    response = api_harness["client"].post("/api/v1/data-health/repair", json={
        "action": "hydrate_symbol_history", "symbol": "BTC/USDT", "timeframe": "1h", "days": days,
    })
    assert response.status_code == 200, response.text
    value = response.json()
    assert len(requests) == windows
    assert requests[0][0].date() == first_day and requests[-1][1].date() == end_day
    assert all(left[1] + timedelta(milliseconds=1) == right[0] for left, right in zip(requests, requests[1:]))
    assert value["status"] == "partial" and value["result"]["coverageComplete"] is False
    assert value["result"]["pointCount"] == windows
    assert value["coverage"] == {"complete": False, "startDate": first_day.isoformat(), "endDate": end_day.isoformat(),
        "missingRanges": [{"start": first_day.isoformat() + "T00:00:00Z", "end": first_day.isoformat() + "T01:00:00Z"}],
        "missingSessions": []}
    if days == 1000:
        export_fixture("health-repair-partial.json", value)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [[], ["2026-11-23"]])
async def test_index_history_repair_preserves_missing_trading_sessions(missing):
    async def history(**kwargs):
        assert "end_date" in kwargs
        return SimpleNamespace(data=[1], source="offline", coverage=SimpleNamespace(complete=not missing, missing_sessions=missing))
    service = DataHealthService(repository=object(), database_verifier=lambda: None, market_query_service=object(),
        index_data_service=SimpleNamespace(get_pricing_history_async=history), binance_market_service=object(),
        research_alert_runtime=object(), trade_signal_runtime=object())
    response = await service.repair(DataRepairCommand(action="hydrate_symbol_history", symbol="US_SP500", days=10))
    assert response.status == ("partial" if missing else "completed")
    assert response.coverage.complete == (not missing)
    assert response.coverage.missingSessions == [date.fromisoformat(day) for day in missing]


def test_memory_cache_health_reports_ready():
    service = DataHealthService(
        repository=None, database_verifier=None, market_query_service=None,
        index_data_service=None, binance_market_service=None,
        research_alert_runtime=None, trade_signal_runtime=None,
        cache_service=SimpleNamespace(runtime_backend="memory", local_entry_count=2, local_byte_size=128),
    )
    result = service._cache_source()
    assert result.status == "ready"
    assert result.detail == "本地内存缓存可用"
    assert result.metadata["backend"] == "memory"


@pytest.mark.asyncio
async def test_data_health_reports_coverage_and_scoped_database_repair(installed_database_runtime):
    verified = []
    KlineStore(database_runtime=installed_database_runtime).save(
        "BTC/USDT",
        "1h",
        [
            [1_700_000_000_000, 1, 1, 1, 1, 1],
            [1_700_007_200_000, 1, 1, 1, 1, 1],
        ],
    )
    service = DataHealthService(
        repository=DataHealthRepository(installed_database_runtime),
        database_verifier=lambda: verified.append(True),
        market_query_service=object(),
        index_data_service=object(),
        binance_market_service=SimpleNamespace(snapshot_service=StubSnapshot()),
        research_alert_runtime=object(),
        trade_signal_runtime=object(),
        cache_service=SimpleNamespace(
            runtime_backend="memory",
            local_entry_count=3,
            local_byte_size=256,
        ),
    )

    health = await service.get_health()
    repair = await service.repair(DataRepairCommand(action="verify_database"))

    from alembic.script import ScriptDirectory
    from app.infra.db.schema_runtime import _alembic_config

    assert health.databaseRevision == ScriptDirectory.from_config(
        _alembic_config(installed_database_runtime.database_url)).get_current_head()
    assert any(source.id == "database" for source in health.sources)
    kline_source = next(source for source in health.sources if source.id == "klines")
    assert kline_source.gapCount == 1
    assert kline_source.coverageStart is not None
    assert next(source for source in health.sources if source.id == "runtime_cache").metadata["backend"] == "memory"
    assert repair.status == "completed"
    assert verified == [True]
