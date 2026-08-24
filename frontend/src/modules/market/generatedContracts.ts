// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

export interface MarketSymbolSearchResponse {
  symbol: string
  name: string
  asset_class: string
  market: string
  currency: string
  exchange?: string | null
  aliases?: Array<string>
  pricing_symbol?: string | null
  pricing_name?: string | null
  pricing_currency?: string | null
}

export interface ApiStatusResponse {
  status: string
  version: string
  framework: string
  dependencies: string
  timestamp: string
}

export interface RealtimeResponse {
  symbol: string
  timestamp: string
  current_price: number
  indicators: IndicatorSummaryResponse
  ai_analysis: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null
  kline_data?: Array<OhlcvPointResponse>
  timeframe?: string | null
  type?: string | null
}

export interface MarketHistoryResponse {
  symbol: string
  timeframe: string
  items?: Array<OhlcvPointResponse>
  coverage?: MarketHistoryCoverageResponse
}

export interface KlineTailResponse {
  symbol: string
  timeframe: string
  timestamp: string
  current_price: number | null
  kline_data?: Array<OhlcvPointResponse>
}

export interface CurrentPriceResponse {
  symbol: string
  timeframe: string
  timestamp: string
  current_price: number | null
}

export interface CurrentPriceBatchResponse {
  timeframe: string
  items?: Array<CurrentPriceBatchItemResponse>
}

export interface MarketHistoryBatchResponse {
  timeframe: string
  items?: Array<MarketHistoryBatchItemResponse>
}

export interface MarketIndexResponse {
  symbol: string
  name: string
  market: string
  currency: string
  pricing_symbol?: string | null
  pricing_name?: string | null
  pricing_currency?: string | null
}

export interface MarketIndexHistoryResponse {
  symbol: string
  name: string
  market: string
  currency: string
  native_currency?: string | null
  timeframe: string
  source: string
  price_basis?: string
  pricing_symbol?: string | null
  pricing_name?: string | null
  pricing_currency?: string | null
  is_close_only?: boolean
  count: number
  data?: Array<OhlcvPointResponse>
}

export interface MarketIndicatorResponse {
  indicator_id: string
  name: string
  category: string
  unit: string | null
  current_value: number | null
  last_updated: string | null
  data_lag_days?: number | null
  short_label?: string | null
  group?: string | null
  group_label?: string | null
  group_description?: string | null
  polarity?: string | null
  description?: string | null
  is_scored?: boolean | null
  history: Array<IndicatorHistoryPoint>
}

export interface TradeSetupResponse {
  symbol: string
  timeframe: string
  timestamp: string
  current_price: number | null
  setup: TradeSetupResponseItem | null
  reason: string
  source: string
  status: "ready" | "waiting" | "unavailable" | "rejected"
  error_code: string | null
}

export interface BinanceMarketPageResponse {
  exchange: string
  quote_asset: string
  updated_at: number
  monitor: BinanceBreakoutMonitorResponse
  spot_boards?: { [key: string]: BinanceTickerStatsResponse }
  contract_boards?: { [key: string]: BinanceContractBoardResponse }
  load_errors?: Array<string>
  refresh_status?: BinanceMarketPageRefreshStatusResponse
}

export interface BinanceContractResearchDetailResponse {
  exchange: string
  market: string
  symbol: string
  period: string
  open_interest: BinanceOpenInterestStatsResponse
  basis: BinanceBasisResponse
  taker_volume: BinanceTakerVolumeResponse
  force_orders: BinanceForceOrderResponse
  long_short_ratio: BinanceRatioSeriesResponse
  top_trader_accounts: BinanceRatioSeriesResponse
  top_trader_positions: BinanceRatioSeriesResponse
}

export interface BinanceWeb3AddressPnlResponse {
  source: string
  leaderboard: string
  page: number
  size: number
  pages?: number | null
  items?: Array<BinanceWeb3AddressPnlItemResponse>
}

export interface BinanceWeb3HeatRankBoardsResponse {
  source: string
  leaderboard: string
  chain_id: string
  size: number
  boards?: { [key: string]: BinanceWeb3HeatRankResponse }
  formula?: { [key: string]: Array<string> }
}

