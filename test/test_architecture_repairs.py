import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.contracts.research import ResearchAlertCreateCommand, ResearchAlertUpdateCommand
from app.domain.research import ResearchRevisionConflictError
from app.infra.db.schema import ResearchNote
from app.infra.persistence.research_repository import ResearchRepository
from app.infra.persistence.market_screener_repository import MarketScreenerRepository
from app.infra.persistence.market.indicator_repository import MarketIndicatorRepository
from app.infra.persistence.market.kline_store import KlineStore
from app.services.research_service import ResearchService
from app.services.market_screener_service import MarketScreenerService
from app.services.market.market_data_service import MarketDataService
from app.services.market.query_app_service import MarketQueryAppService
from app.services.market.realtime_service import RealtimeService
from app.services.market.binance_market_snapshot_service import BinanceMarketSnapshotService
from app.services.market.binance_market_page_service import BinanceMarketPageService
from app.services.market_scheduler_runtime import MarketSchedulerRuntime
from app.exceptions import ServiceUnavailableError


def test_alert_commit_rejects_edits_and_reorders_and_rechecks_cooldown(installed_database_runtime):
    repository = ResearchRepository(installed_database_runtime)
    service = ResearchService(repository)
    command = ResearchAlertCreateCommand(symbol="BTC/USDT", name="Price", metric="price", operator="gt", threshold=100)
    original = service.create_alert(command)
    edited = service.update_alert(original.id, ResearchAlertUpdateCommand(**{**command.model_dump(), "threshold": 200, "expectedVersion": 1}))
    at = datetime(2026, 11, 25)
    assert repository.record_alert_evaluation(original.id, value=150, evaluated_at=at, expected_version=1) is None
    saved = repository.record_alert_evaluation(original.id, value=150, evaluated_at=at, expected_version=edited.version)
    assert saved["lastTriggeredAt"] is None
    repository.record_alert_evaluation(original.id, value=250, evaluated_at=at + timedelta(seconds=1), expected_version=edited.version)
    assert repository.record_alert_evaluation(original.id, value=50, evaluated_at=at, expected_version=edited.version) is None
    repository.record_alert_evaluation(original.id, value=260, evaluated_at=at + timedelta(seconds=2), expected_version=edited.version)
    events = service.list_events(kind="alert_triggered", unacknowledged_only=False, since=None, limit=100)
    assert events.total == 1
    assert events.items[0].payload["threshold"] == 200


def test_alert_symbol_change_rejects_the_original_symbols_quote(installed_database_runtime):
    repository = ResearchRepository(installed_database_runtime)
    service = ResearchService(repository)
    command = ResearchAlertCreateCommand(symbol="BTC/USDT", name="Price", metric="price", operator="gt", threshold=100)
    row = service.create_alert(command)
    service.update_alert(row.id, ResearchAlertUpdateCommand(**{**command.model_dump(), "symbol": "ETH/USDT", "expectedVersion": row.version}))
    assert repository.record_alert_evaluation(row.id, value=150, evaluated_at=datetime(2026, 11, 25), expected_version=row.version) is None
    current = repository.list_enabled_alerts()[0]
    assert current["symbol"] == "ETH/USDT" and current["last_value"] is None


def test_screener_result_cannot_commit_after_edit_or_archive(installed_database_runtime):
    repository = MarketScreenerRepository(installed_database_runtime)
    row = repository.create_screener({"name": "Probe", "description": "", "filters": {"minRsi": 0}})
    result = {"filters_snapshot": row["filters"], "result_items": [], "result_count": 0,
              "snapshot_as_of": datetime(2026, 11, 25), "evaluated_at": datetime(2026, 11, 25)}
    edited = repository.update_screener(row["id"], 1, {"name": "Edited", "description": "", "filters": {"minRsi": 90}})
    with pytest.raises(ResearchRevisionConflictError):
        repository.save_run(row["id"], result, expected_version=1)
    archived = repository.set_screener_archived(row["id"], edited["version"], True)
    with pytest.raises(ResearchRevisionConflictError):
        repository.save_run(row["id"], result, expected_version=archived["version"])
    assert repository.list_runs(row["id"], offset=0, limit=10)[1] == 0


