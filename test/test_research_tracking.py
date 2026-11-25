from __future__ import annotations

import pytest

from app.contracts.research import (
    ResearchAlertCreateCommand,
    ResearchArchiveCommand,
    ResearchEventAcknowledgeCommand,
    ResearchNoteCreateCommand,
    ResearchWatchItemCreateCommand,
    ResearchWatchItemUpdateCommand,
    ResearchWatchlistCreateCommand,
)
from app.domain.research import ResearchDuplicateError, ResearchNotFoundError, ResearchRevisionConflictError
from app.infra.persistence.research_repository import ResearchRepository
from app.services.research_service import ResearchService
from app.services.research_alert_runtime import ResearchAlertRuntime


@pytest.mark.parametrize("kind", ["watchlist", "item", "note"])
def test_delete_research_records_checks_versions_and_removes_linked_content(research_service, installed_database_runtime, kind):
    from app.infra.db.schema import ResearchAlertRule, ResearchEvent, ResearchNote, ResearchWatchItem, ResearchWatchlist
    from sqlalchemy import select

    watchlist = research_service.create_watchlist(ResearchWatchlistCreateCommand(name="Delete me"))
    other = research_service.create_watchlist(ResearchWatchlistCreateCommand(name="Keep me"))
    item = research_service.create_watch_item(ResearchWatchItemCreateCommand(watchlistId=watchlist.id, symbol="BTC/USDT"))
    note = research_service.create_note(ResearchNoteCreateCommand(symbol="BTC/USDT", watchItemId=item.id, title="Private note", content="Remove this content"))
    alert = research_service.create_alert(ResearchAlertCreateCommand(symbol="BTC/USDT", watchItemId=item.id, name="Linked alert", metric="price", operator="gt", threshold=100))
    target = {"watchlist":watchlist,"item":item,"note":note}[kind]
    with pytest.raises(ResearchRevisionConflictError):
        research_service.delete_record(kind, target.id, target.version + 1)
    research_service.delete_record(kind, target.id, target.version)
    with installed_database_runtime.session_scope() as session:
        assert session.get(ResearchWatchlist, other.id) is not None
        assert session.get(ResearchNote, note.id) is None
        assert (session.get(ResearchWatchItem, item.id) is None) == (kind != "note")
        if kind != "note":
            assert session.get(ResearchAlertRule, alert.id) is None
        assert not list(session.scalars(select(ResearchEvent).where(ResearchEvent.entity_id == target.id)))
    with pytest.raises(ResearchNotFoundError, match="不存在"):
        research_service.delete_record(kind,target.id,target.version)


@pytest.mark.parametrize("kind", ["watchlists", "items", "notes", "screeners"])
def test_record_delete_api_requires_the_current_version(api_harness, installed_database_runtime, kind):
    from app.dependencies import get_research_service, get_market_screener_service
    from app.main import app
    from app.infra.persistence.market_screener_repository import MarketScreenerRepository
    from app.services.market_screener_service import MarketScreenerService
    from app.contracts.research import SavedMarketScreenerCreateCommand

    service = ResearchService(ResearchRepository(installed_database_runtime))
    screener_service = MarketScreenerService(repository=MarketScreenerRepository(installed_database_runtime), binance_market_service=object())
    app.dependency_overrides[get_research_service] = lambda: service
    app.dependency_overrides[get_market_screener_service] = lambda: screener_service
    watchlist = service.create_watchlist(ResearchWatchlistCreateCommand(name="List"))
    if kind == "items":
        target = service.create_watch_item(ResearchWatchItemCreateCommand(watchlistId=watchlist.id,symbol="BTC/USDT"))
    elif kind == "notes":
        target = service.create_note(ResearchNoteCreateCommand(symbol="BTC/USDT",title="Note"))
    elif kind == "screeners":
        target = screener_service.create(SavedMarketScreenerCreateCommand(name="Screen",filters={}))
    else:
        target = watchlist
    url = f"/api/v1/research/{kind}/{target.id}"
    client = api_harness["client"]
    assert client.delete(url,params={"expected_version":target.version+1}).status_code == 409
    assert client.delete(url,params={"expected_version":target.version}).json() == {"deleted":True}
    assert client.delete(url,params={"expected_version":target.version}).status_code == 404


@pytest.fixture
def research_service(installed_database_runtime):
    return ResearchService(ResearchRepository(installed_database_runtime))