export interface BinanceWeb3TokenDynamicResponse {
  source: string
  chain_id: string
  contract_address: string
  price?: number | null
  native_token_price?: number | null
  volume_24h?: number | null
  volume_24h_buy?: number | null
  volume_24h_sell?: number | null
  volume_4h?: number | null
  volume_1h?: number | null
  volume_5m?: number | null
  count_24h?: number | null
  count_24h_buy?: number | null
  count_24h_sell?: number | null
  percent_change_5m?: number | null
  percent_change_1h?: number | null
  percent_change_4h?: number | null
  percent_change_24h?: number | null
  market_cap?: number | null
  fdv?: number | null
  total_supply?: number | null
  circulating_supply?: number | null
  price_high_24h?: number | null
  price_low_24h?: number | null
  holders?: number | null
  liquidity?: number | null
  launch_time?: number | null
  top10_holders_percentage?: number | null
  kyc_holder_count?: number | null
  kol_holders?: number | null
  kol_holding_percent?: number | null
  pro_holders?: number | null
  pro_holding_percent?: number | null
  smart_money_holders?: number | null
  smart_money_holding_percent?: number | null
}

export interface BinanceWeb3TokenKlineResponse {
  source: string
  address: string
  platform: string
  interval: string
  items?: Array<BinanceWeb3TokenKlineItemResponse>
}