@pytest.mark.asyncio
async def test_unconfigured_spot_and_perpetual_rsi_keep_market_identity_without_model_calls(installed_database_runtime):
    calls, model_calls = [], []
    start = int(datetime.now(timezone.utc).timestamp() * 1000) // 3_600_000 * 3_600_000 - 199 * 3_600_000

    class Gateway:
        def __init__(self, exchange_id, rising):
            self.exchange_id, self.rising = exchange_id, rising

        def fetch_ohlcv(self, symbol, timeframe, **_kwargs):
            calls.append((self.exchange_id, symbol))
            prices = [100 + i if self.rising else 300 - i for i in range(200)]
            return [[start + i * 3_600_000, value, value + 1, value - 1, value, 1] for i, value in enumerate(prices)], 1

    data = MarketDataService(Gateway("binance", True), KlineStore(database_runtime=installed_database_runtime))
    data.symbol_routing._exchange_gateways["binanceusdm"] = Gateway("binanceusdm", False)
    query = MarketQueryAppService(market_data_service=data, realtime_service=RealtimeService(), llm_client_factory=lambda: model_calls.append(True))
    service = MarketScreenerService(repository=object(), binance_market_service=object(), market_query_service=query)
    result = await service._apply_rsi_filters([{"symbol": "XRPUSDT", "market": market} for market in ("spot", "usdm")], {"minRsi": 0})
    assert [(row["market"], row["rsi"]) for row in result] == [("spot", 100), ("usdm", 0)]
    assert ("binance", "XRP/USDT") in calls and ("binanceusdm", "XRP/USDT:USDT") in calls
    assert data.symbol_routing.storage_symbol("XRP/USDT:PERPETUAL") == "binance:usdm:XRPUSDT"
    assert not model_calls


@pytest.mark.asyncio
async def test_business_page_waits_and_coalesces_while_ui_can_remain_pending(monkeypatch):
    async def ticker(market):
        return {"items": [{"symbol": "XRPUSDT", "last_price": 100, "price_change_pct": 10, "quote_volume": 100000}]}

    snapshot = BinanceMarketSnapshotService(spot_ticker_loader=lambda: ticker("spot"), usdm_ticker_loader=lambda: ticker("usdm"),
                                           usdm_mark_loader=AsyncMock(return_value={"items": []}))
    page = BinanceMarketPageService(spot=object(), usdm=object(), snapshot_service=snapshot)
    assert not (await page.get_page(min_rise_pct=0, limit=100)).refresh_status.monitor_ready
    calls = []

    async def refresh(key):
        calls.append(key)
        await asyncio.sleep(.02)
        pending = await page._build_pending_page(key)
        pending.refresh_status.monitor_ready = True
        return pending

    monkeypatch.setattr(page, "refresh_page", refresh)
    first, second = await asyncio.gather(page.get_ready_page(), page.get_ready_page())
    assert first.refresh_status.monitor_ready and second is first and len(calls) == 1
    await page.shutdown()


@pytest.mark.asyncio
async def test_screener_never_saves_a_pending_page_as_an_empty_result():
    row = SimpleNamespace(market="spot", symbol="XRPUSDT", natural_score=10, momentum_score=20, verdict="watch")
    page = SimpleNamespace(updated_at=1, monitor=SimpleNamespace(items=[row]), contract_boards={})
    snapshot = {"updated_at": 1, "spot_ticker": {"items": [{"symbol": "XRPUSDT", "last_price": 1, "price_change_pct": 2, "quote_volume": 3}]}}
    ready = AsyncMock(return_value=page)
    service = MarketScreenerService(repository=object(), binance_market_service=SimpleNamespace(
        page=SimpleNamespace(get_ready_page=ready), snapshot_service=SimpleNamespace(get_ready_snapshot=AsyncMock(return_value=snapshot))))
    result = await service.preview({"market": "spot", "minBreakoutScore": 0})
    assert result["result_count"] == 1
    ready.side_effect = ServiceUnavailableError("offline")
    with pytest.raises(ServiceUnavailableError):
        await service.preview({"market": "spot", "minBreakoutScore": 0})


