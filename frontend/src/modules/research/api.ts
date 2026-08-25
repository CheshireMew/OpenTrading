import { apiGet, apiPost, apiPut } from '@/api/request'
import type {
  ResearchAlertCreateCommand,
  ResearchAlertEvaluationResponse,
  ResearchAlertResponse,
  ResearchAlertUpdateCommand,
  ResearchArchiveCommand,
  ResearchEventAcknowledgeCommand,
  ResearchEventResponse,
  ResearchEventPageResponse,
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
  ListTradeSignalsQueryParams,
  TradeSignalEvaluationRunResponse,
  TradeSignalPageResponse,
  TradeSignalResponse,
  TradeSignalStatsResponse,
  AssetResearchResponse,
  MarketScreenerRunPageResponse,
  MarketScreenerRunResponse,
  SavedMarketScreenerCreateCommand,
  SavedMarketScreenerListResponse,
  SavedMarketScreenerResponse,
  SavedMarketScreenerUpdateCommand,
  ResearchReportGenerateCommand,
  ResearchReportPageResponse,
  ResearchReportResponse,
} from './contracts'

export const researchApi = {
  listEvents(kind = 'alert_triggered', unacknowledgedOnly = true, limit = 100): Promise<ResearchEventPageResponse> {
    return apiGet('list_research_events', {
      query: { kind, unacknowledged_only: unacknowledgedOnly, limit },
    })
  },
  listReports(includeArchived = false, offset = 0, limit = 50): Promise<ResearchReportPageResponse> {
    return apiGet('list_research_reports', { query: { include_archived: includeArchived, offset, limit } })
  },
  generateReport(body: ResearchReportGenerateCommand): Promise<ResearchReportResponse> {
    return apiPost('generate_research_report', body, { client: 'longTask' })
  },
  getReport(id: string): Promise<ResearchReportResponse> {
    return apiGet('get_research_report', { path: { report_id: id } })
  },
  setReportArchived(id: string, expectedVersion: number, archived: boolean): Promise<ResearchReportResponse> {
    return apiPost(archived ? 'archive_research_report' : 'restore_research_report', { expectedVersion }, { path: { report_id: id } })
  },
  listScreeners(includeArchived = false): Promise<SavedMarketScreenerListResponse> {
    return apiGet('list_market_screeners', { query: { include_archived: includeArchived } })
  },
  createScreener(body: SavedMarketScreenerCreateCommand): Promise<SavedMarketScreenerResponse> {
    return apiPost('create_market_screener', body)
  },
  updateScreener(id: string, body: SavedMarketScreenerUpdateCommand): Promise<SavedMarketScreenerResponse> {
    return apiPut('update_market_screener', body, { path: { screener_id: id } })
  },
  setScreenerArchived(id: string, expectedVersion: number, archived: boolean): Promise<SavedMarketScreenerResponse> {
    return apiPost(archived ? 'archive_market_screener' : 'restore_market_screener', { expectedVersion }, { path: { screener_id: id } })
  },
  runScreener(id: string, asOf?: string): Promise<MarketScreenerRunResponse> {
    return apiPost('run_market_screener', { asOf: asOf || null }, { path: { screener_id: id } })
  },
  listScreenerRuns(id: string, offset = 0, limit = 50): Promise<MarketScreenerRunPageResponse> {
    return apiGet('list_market_screener_runs', { path: { screener_id: id }, query: { offset, limit } })
  },
  getAsset(
    symbol: string,
    timeframe = '1h',
    historyDays = 365,
    context: { assetClass?: string; chainId?: string; platform?: string } = {},
  ): Promise<AssetResearchResponse> {
    return apiGet('get_asset_research', {
      path: { symbol },
      query: {
        timeframe,
        history_days: historyDays,
        asset_class: context.assetClass || null,
        chain_id: context.chainId || null,
        platform: context.platform || null,
      },
    })
  },
  listSignals(query: ListTradeSignalsQueryParams = {}): Promise<TradeSignalPageResponse> {
    return apiGet('list_trade_signals', { query })
  },
  getSignalStats(): Promise<TradeSignalStatsResponse> {
    return apiGet('get_trade_signal_stats')
  },
  evaluateSignals(signalId?: string): Promise<TradeSignalEvaluationRunResponse> {
    return apiPost('evaluate_trade_signals', { signalId: signalId || null, force: true })
  },
  setSignalArchived(id: string, expectedVersion: number, archived: boolean): Promise<TradeSignalResponse> {
    return apiPost(archived ? 'archive_trade_signal' : 'restore_trade_signal', { expectedVersion }, { path: { signal_id: id } })
  },
  evaluateAlerts(): Promise<ResearchAlertEvaluationResponse> {
    return apiPost('evaluate_research_alerts', { force: true })
  },
  getWorkbench(eventLimit = 100, noteLimit = 200): Promise<ResearchWorkbenchResponse> {
    return apiGet('get_research_workbench', { query: { event_limit: eventLimit, note_limit: noteLimit } })
  },
  createWatchlist(body: ResearchWatchlistCreateCommand): Promise<ResearchWatchlistResponse> {
    return apiPost('create_research_watchlist', body)
  },
  updateWatchlist(id: string, body: ResearchWatchlistUpdateCommand): Promise<ResearchWatchlistResponse> {
    return apiPut('update_research_watchlist', body, { path: { watchlist_id: id } })
  },
  setWatchlistArchived(id: string, body: ResearchArchiveCommand, archived: boolean): Promise<ResearchWatchlistResponse> {
    return apiPost(archived ? 'archive_research_watchlist' : 'restore_research_watchlist', body, { path: { watchlist_id: id } })
  },
  createItem(body: ResearchWatchItemCreateCommand): Promise<ResearchWatchItemResponse> {
    return apiPost('create_research_watch_item', body)
  },
  updateItem(id: string, body: ResearchWatchItemUpdateCommand): Promise<ResearchWatchItemResponse> {
    return apiPut('update_research_watch_item', body, { path: { item_id: id } })
  },
  setItemArchived(id: string, body: ResearchArchiveCommand, archived: boolean): Promise<ResearchWatchItemResponse> {
    return apiPost(archived ? 'archive_research_watch_item' : 'restore_research_watch_item', body, { path: { item_id: id } })
  },
  createNote(body: ResearchNoteCreateCommand): Promise<ResearchNoteResponse> {
    return apiPost('create_research_note', body)
  },
  updateNote(id: string, body: ResearchNoteUpdateCommand): Promise<ResearchNoteResponse> {
    return apiPut('update_research_note', body, { path: { note_id: id } })
  },
  setNoteArchived(id: string, body: ResearchArchiveCommand, archived: boolean): Promise<ResearchNoteResponse> {
    return apiPost(archived ? 'archive_research_note' : 'restore_research_note', body, { path: { note_id: id } })
  },
  createAlert(body: ResearchAlertCreateCommand): Promise<ResearchAlertResponse> {
    return apiPost('create_research_alert', body)
  },
  updateAlert(id: string, body: ResearchAlertUpdateCommand): Promise<ResearchAlertResponse> {
    return apiPut('update_research_alert', body, { path: { alert_id: id } })
  },
  setAlertArchived(id: string, body: ResearchArchiveCommand, archived: boolean): Promise<ResearchAlertResponse> {
    return apiPost(archived ? 'archive_research_alert' : 'restore_research_alert', body, { path: { alert_id: id } })
  },
  acknowledgeEvent(id: string, body: ResearchEventAcknowledgeCommand): Promise<ResearchEventResponse> {
    return apiPut('acknowledge_research_event', body, { path: { event_id: id } })
  },
}
