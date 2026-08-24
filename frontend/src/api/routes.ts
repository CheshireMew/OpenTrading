// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

import type * as MarketTypes from '../modules/market/contracts'
import type * as ToolsTypes from '../modules/tools/contracts'
import type * as ConfigTypes from '../modules/system/contracts'

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
  change_portfolio_collection: "/tools/portfolios",
  compare_pairs: "/tools/compare_pairs",
  dca_simulate: "/tools/dca_simulate",
  export_portfolio_collection: "/tools/portfolios/export",
  get_api_status: "/status",
  get_binance_market_contract_detail: "/binance/market/contract_detail",
  get_binance_market_klines: "/binance/market/klines",
  get_binance_market_page: "/binance/market/page",
  get_binance_web3_address_pnl_rank: "/binance/web3/address_pnl_rank",
  get_binance_web3_heat_rank_boards: "/binance/web3/heat_rank_boards",
  get_binance_web3_token_audit: "/binance/web3/token_audit",
  get_binance_web3_token_dynamic: "/binance/web3/token_dynamic",
  get_binance_web3_token_kline: "/binance/web3/token_kline",
  get_config: "/config",
  get_currencies: "/currencies",
  get_current_price: "/price/current",
  get_current_price_batch: "/price/current/batch",
  get_fred_api_config: "/fred-api-config",
  get_index_history: "/indexes/history",
  get_index_pricing_history: "/indexes/pricing/history",
  get_kline_tail: "/klines/tail",
  get_latest_klines: "/klines/latest",
  get_llm_config: "/llm-config",
  get_market_full_history: "/full_history",
  get_market_full_history_batch: "/full_history/batch",
  get_market_history: "/history",
  get_market_indicators: "/indicators",
  get_portfolio_collection: "/tools/portfolios",
  get_portfolio_simulation: "/tools/portfolios/{portfolio_id}/simulation",
  get_realtime_analysis: "/realtime",
  get_tools_contract: "/tools/contract",
  get_trade_setup: "/trade-setup",
  import_portfolio_collection: "/tools/portfolios/import",
  list_deleted_portfolios: "/tools/portfolios/deleted",
  list_market_indexes: "/indexes",
  list_market_symbols: "/symbols",
  restore_portfolio: "/tools/portfolios/{portfolio_id}/restore",
  save_portfolio_collection: "/tools/portfolios",
  save_portfolio_simulation: "/tools/portfolios/{portfolio_id}/simulation",
  update_fred_api_config: "/fred-api-config",
  update_llm_config: "/llm-config",
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
  change_portfolio_collection: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  compare_pairs: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  dca_simulate: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  export_portfolio_collection: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_api_status: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_market_contract_detail: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_market_klines: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_market_page: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_address_pnl_rank: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_heat_rank_boards: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_token_audit: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_token_dynamic: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_binance_web3_token_kline: {"repeatedKeys": [], "aliases": {"from_time": "from", "to_time": "to"}} as EndpointQueryContract,
  get_config: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_currencies: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_current_price: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_current_price_batch: {"repeatedKeys": ["symbols"], "aliases": {}} as EndpointQueryContract,
  get_fred_api_config: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_index_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_index_pricing_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_kline_tail: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_latest_klines: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_llm_config: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_market_full_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_market_full_history_batch: {"repeatedKeys": ["symbols"], "aliases": {}} as EndpointQueryContract,
  get_market_history: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_market_indicators: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_portfolio_collection: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_portfolio_simulation: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_realtime_analysis: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_tools_contract: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  get_trade_setup: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  import_portfolio_collection: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_deleted_portfolios: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_market_indexes: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  list_market_symbols: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  restore_portfolio: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  save_portfolio_collection: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  save_portfolio_simulation: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  update_fred_api_config: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
  update_llm_config: {"repeatedKeys": [], "aliases": {}} as EndpointQueryContract,
} as const

