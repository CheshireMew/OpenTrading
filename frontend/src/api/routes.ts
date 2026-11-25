// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

import type * as MarketTypes from '../modules/market/contracts'
import type * as ToolsTypes from '../modules/tools/contracts'
import type * as ConfigTypes from '../modules/system/contracts'
import type * as ChartWorkspaceTypes from '../modules/chartWorkspace/generatedContracts'
import type * as ResearchTypes from '../modules/research/contracts'

export type RouteParams = Record<string, string | number>
export type ApiQueryShape = object
export type EndpointQueryContract = { aliases?: Record<string, string>; repeatedKeys?: readonly string[] }
export const API_BASE_PATH = "/api/v1"

const fillRoute = (template: string, params: RouteParams = {}) => template.replace(/\{([^}]+)\}/g, (_, key: string) => {
  const value = params[key]
  if (value === undefined || value === null || value === '') throw new Error(`Missing API route param: ${key}`)
  return encodeURIComponent(String(value))
})

const routeTemplates = {
  acknowledge_research_event: "/research/events/{event_id}/acknowledgement",
  archive_market_screener: "/research/screeners/{screener_id}/archive",
  archive_research_note: "/research/notes/{note_id}/archive",
  archive_research_watch_item: "/research/items/{item_id}/archive",
  archive_research_watchlist: "/research/watchlists/{watchlist_id}/archive",
  archive_trade_signal: "/research/signals/{signal_id}/archive",
  chart_archive_document: "/chart-workspace/{kind}/{key}/archive",
  chart_bars: "/chart-workspace/bars",
  chart_cancel_pine_run: "/chart-workspace/pine-runs/{key}/cancel",
  chart_capabilities: "/chart-workspace/capabilities",
  chart_create_pine_run: "/chart-workspace/pine-runs",
  chart_document: "/chart-workspace/{kind}/{key}",
  chart_documents: "/chart-workspace/{kind}",
  chart_get_pine_run: "/chart-workspace/pine-runs/{key}",
  chart_pine_records: "/chart-workspace/pine-runs/{key}/records",
  chart_pine_runs: "/chart-workspace/pine-runs",
  chart_quotes: "/chart-workspace/quotes",
  chart_replay_bars: "/chart-workspace/replay/bars",
  chart_rerun_pine: "/chart-workspace/pine-runs/{key}/rerun",
  chart_save_document: "/chart-workspace/{kind}/{key}",
  chart_symbol_icon: "/chart-workspace/symbol-icons/{asset}",
  chart_symbols: "/chart-workspace/symbols",
  compare_pairs: "/tools/compare_pairs",
  create_market_screener: "/research/screeners",
  create_research_alert: "/research/alerts",
  create_research_note: "/research/notes",
  create_research_watch_item: "/research/items",
  create_research_watchlist: "/research/watchlists",
  dca_simulate: "/tools/dca_simulate",
  delete_market_screener: "/research/screeners/{screener_id}",
  delete_research_alert: "/research/alerts/{alert_id}",
  delete_research_note: "/research/notes/{note_id}",
  delete_research_watch_item: "/research/items/{item_id}",
  delete_research_watchlist: "/research/watchlists/{watchlist_id}",
  evaluate_browser_screener: "/research/screener-preview",
  evaluate_research_alerts: "/research/alerts/evaluate",
  evaluate_trade_signals: "/research/signals/evaluate",
  get_api_status: "/status",
  get_asset_research: "/research/assets/{symbol}",
  get_binance_market_contract_detail: "/binance/market/contract_detail",
  get_binance_market_klines: "/binance/market/klines",
  get_binance_market_page: "/binance/market/page",
  get_binance_web3_address_pnl_rank: "/binance/web3/address_pnl_rank",
  get_binance_web3_heat_rank_boards: "/binance/web3/heat_rank_boards",
  get_binance_web3_token_audit: "/binance/web3/token_audit",
  get_binance_web3_token_dynamic: "/binance/web3/token_dynamic",
  get_binance_web3_token_kline: "/binance/web3/token_kline",
  get_bitcoin_halving: "/bitcoin/halving",
  get_config: "/config",
  get_currencies: "/currencies",
  get_current_price: "/price/current",
  get_current_price_batch: "/price/current/batch",
  get_data_health: "/data-health",
  get_equity_catalog: "/equities/catalog",
  get_index_history: "/indexes/history",
  get_index_pricing_history: "/indexes/pricing/history",
  get_kline_tail: "/klines/tail",
  get_latest_klines: "/klines/latest",
  get_llm_config: "/llm-config",
  get_market_full_history: "/full_history",
  get_market_full_history_batch: "/full_history/batch",
  get_market_history: "/history",
  get_market_indicators: "/indicators",
  get_market_observations: "/binance/market/observations",
  get_realtime_analysis: "/realtime",
  get_research_workbench: "/research/workbench",
  get_tools_contract: "/tools/contract",
  get_trade_signal_stats: "/research/signals/stats",
  list_market_indexes: "/indexes",
  list_market_screener_runs: "/research/screeners/{screener_id}/runs",
  list_market_screeners: "/research/screeners",
  list_market_symbols: "/symbols",
  list_research_events: "/research/events",
  list_trade_signals: "/research/signals",
  refresh_signal_lab_liquidity: "/signal-lab/liquidity/refresh",
  repair_data_source: "/data-health/repair",
  restore_market_screener: "/research/screeners/{screener_id}/restore",
  restore_research_note: "/research/notes/{note_id}/restore",
  restore_research_watch_item: "/research/items/{item_id}/restore",
  restore_research_watchlist: "/research/watchlists/{watchlist_id}/restore",
  restore_trade_signal: "/research/signals/{signal_id}/restore",
  run_market_screener: "/research/screeners/{screener_id}/run",
  signal_lab_inventory: "/signal-lab/database",
  signal_lab_liquidity: "/signal-lab/liquidity",
  signal_lab_price_download: "/signal-lab/prices/download",
  signal_lab_price_history: "/signal-lab/prices/history",
  update_llm_config: "/llm-config",
  update_market_screener: "/research/screeners/{screener_id}",
  update_research_alert: "/research/alerts/{alert_id}",
  update_research_note: "/research/notes/{note_id}",
  update_research_watch_item: "/research/items/{item_id}",
  update_research_watchlist: "/research/watchlists/{watchlist_id}",
  workspace_defaults: "/chart-workspace/defaults/{kind}",
} as const

