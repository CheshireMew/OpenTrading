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
from app.domain.research import ResearchDuplicateError, ResearchRevisionConflictError
from app.infra.persistence.research_repository import ResearchRepository
from app.services.research_service import ResearchService
from app.services.research_alert_runtime import ResearchAlertRuntime


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


class _PortfolioRepository:
    def get_collection(self):
        raise AssertionError("price-only alerts do not need portfolios")


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
        portfolio_repository=_PortfolioRepository(),
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