export type ApiRouteResponseMap = {
  change_portfolio_collection: ToolsTypes.PortfolioCollectionResponse
  compare_pairs: ToolsTypes.PairCompareToolResponse
  dca_simulate: ToolsTypes.DCAResponse
  export_portfolio_collection: ToolsTypes.PortfolioExportDocument
  get_api_status: MarketTypes.ApiStatusResponse
  get_binance_market_contract_detail: MarketTypes.BinanceContractResearchDetailResponse
  get_binance_market_klines: MarketTypes.MarketHistoryResponse
  get_binance_market_page: MarketTypes.BinanceMarketPageResponse
  get_binance_web3_address_pnl_rank: MarketTypes.BinanceWeb3AddressPnlResponse
  get_binance_web3_heat_rank_boards: MarketTypes.BinanceWeb3HeatRankBoardsResponse
  get_binance_web3_token_audit: MarketTypes.BinanceWeb3TokenAuditResponse
  get_binance_web3_token_dynamic: MarketTypes.BinanceWeb3TokenDynamicResponse
  get_binance_web3_token_kline: MarketTypes.BinanceWeb3TokenKlineResponse
  get_config: ConfigTypes.SystemConfigResponse
  get_currencies: ConfigTypes.CurrencyRatesResponse
  get_current_price: MarketTypes.CurrentPriceResponse
  get_current_price_batch: MarketTypes.CurrentPriceBatchResponse
  get_fred_api_config: ConfigTypes.FredApiConfigResponse
  get_index_history: MarketTypes.MarketIndexHistoryResponse
  get_index_pricing_history: MarketTypes.MarketIndexHistoryResponse
  get_kline_tail: MarketTypes.KlineTailResponse
  get_latest_klines: MarketTypes.MarketHistoryResponse
  get_llm_config: ConfigTypes.LlmProviderConfigResponse
  get_market_full_history: MarketTypes.MarketHistoryResponse
  get_market_full_history_batch: MarketTypes.MarketHistoryBatchResponse
  get_market_history: MarketTypes.MarketHistoryResponse
  get_market_indicators: Array<MarketTypes.MarketIndicatorResponse>
  get_portfolio_collection: ToolsTypes.PortfolioCollectionResponse
  get_portfolio_simulation: ToolsTypes.PortfolioSimulationResultResponse
  get_realtime_analysis: MarketTypes.RealtimeResponse
  get_tools_contract: ToolsTypes.ToolsPageContractResponse
  get_trade_setup: MarketTypes.TradeSetupResponse
  import_portfolio_collection: ToolsTypes.PortfolioCollectionResponse
  list_deleted_portfolios: ToolsTypes.PortfolioDeletedPage
  list_market_indexes: Array<MarketTypes.MarketIndexResponse>
  list_market_symbols: Array<MarketTypes.MarketSymbolSearchResponse>
  restore_portfolio: ToolsTypes.PortfolioCollectionResponse
  save_portfolio_collection: ToolsTypes.PortfolioCollectionResponse
  save_portfolio_simulation: ToolsTypes.PortfolioSimulationResultResponse
  update_fred_api_config: ConfigTypes.FredApiConfigResponse
  update_llm_config: ConfigTypes.LlmProviderConfigResponse
}

export type ApiRouteBodyMap = {
  change_portfolio_collection: ToolsTypes.PortfolioCollectionChangeCommand
  compare_pairs: ToolsTypes.ComparePairsCommand
  dca_simulate: ToolsTypes.SimulateDcaCommand
  export_portfolio_collection: never
  get_api_status: never
  get_binance_market_contract_detail: never
  get_binance_market_klines: never
  get_binance_market_page: never
  get_binance_web3_address_pnl_rank: never
  get_binance_web3_heat_rank_boards: never
  get_binance_web3_token_audit: never
  get_binance_web3_token_dynamic: never
  get_binance_web3_token_kline: never
  get_config: never
  get_currencies: never
  get_current_price: never
  get_current_price_batch: never
  get_fred_api_config: never
  get_index_history: never
  get_index_pricing_history: never
  get_kline_tail: never
  get_latest_klines: never
  get_llm_config: never
  get_market_full_history: never
  get_market_full_history_batch: never
  get_market_history: never
  get_market_indicators: never
  get_portfolio_collection: never
  get_portfolio_simulation: never
  get_realtime_analysis: never
  get_tools_contract: never
  get_trade_setup: never
  import_portfolio_collection: ToolsTypes.PortfolioCollectionImportCommand
  list_deleted_portfolios: never
  list_market_indexes: never
  list_market_symbols: never
  restore_portfolio: ToolsTypes.PortfolioRestoreCommand
  save_portfolio_collection: ToolsTypes.PortfolioCollectionSaveCommand
  save_portfolio_simulation: ToolsTypes.PortfolioSimulationResultCommand
  update_fred_api_config: ConfigTypes.FredApiConfigUpdateRequest
  update_llm_config: ConfigTypes.LlmProviderConfigUpdateRequest
}