export type ApiRouteName = keyof typeof routeTemplates

export const apiRoute = (name: ApiRouteName, params?: RouteParams) => fillRoute(routeTemplates[name], params)

export const apiEndpoint = (name: ApiRouteName, params?: RouteParams) => ({
  name,
  url: apiRoute(name, params),
  query: endpointQueryContracts[name],
})

export const serializeEndpointQuery = (name: ApiRouteName, params: ApiQueryShape = {}) => {
  const contract = endpointQueryContracts[name]
  const query = new URLSearchParams()
  Object.entries(params as Record<string, unknown>).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') return
    const resolvedKey = contract?.aliases?.[key] ?? key
    const repeatedKeys = contract?.repeatedKeys ?? []
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== null && item !== undefined && item !== '') query.append(resolvedKey, String(item))
      })
      return
    }
    if (repeatedKeys.includes(key)) {
      query.append(resolvedKey, String(value))
      return
    }
    query.set(resolvedKey, String(value))
  })
  return query.toString()
}

const endpointQueryContracts = {
  acknowledge_research_event: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  archive_market_screener: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  archive_research_note: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  archive_research_watch_item: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  archive_research_watchlist: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  archive_trade_signal: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_archive_document: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_bars: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_cancel_pine_run: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_capabilities: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_create_pine_run: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_document: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_documents: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_get_pine_run: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_pine_records: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_pine_runs: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_quotes: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_replay_bars: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_rerun_pine: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_save_document: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_symbol_icon: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  chart_symbols: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  compare_pairs: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  create_market_screener: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  create_research_alert: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  create_research_note: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  create_research_watch_item: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  create_research_watchlist: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  dca_simulate: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  delete_market_screener: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  delete_research_alert: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  delete_research_note: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  delete_research_watch_item: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  delete_research_watchlist: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  evaluate_browser_screener: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  evaluate_research_alerts: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  evaluate_trade_signals: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_api_status: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_asset_research: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_market_contract_detail: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_market_klines: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_market_page: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_address_pnl_rank: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_heat_rank_boards: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_token_audit: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_token_dynamic: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_token_kline: {"repeatedKeys": [], "aliases": {"from_time": "from", "to_time": "to"}} as EndpointQueryContract,
  get_bitcoin_halving: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_config: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_currencies: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_current_price: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_current_price_batch: {"repeatedKeys": ["symbols"], "aliases": {}} as EndpointQueryContract,
  get_data_health: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_equity_catalog: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_index_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_index_pricing_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_kline_tail: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_latest_klines: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_llm_config: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_market_full_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_market_full_history_batch: {"repeatedKeys": ["symbols"], "aliases": {}} as EndpointQueryContract,
  get_market_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_market_indicators: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_market_observations: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_realtime_analysis: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_research_workbench: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_tools_contract: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_trade_signal_stats: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_market_indexes: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_market_screener_runs: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_market_screeners: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_market_symbols: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_research_events: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_trade_signals: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  refresh_signal_lab_liquidity: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  repair_data_source: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  restore_market_screener: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  restore_research_note: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  restore_research_watch_item: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  restore_research_watchlist: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  restore_trade_signal: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  run_market_screener: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  signal_lab_inventory: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  signal_lab_liquidity: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  signal_lab_price_download: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  signal_lab_price_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  update_llm_config: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  update_market_screener: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  update_research_alert: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  update_research_note: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  update_research_watch_item: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  update_research_watchlist: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  workspace_defaults: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
} as const