export interface BinanceWeb3TokenAuditResponse {
  source: string
  binance_chain_id: string
  contract_address: string
  has_result?: boolean
  is_supported?: boolean
  risk_level_enum?: string | null
  risk_level?: number | null
  buy_tax?: number | null
  sell_tax?: number | null
  is_verified?: boolean | null
  risk_items?: Array<{ [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }>
}

export interface BinanceBasisItemResponse {
  symbol?: string | null
  pair?: string | null
  contract_type?: string | null
  basis?: number | null
  basis_rate?: number | null
  annualized_basis_rate?: number | null
  futures_price?: number | null
  index_price?: number | null
  timestamp?: number | null
}

export interface BinanceBasisResponse {
  exchange: string
  market: string
  items?: Array<BinanceBasisItemResponse>
}

export interface BinanceBreakoutMonitorItemResponse {
  market: string
  market_label: string
  symbol: string
  last_price?: number | null
  mark_price?: number | null
  price_change_pct?: number | null
  quote_volume?: number | null
  funding_rate_pct?: number | null
  change_15m_pct?: number | null
  change_1h_pct?: number | null
  change_4h_pct?: number | null
  pullback_from_high_pct?: number | null
  range_position_pct?: number | null
  ema20_gap_15m_pct?: number | null
  ema20_gap_1h_pct?: number | null
  rsi_15m?: number | null
  rsi_1h?: number | null
  macd_hist_15m?: number | null
  green_ratio_15m_pct?: number | null
  natural_score?: number
  momentum_score?: number
  structure_ok?: boolean
  momentum_ok?: boolean
  follow_status?: string
  verdict?: string
  reasons?: Array<string>
}

export interface BinanceBreakoutMonitorResponse {
  exchange: string
  min_rise_pct: number
  quote_asset: string
  updated_at: number
  summary?: BinanceBreakoutMonitorSummaryResponse
  items?: Array<BinanceBreakoutMonitorItemResponse>
}

export interface BinanceBreakoutMonitorSummaryResponse {
  monitored_count?: number
  natural_count?: number
  momentum_count?: number
  focus_count?: number
  advancing_count?: number
  spot_count?: number
  contract_count?: number
}

export interface BinanceContractBoardItemResponse {
  market?: string
  market_label?: string
  symbol?: string | null
  price_change_pct?: number | null
  last_price?: number | null
  quote_volume?: number | null
  mark_price?: number | null
  index_price?: number | null
  funding_rate_pct?: number | null
  open_interest?: number | null
  open_interest_value?: number | null
  oi_change_1h_pct?: number | null
  oi_change_4h_pct?: number | null
  oi_change_24h_pct?: number | null
}

export interface BinanceContractBoardResponse {
  exchange: string
  market: string
  items?: Array<BinanceContractBoardItemResponse>
}

export interface BinanceForceOrderItemResponse {
  symbol?: string | null
  side?: string | null
  price?: number | null
  avg_price?: number | null
  orig_qty?: number | null
  executed_qty?: number | null
  cum_quote?: number | null
  status?: string | null
  time?: number | null
  update_time?: number | null
}

export interface BinanceForceOrderResponse {
  exchange: string
  market: string
  items?: Array<BinanceForceOrderItemResponse>
}

export interface BinanceMarketPageRefreshStatusResponse {
  snapshot_ready?: boolean
  boards_ready?: boolean
  monitor_ready?: boolean
  refreshing?: boolean
  oi_ready_count?: number
  oi_requested_count?: number
  last_refresh_started_at?: number | null
  last_refresh_completed_at?: number | null
  last_refresh_error?: string | null
}

export interface BinanceOpenInterestStatItemResponse {
  symbol?: string | null
  pair?: string | null
  contract_type?: string | null
  sum_open_interest?: number | null
  sum_open_interest_value?: number | null
  timestamp?: number | null
}

export interface BinanceOpenInterestStatsResponse {
  exchange: string
  market: string
  items?: Array<BinanceOpenInterestStatItemResponse>
}

export interface BinanceRatioItemResponse {
  symbol?: string | null
  pair?: string | null
  long_short_ratio?: number | null
  long_account?: number | null
  short_account?: number | null
  long_position?: number | null
  short_position?: number | null
  timestamp?: number | null
}

export interface BinanceRatioSeriesResponse {
  exchange: string
  market: string
  items?: Array<BinanceRatioItemResponse>
}

export interface BinanceTakerVolumeItemResponse {
  symbol?: string | null
  pair?: string | null
  buy_sell_ratio?: number | null
  buy_vol?: number | null
  sell_vol?: number | null
  buy_vol_value?: number | null
  sell_vol_value?: number | null
  timestamp?: number | null
}

export interface BinanceTakerVolumeResponse {
  exchange: string
  market: string
  items?: Array<BinanceTakerVolumeItemResponse>
}

export interface BinanceTickerStatsItemResponse {
  symbol?: string | null
  price_change?: number | null
  price_change_pct?: number | null
  weighted_avg_price?: number | null
  last_price?: number | null
  last_qty?: number | null
  open_price?: number | null
  high_price?: number | null
  low_price?: number | null
  volume?: number | null
  quote_volume?: number | null
  open_time?: number | null
  close_time?: number | null
  count?: number | null
}

export interface BinanceTickerStatsResponse {
  exchange: string
  market: string
  items?: Array<BinanceTickerStatsItemResponse>
}

export interface BinanceWeb3AddressPnlItemResponse {
  address?: string | null
  address_label?: string | null
  address_logo?: string | null
  tags?: Array<string>
  realized_pnl?: number | null
  realized_pnl_pct?: number | null
  win_rate?: number | null
  total_volume?: number | null
  total_tx_cnt?: number | null
  total_traded_tokens?: number | null
  last_activity?: number | null
}

export interface BinanceWeb3HeatRankItemResponse {
  rank?: number | null
  symbol?: string | null
  chain_id?: string | null
  contract_address?: string | null
  icon_url?: string | null
  platform?: string | null
  heat_score?: number
  ranks?: { [key: string]: number }
  components?: { [key: string]: number }
  penalties?: { [key: string]: number }
  metrics?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  audit_info?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  sentiment?: string | null
  summary?: string | null
}

export interface BinanceWeb3HeatRankResponse {
  source: string
  leaderboard: string
  chain_id: string
  size: number
  items?: Array<BinanceWeb3HeatRankItemResponse>
  formula?: { [key: string]: Array<string> }
}

export interface BinanceWeb3TokenKlineItemResponse {
  open_time?: number | null
  open?: number | null
  high?: number | null
  low?: number | null
  close?: number | null
  volume?: number | null
  trade_count?: number | null
}

export interface CurrentPriceBatchItemResponse {
  symbol: string
  timeframe: string
  timestamp: string
  current_price: number | null
  source: string
}

export interface IndicatorHistoryPoint {
  date: string
  value: number
}

export interface IndicatorSummaryResponse {
  ema: number | null
  rsi: number | null
  macd: MACDResponse | null
  atr: number | null
  atr_pct?: number | null
  realized_volatility_pct?: number | null
  annualized_volatility_pct?: number | null
}

export interface MACDResponse {
  dif: number | null
  dea: number | null
  histogram: number | null
}

export interface MarketHistoryBatchItemResponse {
  symbol: string
  items?: Array<OhlcvPointResponse>
  coverage?: MarketHistoryCoverageResponse
}

export interface MarketHistoryCoverageResponse {
  complete: boolean
  missing_ranges?: Array<MarketHistoryMissingRangeResponse>
}

export interface MarketHistoryMissingRangeResponse {
  start_ts: number
  end_ts: number
}

export interface OhlcvPointResponse {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface TradeSetupResponseItem {
  side: string
  entry: number
  target: number
  stop: number
  risk_reward: number
  confidence: number
  risk_amount: number
  entry_time: number
  style: string
  strategy: string
  source: string
}

export interface GetBinanceMarketContractDetailQueryParams {
  symbol: string
  period?: string
  limit?: number
}

export interface GetBinanceMarketKlinesQueryParams {
  symbol: string
  market?: string
  interval?: string
  limit?: number
  start_time?: number | null
  end_time?: number | null
}

export interface GetBinanceMarketPageQueryParams {
  min_rise_pct?: number
  limit?: number
  quote_asset?: string
}

export interface GetBinanceWeb3AddressPnlRankQueryParams {
  chain_id: string
  period?: string
  tag?: string
  page_no?: number
  page_size?: number
}

export interface GetBinanceWeb3HeatRankBoardsQueryParams {
  chain_id?: string | null
  size?: number
}

export interface GetBinanceWeb3TokenAuditQueryParams {
  binance_chain_id: string
  contract_address: string
}

export interface GetBinanceWeb3TokenDynamicQueryParams {
  chain_id: string
  contract_address: string
}

export interface GetBinanceWeb3TokenKlineQueryParams {
  address: string
  platform: string
  interval?: string
  limit?: number
  from_time?: number | null
  to_time?: number | null
  pm?: string | null
}

export interface GetCurrentPriceBatchQueryParams {
  symbols: Array<string>
  timeframe?: string
}

export interface GetCurrentPriceQueryParams {
  symbol: string
  timeframe?: string
}

export interface GetIndexHistoryQueryParams {
  symbol: string
  timeframe?: string
  start_date?: string
  end_date?: string | null
}

export interface GetIndexPricingHistoryQueryParams {
  symbol: string
  timeframe?: string
  start_date?: string
  end_date?: string | null
}

export interface GetKlineTailQueryParams {
  symbol: string
  timeframe: string
  limit?: number
}

export interface GetLatestKlinesQueryParams {
  symbol: string
  timeframe: string
  limit?: number
}

export interface GetMarketFullHistoryBatchQueryParams {
  symbols: Array<string>
  timeframe?: string
  start_date?: string
  fetch_policy?: "cache_only" | "hydrate"
}

export interface GetMarketFullHistoryQueryParams {
  symbol: string
  timeframe?: string
  start_date?: string
  fetch_policy?: "cache_only" | "hydrate"
}

export interface GetMarketHistoryQueryParams {
  symbol: string
  timeframe: string
  end_ts: number
  limit?: number
}

export interface GetMarketIndicatorsQueryParams {
  category?: string | null
  days?: number
}

export interface GetRealtimeAnalysisQueryParams {
  symbol: string
  timeframe?: string | null
  limit?: number | null
}

export interface GetTradeSetupQueryParams {
  symbol: string
  timeframe?: string
  limit?: number
  account_size?: number
  style?: string
  strategy?: string
  mode?: string
}