export type ApiRoutePathMap = {
  change_portfolio_collection: never
  compare_pairs: never
  dca_simulate: never
  export_portfolio_collection: never
  get_api_status: never
  get_binance_market_contract_detail: never
  get_binance_market_klines: never
  get_binance_market_page: never
  get_binance_web3_address_pnl_rank: never
  get_binance_web3_heat_rank_boards: never
  get_binance_web3_token_audit: never
  get_binance_web3_token_dynamic: never
  get_binance_web3_token_kline: never
  get_config: never
  get_currencies: never
  get_current_price: never
  get_current_price_batch: never
  get_fred_api_config: never
  get_index_history: never
  get_index_pricing_history: never
  get_kline_tail: never
  get_latest_klines: never
  get_llm_config: never
  get_market_full_history: never
  get_market_full_history_batch: never
  get_market_history: never
  get_market_indicators: never
  get_portfolio_collection: never
  get_portfolio_simulation: { portfolio_id: string | number }
  get_realtime_analysis: never
  get_tools_contract: never
  get_trade_setup: never
  import_portfolio_collection: never
  list_deleted_portfolios: never
  list_market_indexes: never
  list_market_symbols: never
  restore_portfolio: { portfolio_id: string | number }
  save_portfolio_collection: never
  save_portfolio_simulation: { portfolio_id: string | number }
  update_fred_api_config: never
  update_llm_config: never
}

export type ApiRouteQueryMap = {
  change_portfolio_collection: never
  compare_pairs: never
  dca_simulate: never
  export_portfolio_collection: never
  get_api_status: never
  get_binance_market_contract_detail: MarketTypes.GetBinanceMarketContractDetailQueryParams
  get_binance_market_klines: MarketTypes.GetBinanceMarketKlinesQueryParams
  get_binance_market_page: MarketTypes.GetBinanceMarketPageQueryParams
  get_binance_web3_address_pnl_rank: MarketTypes.GetBinanceWeb3AddressPnlRankQueryParams
  get_binance_web3_heat_rank_boards: MarketTypes.GetBinanceWeb3HeatRankBoardsQueryParams
  get_binance_web3_token_audit: MarketTypes.GetBinanceWeb3TokenAuditQueryParams
  get_binance_web3_token_dynamic: MarketTypes.GetBinanceWeb3TokenDynamicQueryParams
  get_binance_web3_token_kline: MarketTypes.GetBinanceWeb3TokenKlineQueryParams
  get_config: never
  get_currencies: never
  get_current_price: MarketTypes.GetCurrentPriceQueryParams
  get_current_price_batch: MarketTypes.GetCurrentPriceBatchQueryParams
  get_fred_api_config: never
  get_index_history: MarketTypes.GetIndexHistoryQueryParams
  get_index_pricing_history: MarketTypes.GetIndexPricingHistoryQueryParams
  get_kline_tail: MarketTypes.GetKlineTailQueryParams
  get_latest_klines: MarketTypes.GetLatestKlinesQueryParams
  get_llm_config: never
  get_market_full_history: MarketTypes.GetMarketFullHistoryQueryParams
  get_market_full_history_batch: MarketTypes.GetMarketFullHistoryBatchQueryParams
  get_market_history: MarketTypes.GetMarketHistoryQueryParams
  get_market_indicators: MarketTypes.GetMarketIndicatorsQueryParams
  get_portfolio_collection: never
  get_portfolio_simulation: never
  get_realtime_analysis: MarketTypes.GetRealtimeAnalysisQueryParams
  get_tools_contract: never
  get_trade_setup: MarketTypes.GetTradeSetupQueryParams
  import_portfolio_collection: never
  list_deleted_portfolios: ToolsTypes.ListDeletedPortfoliosQueryParams
  list_market_indexes: never
  list_market_symbols: never
  restore_portfolio: never
  save_portfolio_collection: never
  save_portfolio_simulation: never
  update_fred_api_config: never
  update_llm_config: never
}

export type ApiRouteResponse<N extends ApiRouteName> = ApiRouteResponseMap[N]
export type ApiRouteBody<N extends ApiRouteName> = ApiRouteBodyMap[N]
export type ApiRouteQuery<N extends ApiRouteName> = ApiRouteQueryMap[N]
export type ApiRoutePath<N extends ApiRouteName> = ApiRoutePathMap[N]
