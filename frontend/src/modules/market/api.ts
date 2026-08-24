import { apiGet } from '@/api/request'
import type {
  BinanceContractResearchDetailResponse,
  BinanceMarketPageResponse,
  BinanceWeb3HeatRankBoardsResponse,
  BinanceWeb3AddressPnlResponse,
  BinanceWeb3TokenAuditResponse,
  BinanceWeb3TokenDynamicResponse,
  BinanceWeb3TokenKlineResponse,
  CurrentPriceBatchResponse,
  CurrentPriceResponse,
  RealtimeResponse,
  KlineTailResponse,
  TradeSetupResponse,
  MarketHistoryResponse,
  MarketHistoryBatchResponse,
  MarketIndicatorResponse,
  MarketIndexHistoryResponse,
  MarketSymbolSearchResponse,
  GetBinanceMarketContractDetailQueryParams,
  GetBinanceMarketPageQueryParams,
  GetBinanceMarketKlinesQueryParams,
  GetBinanceWeb3AddressPnlRankQueryParams,
  GetBinanceWeb3HeatRankBoardsQueryParams,
  GetBinanceWeb3TokenAuditQueryParams,
  GetBinanceWeb3TokenDynamicQueryParams,
  GetBinanceWeb3TokenKlineQueryParams,
  GetCurrentPriceBatchQueryParams,
  GetCurrentPriceQueryParams,
  GetIndexHistoryQueryParams,
  GetIndexPricingHistoryQueryParams,
  GetKlineTailQueryParams,
  GetLatestKlinesQueryParams,
  GetMarketFullHistoryBatchQueryParams,
  GetMarketFullHistoryQueryParams,
  GetMarketHistoryQueryParams,
  GetMarketIndicatorsQueryParams,
  GetRealtimeAnalysisQueryParams,
  GetTradeSetupQueryParams,
} from './contracts'

const MARKET_API_TIMEOUT_MS = {
  standard: 15000,
  liveMarket: 30000,
  history: 30000,
  externalMarket: 30000,
  aiTradeSetup: 180000,
} as const

export const marketCatalogApi = {
  getSymbols(): Promise<MarketSymbolSearchResponse[]> {
    return apiGet('list_market_symbols')
  },
}

export const marketLiveApi = {
  getRealtime(params: GetRealtimeAnalysisQueryParams): Promise<RealtimeResponse> {
    return apiGet('get_realtime_analysis', { query: params, timeout: MARKET_API_TIMEOUT_MS.liveMarket })
  },
}

export const marketInsightApi = {
  getTradeSetup(params: GetTradeSetupQueryParams & {
    signal?: AbortSignal
  }): Promise<TradeSetupResponse> {
    const client = params.mode === 'ai' ? 'longTask' : undefined
    const { signal, ...query } = params
    return apiGet('get_trade_setup', {
      client,
      query,
      signal,
      timeout: params.mode === 'ai' ? MARKET_API_TIMEOUT_MS.aiTradeSetup : MARKET_API_TIMEOUT_MS.standard,
    })
  },

  getIndicators(params: GetMarketIndicatorsQueryParams): Promise<MarketIndicatorResponse[]> {
    return apiGet('get_market_indicators', { query: params })
  },
}