def test_research_workbench_persists_thesis_notes_alerts_and_timeline(research_service):
    watchlist = research_service.create_watchlist(
        ResearchWatchlistCreateCommand(name="核心观察", description="长期跟踪")
    )
    item = research_service.create_watch_item(
        ResearchWatchItemCreateCommand(
            watchlistId=watchlist.id,
            symbol="btc/usdt",
            displayName="Bitcoin",
            thesis="流动性改善时继续观察。",
            targetPrice=150_000,
            invalidationPrice=80_000,
            tags=["核心", "核心", " 周期 "],
            sourceContext={"route": "/"},
        )
    )
    note = research_service.create_note(
        ResearchNoteCreateCommand(
            watchItemId=item.id,
            symbol=item.symbol,
            kind="thesis",
            title="初始判断",
            content="等待突破后确认。",
            snapshot={"price": 100_000},
        )
    )
    alert = research_service.create_alert(
        ResearchAlertCreateCommand(
            watchItemId=item.id,
            symbol=item.symbol,
            name="突破目标",
            metric="price",
            operator="crosses_above",
            threshold=110_000,
            notificationChannels=["in_app", "windows"],
        )
    )

    workbench = research_service.get_workbench(event_limit=100, note_limit=100)
    assert workbench.watchlists == [watchlist]
    assert workbench.items[0].symbol == "BTC/USDT"
    assert workbench.items[0].tags == ["核心", "周期"]
    assert workbench.notes == [note]
    assert workbench.alerts == [alert]
    assert workbench.unacknowledgedEventCount == 4

    acknowledged = research_service.acknowledge_event(
        workbench.events[0].id,
        ResearchEventAcknowledgeCommand(acknowledged=True),
    )
    assert acknowledged.acknowledgedAt is not None


def test_research_records_use_optimistic_versions_and_recoverable_archives(research_service):
    watchlist = research_service.create_watchlist(ResearchWatchlistCreateCommand(name="观察"))
    item = research_service.create_watch_item(
        ResearchWatchItemCreateCommand(watchlistId=watchlist.id, symbol="ETH/USDT")
    )
    updated = research_service.update_watch_item(
        item.id,
        ResearchWatchItemUpdateCommand(
            expectedVersion=item.version,
            watchlistId=watchlist.id,
            symbol=item.symbol,
            thesis="升级后的判断",
        ),
    )
    assert updated.version == item.version + 1

    with pytest.raises(ResearchRevisionConflictError):
        research_service.update_watch_item(
            item.id,
            ResearchWatchItemUpdateCommand(
                expectedVersion=item.version,
                watchlistId=watchlist.id,
                symbol=item.symbol,
            ),
        )

    archived = research_service.archive_watch_item(
        item.id,
        ResearchArchiveCommand(expectedVersion=updated.version),
        archived=True,
    )
    assert archived.archivedAt is not None
    restored = research_service.archive_watch_item(
        item.id,
        ResearchArchiveCommand(expectedVersion=archived.version),
        archived=False,
    )
    assert restored.archivedAt is None


def test_research_watchlist_rejects_duplicate_symbols(research_service):
    watchlist = research_service.create_watchlist(ResearchWatchlistCreateCommand(name="观察"))
    command = ResearchWatchItemCreateCommand(
        watchlistId=watchlist.id,
        symbol="SOL/USDT",
    )
    research_service.create_watch_item(command)
    with pytest.raises(ResearchDuplicateError):
        research_service.create_watch_item(command)


class _AlertSnapshot:
    def __init__(self, price: float) -> None:
        self.price = price

    async def get_market_page_snapshot_data(self):
        return {
            "spot_ticker": {"items": [{"symbol": "BTCUSDT", "last_price": self.price, "price_change_pct": 3.2}]},
            "usdm_ticker": {"items": []},
            "usdm_mark": {"items": []},
        }


class _AlertMarketPage:
    async def get_page(self, **_kwargs):
        raise AssertionError("price-only alerts do not need the market page")


class _AlertMarket:
    def __init__(self, snapshot):
        self.snapshot_service = snapshot
        self.page = _AlertMarketPage()


class _AlertQuery:
    async def get_current_price(self, **_kwargs):
        raise AssertionError("snapshot price should be used")




@pytest.mark.asyncio
async def test_research_alert_runtime_detects_crossing_and_emits_event(installed_database_runtime):
    repository = ResearchRepository(installed_database_runtime)
    service = ResearchService(repository)
    watchlist = service.create_watchlist(ResearchWatchlistCreateCommand(name="观察"))
    item = service.create_watch_item(ResearchWatchItemCreateCommand(watchlistId=watchlist.id, symbol="BTC/USDT"))
    service.create_alert(
        ResearchAlertCreateCommand(
            watchItemId=item.id,
            symbol=item.symbol,
            name="突破",
            metric="price",
            operator="crosses_above",
            threshold=100,
            notificationChannels=["in_app", "windows"],
        )
    )
    snapshot = _AlertSnapshot(90)
    runtime = ResearchAlertRuntime(
        research_repository=repository,
        market_query_service=_AlertQuery(),
        binance_market_service=_AlertMarket(snapshot),
    )

    first = await runtime.evaluate_once()
    assert first.evaluatedCount == 1
    assert first.triggeredCount == 0

    snapshot.price = 110
    second = await runtime.evaluate_once()
    assert second.triggeredCount == 1
    workbench = service.get_workbench(event_limit=100, note_limit=100)
    triggered = [event for event in workbench.events if event.kind == "alert_triggered"]
    assert len(triggered) == 1
    assert triggered[0].payload["value"] == 110
    assert triggered[0].payload["notificationChannels"] == ["in_app", "windows"]

    event_page = service.list_events(
        kind="alert_triggered",
        unacknowledged_only=True,
        since=None,
        limit=20,
    )
    assert event_page.total == 1
    assert event_page.items[0].id == triggered[0].id
