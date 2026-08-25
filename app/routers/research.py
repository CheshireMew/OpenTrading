from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Query

from app.contracts.frontend import FrontendContractRouter
from app.contracts.research import (
    ResearchAlertCreateCommand,
    ResearchAlertEvaluationResponse,
    ResearchAlertEvaluateCommand,
    ResearchAlertResponse,
    ResearchAlertUpdateCommand,
    ResearchArchiveCommand,
    ResearchEventAcknowledgeCommand,
    ResearchEventPageResponse,
    ResearchEventResponse,
    ResearchNoteCreateCommand,
    ResearchNoteResponse,
    ResearchNoteUpdateCommand,
    ResearchWatchItemCreateCommand,
    ResearchWatchItemResponse,
    ResearchWatchItemUpdateCommand,
    ResearchWatchlistCreateCommand,
    ResearchWatchlistResponse,
    ResearchWatchlistUpdateCommand,
    ResearchWorkbenchResponse,
    TradeSignalEvaluationCommand,
    TradeSignalEvaluationRunResponse,
    TradeSignalPageResponse,
    TradeSignalResponse,
    TradeSignalStatsResponse,
    AssetResearchResponse,
    MarketScreenerRunCommand,
    MarketScreenerRunPageResponse,
    MarketScreenerRunResponse,
    SavedMarketScreenerCreateCommand,
    SavedMarketScreenerListResponse,
    SavedMarketScreenerResponse,
    SavedMarketScreenerUpdateCommand,
    ResearchReportGenerateCommand,
    ResearchReportPageResponse,
    ResearchReportResponse,
)
from app.dependencies import (
    get_research_alert_runtime,
    get_research_service,
    get_trade_signal_evaluation_runtime,
    get_trade_signal_service,
    get_asset_research_service,
    get_market_screener_service,
    get_research_report_service,
)
from app.infra.executor import run_database


router = FrontendContractRouter(frontend_contract_target="research")


@router.get("/research/reports", response_model=ResearchReportPageResponse)
async def list_research_reports(
    include_archived: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    service=Depends(get_research_report_service),
):
    return await run_database(
        lambda: service.list_reports(include_archived=include_archived, offset=offset, limit=limit)
    )


@router.post("/research/reports", response_model=ResearchReportResponse)
async def generate_research_report(body: ResearchReportGenerateCommand, service=Depends(get_research_report_service)):
    return await service.generate(body)


@router.get("/research/reports/{report_id}", response_model=ResearchReportResponse)
async def get_research_report(report_id: str, service=Depends(get_research_report_service)):
    return await run_database(lambda: service.get_report(report_id))


@router.post("/research/reports/{report_id}/archive", response_model=ResearchReportResponse)
async def archive_research_report(
    report_id: str, body: ResearchArchiveCommand, service=Depends(get_research_report_service)
):
    return await run_database(lambda: service.archive(report_id, body, archived=True))


@router.post("/research/reports/{report_id}/restore", response_model=ResearchReportResponse)
async def restore_research_report(
    report_id: str, body: ResearchArchiveCommand, service=Depends(get_research_report_service)
):
    return await run_database(lambda: service.archive(report_id, body, archived=False))


@router.get("/research/screeners", response_model=SavedMarketScreenerListResponse)
async def list_market_screeners(
    include_archived: bool = False,
    service=Depends(get_market_screener_service),
):
    return await run_database(lambda: service.list_screeners(include_archived=include_archived))


@router.post("/research/screeners", response_model=SavedMarketScreenerResponse)
async def create_market_screener(body: SavedMarketScreenerCreateCommand, service=Depends(get_market_screener_service)):
    return await run_database(lambda: service.create(body))


@router.put("/research/screeners/{screener_id}", response_model=SavedMarketScreenerResponse)
async def update_market_screener(
    screener_id: str, body: SavedMarketScreenerUpdateCommand, service=Depends(get_market_screener_service)
):
    return await run_database(lambda: service.update(screener_id, body))