export type ApiRouteResponseMap = {
  acknowledge_research_event: ResearchTypes.ResearchEventResponse
  archive_market_screener: ResearchTypes.SavedMarketScreenerResponse
  archive_research_note: ResearchTypes.ResearchNoteResponse
  archive_research_watch_item: ResearchTypes.ResearchWatchItemResponse
  archive_research_watchlist: ResearchTypes.ResearchWatchlistResponse
  archive_trade_signal: ResearchTypes.TradeSignalResponse
  chart_archive_document: Record<string, boolean>
  chart_bars: ChartWorkspaceTypes.ChartBars
  chart_cancel_pine_run: ChartWorkspaceTypes.PineRun
  chart_capabilities: ChartWorkspaceTypes.PineCapabilities
  chart_create_pine_run: ChartWorkspaceTypes.PineRun
  chart_document: ChartWorkspaceTypes.WorkspaceDocument
  chart_documents: Array<ChartWorkspaceTypes.WorkspaceDocument>
  chart_get_pine_run: ChartWorkspaceTypes.PineRun
  chart_pine_records: ChartWorkspaceTypes.PineRecords
  chart_pine_runs: Array<ChartWorkspaceTypes.PineRun>
  chart_quotes: Array<ChartWorkspaceTypes.ChartQuote>
  chart_replay_bars: ChartWorkspaceTypes.ChartBars
  chart_rerun_pine: ChartWorkspaceTypes.PineRun
  chart_save_document: ChartWorkspaceTypes.WorkspaceDocument
  chart_symbol_icon: unknown
  chart_symbols: Array<ChartWorkspaceTypes.ChartSymbol>
  compare_pairs: ToolsTypes.PairCompareToolResponse
  create_market_screener: ResearchTypes.SavedMarketScreenerResponse
  create_research_alert: ResearchTypes.ResearchAlertResponse
  create_research_note: ResearchTypes.ResearchNoteResponse
  create_research_watch_item: ResearchTypes.ResearchWatchItemResponse
  create_research_watchlist: ResearchTypes.ResearchWatchlistResponse
  dca_simulate: ToolsTypes.DCAResponse
  delete_market_screener: Record<string, boolean>
  delete_research_alert: Record<string, boolean>
  delete_research_note: Record<string, boolean>
  delete_research_watch_item: Record<string, boolean>
  delete_research_watchlist: Record<string, boolean>
  evaluate_browser_screener: ResearchTypes.MarketScreenerRunResponse
  evaluate_research_alerts: ResearchTypes.ResearchAlertEvaluationResponse
  evaluate_trade_signals: ResearchTypes.TradeSignalEvaluationRunResponse
  get_api_status: MarketTypes.ApiStatusResponse
  get_asset_research: ResearchTypes.AssetResearchResponse
  get_binance_market_contract_detail: MarketTypes.BinanceContractResearchDetailResponse
  get_binance_market_klines: MarketTypes.MarketHistoryResponse
  get_binance_market_page: MarketTypes.BinanceMarketPageResponse
  get_binance_web3_address_pnl_rank: MarketTypes.BinanceWeb3AddressPnlResponse
  get_binance_web3_heat_rank_boards: MarketTypes.BinanceWeb3HeatRankBoardsResponse
  get_binance_web3_token_audit: MarketTypes.BinanceWeb3TokenAuditResponse
  get_binance_web3_token_dynamic: MarketTypes.BinanceWeb3TokenDynamicResponse
  get_binance_web3_token_kline: MarketTypes.BinanceWeb3TokenKlineResponse
  get_bitcoin_halving: MarketTypes.BitcoinHalvingResponse
  get_config: ConfigTypes.SystemConfigResponse
  get_currencies: ConfigTypes.CurrencyRatesResponse
  get_current_price: MarketTypes.CurrentPriceResponse
  get_current_price_batch: MarketTypes.CurrentPriceBatchResponse
  get_data_health: ConfigTypes.DataHealthResponse
  get_equity_catalog: MarketTypes.EquityCatalogResponse
  get_index_history: MarketTypes.MarketIndexHistoryResponse
  get_index_pricing_history: MarketTypes.MarketIndexHistoryResponse
  get_kline_tail: MarketTypes.KlineTailResponse
  get_latest_klines: MarketTypes.MarketHistoryResponse
  get_llm_config: ConfigTypes.LlmProviderConfigResponse
  get_market_full_history: MarketTypes.MarketHistoryResponse
  get_market_full_history_batch: MarketTypes.MarketHistoryBatchResponse
  get_market_history: MarketTypes.MarketHistoryResponse
  get_market_indicators: Array<MarketTypes.MarketIndicatorResponse>
  get_market_observations: Record<string, Record<string, number>>
  get_realtime_analysis: MarketTypes.RealtimeResponse
  get_research_workbench: ResearchTypes.ResearchWorkbenchResponse
  get_tools_contract: ToolsTypes.ToolsPageContractResponse
  get_trade_signal_stats: ResearchTypes.TradeSignalStatsResponse
  list_market_indexes: Array<MarketTypes.MarketIndexResponse>
  list_market_screener_runs: ResearchTypes.MarketScreenerRunPageResponse
  list_market_screeners: ResearchTypes.SavedMarketScreenerListResponse
  list_market_symbols: Array<MarketTypes.MarketSymbolSearchResponse>
  list_research_events: ResearchTypes.ResearchEventPageResponse
  list_trade_signals: ResearchTypes.TradeSignalPageResponse
  refresh_signal_lab_liquidity: MarketTypes.SignalLabRefreshResponse
  repair_data_source: ConfigTypes.DataRepairResponse
  restore_market_screener: ResearchTypes.SavedMarketScreenerResponse
  restore_research_note: ResearchTypes.ResearchNoteResponse
  restore_research_watch_item: ResearchTypes.ResearchWatchItemResponse
  restore_research_watchlist: ResearchTypes.ResearchWatchlistResponse
  restore_trade_signal: ResearchTypes.TradeSignalResponse
  run_market_screener: ResearchTypes.MarketScreenerRunResponse
  signal_lab_inventory: MarketTypes.SignalLabInventoryResponse
  signal_lab_liquidity: MarketTypes.SignalLabLiquidityResponse
  signal_lab_price_download: unknown
  signal_lab_price_history: MarketTypes.SignalLabPriceResponse
  update_llm_config: ConfigTypes.LlmProviderConfigResponse
  update_market_screener: ResearchTypes.SavedMarketScreenerResponse
  update_research_alert: ResearchTypes.ResearchAlertResponse
  update_research_note: ResearchTypes.ResearchNoteResponse
  update_research_watch_item: ResearchTypes.ResearchWatchItemResponse
  update_research_watchlist: ResearchTypes.ResearchWatchlistResponse
  workspace_defaults: Array<ChartWorkspaceTypes.WorkspaceDocument>
}