export const marketHistoryApi = {
  getPriceSeriesWindow(params: GetMarketHistoryQueryParams): Promise<MarketHistoryResponse> {
    return apiGet('get_market_history', { query: params, timeout: MARKET_API_TIMEOUT_MS.history })
  },

  getLatestKlines(params: GetLatestKlinesQueryParams): Promise<MarketHistoryResponse> {
    return apiGet('get_latest_klines', { query: params, timeout: MARKET_API_TIMEOUT_MS.liveMarket })
  },

  getPriceSeriesTail(params: GetKlineTailQueryParams): Promise<KlineTailResponse> {
    return apiGet('get_kline_tail', { query: params, timeout: MARKET_API_TIMEOUT_MS.liveMarket })
  },

  getCurrentPrice(params: GetCurrentPriceQueryParams): Promise<CurrentPriceResponse> {
    return apiGet('get_current_price', { query: params, timeout: MARKET_API_TIMEOUT_MS.liveMarket })
  },

  getCurrentPriceBatch(params: GetCurrentPriceBatchQueryParams): Promise<CurrentPriceBatchResponse> {
    return apiGet('get_current_price_batch', { query: params, timeout: MARKET_API_TIMEOUT_MS.liveMarket })
  },

  getPriceHistory(params: GetMarketFullHistoryQueryParams): Promise<MarketHistoryResponse> {
    return apiGet('get_market_full_history', { query: params, timeout: MARKET_API_TIMEOUT_MS.history })
  },

  getBatchPriceHistory(params: GetMarketFullHistoryBatchQueryParams): Promise<MarketHistoryBatchResponse> {
    return apiGet('get_market_full_history_batch', { query: params, timeout: MARKET_API_TIMEOUT_MS.history })
  },
}

export const marketIndexApi = {
  getIndexHistory(params: GetIndexHistoryQueryParams): Promise<MarketIndexHistoryResponse> {
    return apiGet('get_index_history', { query: params, timeout: MARKET_API_TIMEOUT_MS.history })
  },

  getIndexPricingHistory(params: GetIndexPricingHistoryQueryParams): Promise<MarketIndexHistoryResponse> {
    return apiGet('get_index_pricing_history', { query: params, timeout: MARKET_API_TIMEOUT_MS.history })
  },
}

export const binanceMarketApi = {
  getBinanceMarketKlines(params: GetBinanceMarketKlinesQueryParams): Promise<MarketHistoryResponse> {
    return apiGet('get_binance_market_klines', { query: params, timeout: MARKET_API_TIMEOUT_MS.externalMarket })
  },

  getBinanceMarketContractDetail(params: GetBinanceMarketContractDetailQueryParams): Promise<BinanceContractResearchDetailResponse> {
    return apiGet('get_binance_market_contract_detail', { query: params, timeout: MARKET_API_TIMEOUT_MS.externalMarket })
  },

  getBinanceMarketPage(params: GetBinanceMarketPageQueryParams = {}): Promise<BinanceMarketPageResponse> {
    return apiGet('get_binance_market_page', { query: params, timeout: MARKET_API_TIMEOUT_MS.externalMarket })
  },
}

export const binanceWeb3Api = {
  getBinanceWeb3AddressPnlRank(params: GetBinanceWeb3AddressPnlRankQueryParams): Promise<BinanceWeb3AddressPnlResponse> {
    return apiGet('get_binance_web3_address_pnl_rank', { query: params, timeout: MARKET_API_TIMEOUT_MS.externalMarket })
  },

  getBinanceWeb3HeatRankBoards(params: GetBinanceWeb3HeatRankBoardsQueryParams = {}): Promise<BinanceWeb3HeatRankBoardsResponse> {
    return apiGet('get_binance_web3_heat_rank_boards', { query: params, timeout: MARKET_API_TIMEOUT_MS.externalMarket })
  },

  getBinanceWeb3TokenDynamic(params: GetBinanceWeb3TokenDynamicQueryParams): Promise<BinanceWeb3TokenDynamicResponse> {
    return apiGet('get_binance_web3_token_dynamic', { query: params, timeout: MARKET_API_TIMEOUT_MS.externalMarket })
  },

  getBinanceWeb3TokenKline(params: GetBinanceWeb3TokenKlineQueryParams): Promise<BinanceWeb3TokenKlineResponse> {
    return apiGet('get_binance_web3_token_kline', { query: params, timeout: MARKET_API_TIMEOUT_MS.externalMarket })
  },

  getBinanceWeb3TokenAudit(params: GetBinanceWeb3TokenAuditQueryParams): Promise<BinanceWeb3TokenAuditResponse> {
    return apiGet('get_binance_web3_token_audit', { query: params, timeout: MARKET_API_TIMEOUT_MS.externalMarket })
  },
}