@pytest.mark.asyncio
async def test_cli_waits_for_market_readiness_without_owning_the_api_workspace(monkeypatch):
    import scripts.research_cli as cli
    events = []

    async def record(name):
        events.append(name)

    api = SimpleNamespace(market=SimpleNamespace(binance_intel=SimpleNamespace(start=lambda: record("start"),
        snapshot_service=SimpleNamespace(get_ready_snapshot=lambda: record("ready")))),
        market_screeners=SimpleNamespace(run=lambda *_: record("run")))
    monkeypatch.setattr(cli, "build_app_runtime_services", lambda *_: SimpleNamespace(require_api=lambda: api, shutdown=lambda: record("shutdown")))
    await cli.execute(SimpleNamespace(resource="screener", id="probe", as_of=None))
    assert events == ["start", "ready", "run", "shutdown"]


def test_indicator_ingress_and_http_dates_use_one_utc_instant(installed_database_runtime):
    repository = MarketIndicatorRepository(database_runtime=installed_database_runtime)
    for timestamp, value in [(datetime(2026, 1, 1, 12, tzinfo=timezone.utc), 1),
                             (datetime(2026, 1, 1, 20, tzinfo=timezone(timedelta(hours=8))), 2)]:
        repository.upsert_points([{"indicator_id": "HASHRATE", "timestamp": timestamp, "value": value}], {})
    rows = repository.get_history_points(["HASHRATE"])["HASHRATE"]
    assert len(rows) == 1 and rows[0]["value"] == 2 and rows[0]["date"] == "2026-01-01T12:00:00+00:00"


@pytest.mark.asyncio
async def test_all_failed_real_providers_mark_collection_failed():
    transitions = []
    status = SimpleNamespace(mark_running=lambda *a, **k: transitions.append("running"),
        mark_success=lambda *a, **k: transitions.append("success"), mark_failed=lambda *a, **k: transitions.append("failed"))
    scheduler = MarketSchedulerRuntime(indicator_repository=object(), cleanup_old_data=lambda: None, runtime_status_repository=status)
    scheduler._owner_id = "probe"
    with patch("httpx.AsyncClient", side_effect=OSError("controlled offline")), \
         patch("app.infra.market_data.indicators.sentiment_provider.run_external_io", new=AsyncMock(return_value=None)), \
         patch("app.infra.market_data.indicators.tech_calculator.run_external_io", new=AsyncMock(return_value=None)):
        with pytest.raises(RuntimeError, match="All market indicator providers failed"):
            await scheduler._run_market_indicator_job()
    assert transitions == ["running", "failed"]


def test_asset_notes_filter_before_limit_and_expose_paging(api_harness, installed_database_runtime):
    from app.dependencies import get_research_service
    from app.main import app
    at = datetime(2026, 1, 1)
    with installed_database_runtime.session_scope() as session:
        for i in range(3):
            session.add(ResearchNote(id=f"btc-{i}", symbol="BTC/USDT", kind="thesis", title="BTC", content="", snapshot={}, occurred_at=at + timedelta(seconds=i)))
        for i in range(1001):
            session.add(ResearchNote(id=f"eth-{i}", symbol="ETH/USDT", kind="thesis", title="ETH", content="", snapshot={}, occurred_at=at + timedelta(days=1, seconds=i)))
    repository = ResearchRepository(installed_database_runtime)
    assert len(repository.get_asset_records("BTC/USDT")["notes"]) == 3
    app.dependency_overrides[get_research_service] = lambda: ResearchService(repository)
    response = api_harness["client"].get("/api/v1/research/notes", params={"symbol": "BTC/USDT", "offset": 1, "limit": 1})
    assert response.status_code == 200, response.text
    page = response.json()
    assert (page["total"], page["offset"], [row["id"] for row in page["items"]]) == (3, 1, ["btc-1"])