export type ApiRouteBodyMap = {
  acknowledge_research_event: ResearchTypes.ResearchEventAcknowledgeCommand
  archive_market_screener: ResearchTypes.ResearchArchiveCommand
  archive_research_note: ResearchTypes.ResearchArchiveCommand
  archive_research_watch_item: ResearchTypes.ResearchArchiveCommand
  archive_research_watchlist: ResearchTypes.ResearchArchiveCommand
  archive_trade_signal: ResearchTypes.ResearchArchiveCommand
  chart_archive_document: never
  chart_bars: never
  chart_cancel_pine_run: never
  chart_capabilities: never
  chart_create_pine_run: ChartWorkspaceTypes.PineRunRequest
  chart_document: never
  chart_documents: never
  chart_get_pine_run: never
  chart_pine_records: never
  chart_pine_runs: never
  chart_quotes: never
  chart_replay_bars: never
  chart_rerun_pine: never
  chart_save_document: ChartWorkspaceTypes.WorkspaceWrite
  chart_symbol_icon: never
  chart_symbols: never
  compare_pairs: ToolsTypes.ComparePairsCommand
  create_market_screener: ResearchTypes.SavedMarketScreenerCreateCommand
  create_research_alert: ResearchTypes.ResearchAlertCreateCommand
  create_research_note: ResearchTypes.ResearchNoteCreateCommand
  create_research_watch_item: ResearchTypes.ResearchWatchItemCreateCommand
  create_research_watchlist: ResearchTypes.ResearchWatchlistCreateCommand
  dca_simulate: ToolsTypes.SimulateDcaCommand
  delete_market_screener: never
  delete_research_alert: never
  delete_research_note: never
  delete_research_watch_item: never
  delete_research_watchlist: never
  evaluate_browser_screener: ResearchTypes.MarketScreenerFilters
  evaluate_research_alerts: ResearchTypes.ResearchAlertEvaluateCommand
  evaluate_trade_signals: ResearchTypes.TradeSignalEvaluationCommand
  get_api_status: never
  get_asset_research: never
  get_binance_market_contract_detail: never
  get_binance_market_klines: never
  get_binance_market_page: never
  get_binance_web3_address_pnl_rank: never
  get_binance_web3_heat_rank_boards: never
  get_binance_web3_token_audit: never
  get_binance_web3_token_dynamic: never
  get_binance_web3_token_kline: never
  get_bitcoin_halving: never
  get_config: never
  get_currencies: never
  get_current_price: never
  get_current_price_batch: never
  get_data_health: never
  get_equity_catalog: never
  get_index_history: never
  get_index_pricing_history: never
  get_kline_tail: never
  get_latest_klines: never
  get_llm_config: never
  get_market_full_history: never
  get_market_full_history_batch: never
  get_market_history: never
  get_market_indicators: never
  get_market_observations: never
  get_realtime_analysis: never
  get_research_workbench: never
  get_tools_contract: never
  get_trade_signal_stats: never
  list_market_indexes: never
  list_market_screener_runs: never
  list_market_screeners: never
  list_market_symbols: never
  list_research_events: never
  list_trade_signals: never
  refresh_signal_lab_liquidity: MarketTypes.SignalLabRefreshRequest
  repair_data_source: ConfigTypes.DataRepairCommand
  restore_market_screener: ResearchTypes.ResearchArchiveCommand
  restore_research_note: ResearchTypes.ResearchArchiveCommand
  restore_research_watch_item: ResearchTypes.ResearchArchiveCommand
  restore_research_watchlist: ResearchTypes.ResearchArchiveCommand
  restore_trade_signal: ResearchTypes.ResearchArchiveCommand
  run_market_screener: ResearchTypes.MarketScreenerRunCommand
  signal_lab_inventory: never
  signal_lab_liquidity: never
  signal_lab_price_download: never
  signal_lab_price_history: never
  update_llm_config: ConfigTypes.LlmProviderConfigUpdateRequest
  update_market_screener: ResearchTypes.SavedMarketScreenerUpdateCommand
  update_research_alert: ResearchTypes.ResearchAlertUpdateCommand
  update_research_note: ResearchTypes.ResearchNoteUpdateCommand
  update_research_watch_item: ResearchTypes.ResearchWatchItemUpdateCommand
  update_research_watchlist: ResearchTypes.ResearchWatchlistUpdateCommand
  workspace_defaults: never
}