@router.post("/research/screeners/{screener_id}/archive", response_model=SavedMarketScreenerResponse)
async def archive_market_screener(
    screener_id: str, body: ResearchArchiveCommand, service=Depends(get_market_screener_service)
):
    return await run_database(lambda: service.archive(screener_id, body, archived=True))


@router.post("/research/screeners/{screener_id}/restore", response_model=SavedMarketScreenerResponse)
async def restore_market_screener(
    screener_id: str, body: ResearchArchiveCommand, service=Depends(get_market_screener_service)
):
    return await run_database(lambda: service.archive(screener_id, body, archived=False))


@router.post("/research/screeners/{screener_id}/run", response_model=MarketScreenerRunResponse)
async def run_market_screener(
    screener_id: str, body: MarketScreenerRunCommand, service=Depends(get_market_screener_service)
):
    return await service.run(screener_id, body)


@router.get("/research/screeners/{screener_id}/runs", response_model=MarketScreenerRunPageResponse)
async def list_market_screener_runs(
    screener_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    service=Depends(get_market_screener_service),
):
    return await run_database(lambda: service.list_runs(screener_id, offset=offset, limit=limit))


@router.get("/research/assets/{symbol:path}", response_model=AssetResearchResponse)
async def get_asset_research(
    symbol: str,
    timeframe: str = Query(default="1h", max_length=16),
    history_days: int = Query(default=365, ge=30, le=3_650),
    asset_class: str | None = Query(default=None, pattern="^(crypto|index|cash|web3)$"),
    chain_id: str | None = Query(default=None, max_length=32),
    platform: str | None = Query(default=None, max_length=32),
    service=Depends(get_asset_research_service),
):
    return await service.get_asset(
        symbol=symbol,
        timeframe=timeframe,
        history_days=history_days,
        asset_class=asset_class,
        chain_id=chain_id,
        platform=platform,
    )


@router.get("/research/signals", response_model=TradeSignalPageResponse)
async def list_trade_signals(
    symbol: str | None = Query(default=None, max_length=160),
    outcome_status: str | None = Query(default=None, max_length=32),
    source: str | None = Query(default=None, max_length=32),
    include_archived: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service=Depends(get_trade_signal_service),
):
    return await run_database(
        lambda: service.list_signals(
            symbol=symbol,
            outcome_status=outcome_status,
            source=source,
            include_archived=include_archived,
            offset=offset,
            limit=limit,
        )
    )


@router.get("/research/signals/stats", response_model=TradeSignalStatsResponse)
async def get_trade_signal_stats(service=Depends(get_trade_signal_service)):
    return await run_database(service.get_stats)


@router.post("/research/signals/evaluate", response_model=TradeSignalEvaluationRunResponse)
async def evaluate_trade_signals(
    body: TradeSignalEvaluationCommand,
    service=Depends(get_trade_signal_evaluation_runtime),
):
    return await service.evaluate_once(signal_id=body.signalId, force=body.force)


@router.post("/research/signals/{signal_id}/archive", response_model=TradeSignalResponse)
async def archive_trade_signal(
    signal_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_trade_signal_service),
):
    return await run_database(lambda: service.archive(signal_id, body, archived=True))


@router.post("/research/signals/{signal_id}/restore", response_model=TradeSignalResponse)
async def restore_trade_signal(
    signal_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_trade_signal_service),
):
    return await run_database(lambda: service.archive(signal_id, body, archived=False))


@router.post("/research/alerts/evaluate", response_model=ResearchAlertEvaluationResponse)
async def evaluate_research_alerts(
    _body: ResearchAlertEvaluateCommand,
    service=Depends(get_research_alert_runtime),
):
    return await service.evaluate_once()


@router.get("/research/workbench", response_model=ResearchWorkbenchResponse)
async def get_research_workbench(
    event_limit: int = Query(default=100, ge=1, le=500),
    note_limit: int = Query(default=200, ge=1, le=1_000),
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.get_workbench(event_limit=event_limit, note_limit=note_limit))