export type ApiRoutePathMap = {
  acknowledge_research_event: { event_id: string | number }
  archive_market_screener: { screener_id: string | number }
  archive_research_note: { note_id: string | number }
  archive_research_watch_item: { item_id: string | number }
  archive_research_watchlist: { watchlist_id: string | number }
  archive_trade_signal: { signal_id: string | number }
  chart_archive_document: { kind: string | number; key: string | number }
  chart_bars: never
  chart_cancel_pine_run: { key: string | number }
  chart_capabilities: never
  chart_create_pine_run: never
  chart_document: { kind: string | number; key: string | number }
  chart_documents: { kind: string | number }
  chart_get_pine_run: { key: string | number }
  chart_pine_records: { key: string | number }
  chart_pine_runs: never
  chart_quotes: never
  chart_replay_bars: never
  chart_rerun_pine: { key: string | number }
  chart_save_document: { kind: string | number; key: string | number }
  chart_symbol_icon: { asset: string | number }
  chart_symbols: never
  compare_pairs: never
  create_market_screener: never
  create_research_alert: never
  create_research_note: never
  create_research_watch_item: never
  create_research_watchlist: never
  dca_simulate: never
  delete_market_screener: { screener_id: string | number }
  delete_research_alert: { alert_id: string | number }
  delete_research_note: { note_id: string | number }
  delete_research_watch_item: { item_id: string | number }
  delete_research_watchlist: { watchlist_id: string | number }
  evaluate_browser_screener: never
  evaluate_research_alerts: never
  evaluate_trade_signals: never
  get_api_status: never
  get_asset_research: { symbol: string | number }
  get_binance_market_contract_detail: never
  get_binance_market_klines: never
  get_binance_market_page: never
  get_binance_web3_address_pnl_rank: never
  get_binance_web3_heat_rank_boards: never
  get_binance_web3_token_audit: never
  get_binance_web3_token_dynamic: never
  get_binance_web3_token_kline: never
  get_bitcoin_halving: never
  get_config: never
  get_currencies: never
  get_current_price: never
  get_current_price_batch: never
  get_data_health: never
  get_equity_catalog: never
  get_index_history: never
  get_index_pricing_history: never
  get_kline_tail: never
  get_latest_klines: never
  get_llm_config: never
  get_market_full_history: never
  get_market_full_history_batch: never
  get_market_history: never
  get_market_indicators: never
  get_market_observations: never
  get_realtime_analysis: never
  get_research_workbench: never
  get_tools_contract: never
  get_trade_signal_stats: never
  list_market_indexes: never
  list_market_screener_runs: { screener_id: string | number }
  list_market_screeners: never
  list_market_symbols: never
  list_research_events: never
  list_trade_signals: never
  refresh_signal_lab_liquidity: never
  repair_data_source: never
  restore_market_screener: { screener_id: string | number }
  restore_research_note: { note_id: string | number }
  restore_research_watch_item: { item_id: string | number }
  restore_research_watchlist: { watchlist_id: string | number }
  restore_trade_signal: { signal_id: string | number }
  run_market_screener: { screener_id: string | number }
  signal_lab_inventory: never
  signal_lab_liquidity: never
  signal_lab_price_download: never
  signal_lab_price_history: never
  update_llm_config: never
  update_market_screener: { screener_id: string | number }
  update_research_alert: { alert_id: string | number }
  update_research_note: { note_id: string | number }
  update_research_watch_item: { item_id: string | number }
  update_research_watchlist: { watchlist_id: string | number }
  workspace_defaults: { kind: string | number }
}