@router.get("/research/events", response_model=ResearchEventPageResponse)
async def list_research_events(
    kind: str | None = Query(default=None, max_length=80),
    unacknowledged_only: bool = False,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    service=Depends(get_research_service),
):
    return await run_database(
        lambda: service.list_events(
            kind=kind,
            unacknowledged_only=unacknowledged_only,
            since=since,
            limit=limit,
        )
    )


@router.post("/research/watchlists", response_model=ResearchWatchlistResponse)
async def create_research_watchlist(
    body: ResearchWatchlistCreateCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.create_watchlist(body))


@router.put("/research/watchlists/{watchlist_id}", response_model=ResearchWatchlistResponse)
async def update_research_watchlist(
    watchlist_id: str,
    body: ResearchWatchlistUpdateCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.update_watchlist(watchlist_id, body))


@router.post("/research/watchlists/{watchlist_id}/archive", response_model=ResearchWatchlistResponse)
async def archive_research_watchlist(
    watchlist_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.archive_watchlist(watchlist_id, body, archived=True))


@router.post("/research/watchlists/{watchlist_id}/restore", response_model=ResearchWatchlistResponse)
async def restore_research_watchlist(
    watchlist_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.archive_watchlist(watchlist_id, body, archived=False))


@router.post("/research/items", response_model=ResearchWatchItemResponse)
async def create_research_watch_item(
    body: ResearchWatchItemCreateCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.create_watch_item(body))


@router.put("/research/items/{item_id}", response_model=ResearchWatchItemResponse)
async def update_research_watch_item(
    item_id: str,
    body: ResearchWatchItemUpdateCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.update_watch_item(item_id, body))


@router.post("/research/items/{item_id}/archive", response_model=ResearchWatchItemResponse)
async def archive_research_watch_item(
    item_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.archive_watch_item(item_id, body, archived=True))


@router.post("/research/items/{item_id}/restore", response_model=ResearchWatchItemResponse)
async def restore_research_watch_item(
    item_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.archive_watch_item(item_id, body, archived=False))


@router.post("/research/notes", response_model=ResearchNoteResponse)
async def create_research_note(
    body: ResearchNoteCreateCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.create_note(body))


@router.put("/research/notes/{note_id}", response_model=ResearchNoteResponse)
async def update_research_note(
    note_id: str,
    body: ResearchNoteUpdateCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.update_note(note_id, body))


@router.post("/research/notes/{note_id}/archive", response_model=ResearchNoteResponse)
async def archive_research_note(
    note_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.archive_note(note_id, body, archived=True))


@router.post("/research/notes/{note_id}/restore", response_model=ResearchNoteResponse)
async def restore_research_note(
    note_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.archive_note(note_id, body, archived=False))


@router.post("/research/alerts", response_model=ResearchAlertResponse)
async def create_research_alert(
    body: ResearchAlertCreateCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.create_alert(body))


@router.put("/research/alerts/{alert_id}", response_model=ResearchAlertResponse)
async def update_research_alert(
    alert_id: str,
    body: ResearchAlertUpdateCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.update_alert(alert_id, body))


@router.post("/research/alerts/{alert_id}/archive", response_model=ResearchAlertResponse)
async def archive_research_alert(
    alert_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.archive_alert(alert_id, body, archived=True))


@router.post("/research/alerts/{alert_id}/restore", response_model=ResearchAlertResponse)
async def restore_research_alert(
    alert_id: str,
    body: ResearchArchiveCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.archive_alert(alert_id, body, archived=False))


@router.put("/research/events/{event_id}/acknowledgement", response_model=ResearchEventResponse)
async def acknowledge_research_event(
    event_id: str,
    body: ResearchEventAcknowledgeCommand,
    service=Depends(get_research_service),
):
    return await run_database(lambda: service.acknowledge_event(event_id, body))