export type ApiRouteQueryMap = {
  acknowledge_research_event: never
  archive_market_screener: never
  archive_research_note: never
  archive_research_watch_item: never
  archive_research_watchlist: never
  archive_trade_signal: never
  chart_archive_document: never
  chart_bars: ChartWorkspaceTypes.ChartBarsQueryParams
  chart_cancel_pine_run: never
  chart_capabilities: never
  chart_create_pine_run: never
  chart_document: ChartWorkspaceTypes.ChartDocumentQueryParams
  chart_documents: never
  chart_get_pine_run: never
  chart_pine_records: ChartWorkspaceTypes.ChartPineRecordsQueryParams
  chart_pine_runs: never
  chart_quotes: ChartWorkspaceTypes.ChartQuotesQueryParams
  chart_replay_bars: ChartWorkspaceTypes.ChartReplayBarsQueryParams
  chart_rerun_pine: never
  chart_save_document: never
  chart_symbol_icon: never
  chart_symbols: never
  compare_pairs: never
  create_market_screener: never
  create_research_alert: never
  create_research_note: never
  create_research_watch_item: never
  create_research_watchlist: never
  dca_simulate: never
  delete_market_screener: ResearchTypes.DeleteMarketScreenerQueryParams
  delete_research_alert: ResearchTypes.DeleteResearchAlertQueryParams
  delete_research_note: ResearchTypes.DeleteResearchNoteQueryParams
  delete_research_watch_item: ResearchTypes.DeleteResearchWatchItemQueryParams
  delete_research_watchlist: ResearchTypes.DeleteResearchWatchlistQueryParams
  evaluate_browser_screener: never
  evaluate_research_alerts: never
  evaluate_trade_signals: never
  get_api_status: never
  get_asset_research: ResearchTypes.GetAssetResearchQueryParams
  get_binance_market_contract_detail: MarketTypes.GetBinanceMarketContractDetailQueryParams
  get_binance_market_klines: MarketTypes.GetBinanceMarketKlinesQueryParams
  get_binance_market_page: MarketTypes.GetBinanceMarketPageQueryParams
  get_binance_web3_address_pnl_rank: MarketTypes.GetBinanceWeb3AddressPnlRankQueryParams
  get_binance_web3_heat_rank_boards: MarketTypes.GetBinanceWeb3HeatRankBoardsQueryParams
  get_binance_web3_token_audit: MarketTypes.GetBinanceWeb3TokenAuditQueryParams
  get_binance_web3_token_dynamic: MarketTypes.GetBinanceWeb3TokenDynamicQueryParams
  get_binance_web3_token_kline: MarketTypes.GetBinanceWeb3TokenKlineQueryParams
  get_bitcoin_halving: never
  get_config: never
  get_currencies: never
  get_current_price: MarketTypes.GetCurrentPriceQueryParams
  get_current_price_batch: MarketTypes.GetCurrentPriceBatchQueryParams
  get_data_health: never
  get_equity_catalog: MarketTypes.GetEquityCatalogQueryParams
  get_index_history: MarketTypes.GetIndexHistoryQueryParams
  get_index_pricing_history: MarketTypes.GetIndexPricingHistoryQueryParams
  get_kline_tail: MarketTypes.GetKlineTailQueryParams
  get_latest_klines: MarketTypes.GetLatestKlinesQueryParams
  get_llm_config: never
  get_market_full_history: MarketTypes.GetMarketFullHistoryQueryParams
  get_market_full_history_batch: MarketTypes.GetMarketFullHistoryBatchQueryParams
  get_market_history: MarketTypes.GetMarketHistoryQueryParams
  get_market_indicators: MarketTypes.GetMarketIndicatorsQueryParams
  get_market_observations: MarketTypes.GetMarketObservationsQueryParams
  get_realtime_analysis: MarketTypes.GetRealtimeAnalysisQueryParams
  get_research_workbench: ResearchTypes.GetResearchWorkbenchQueryParams
  get_tools_contract: never
  get_trade_signal_stats: never
  list_market_indexes: never
  list_market_screener_runs: ResearchTypes.ListMarketScreenerRunsQueryParams
  list_market_screeners: ResearchTypes.ListMarketScreenersQueryParams
  list_market_symbols: never
  list_research_events: ResearchTypes.ListResearchEventsQueryParams
  list_trade_signals: ResearchTypes.ListTradeSignalsQueryParams
  refresh_signal_lab_liquidity: never
  repair_data_source: never
  restore_market_screener: never
  restore_research_note: never
  restore_research_watch_item: never
  restore_research_watchlist: never
  restore_trade_signal: never
  run_market_screener: never
  signal_lab_inventory: never
  signal_lab_liquidity: MarketTypes.SignalLabLiquidityQueryParams
  signal_lab_price_download: MarketTypes.SignalLabPriceDownloadQueryParams
  signal_lab_price_history: MarketTypes.SignalLabPriceHistoryQueryParams
  update_llm_config: never
  update_market_screener: never
  update_research_alert: never
  update_research_note: never
  update_research_watch_item: never
  update_research_watchlist: never
  workspace_defaults: never
}

export type ApiRouteResponse<N extends ApiRouteName> = ApiRouteResponseMap[N]
export type ApiRouteBody<N extends ApiRouteName> = ApiRouteBodyMap[N]
export type ApiRouteQuery<N extends ApiRouteName> = ApiRouteQueryMap[N]
export type ApiRoutePath<N extends ApiRouteName> = ApiRoutePathMap[N]
