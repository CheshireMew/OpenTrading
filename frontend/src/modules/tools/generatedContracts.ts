// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

export interface ToolsPageContractResponse {
  dca_defaults: SimulateDcaCommand
  dca_strategies: Array<"standard" | "ema_deviation" | "rsi_dynamic" | "ahr999" | "fear_greed" | "value_averaging">
  dca_multiplier_default: number
  dca_max_days: number
  compare_defaults: ComparePairsCommand
}

export interface DCAResponse {
  symbol: string
  asset_class?: string | null
  price_basis?: string | null
  execution_price_basis?: "hour_open" | "daily_close"
  pricing_symbol?: string | null
  pricing_name?: string | null
  pricing_currency?: string | null
  data_quality: "exchange" | "synthetic_and_exchange_proxy" | "index_proxy"
  start_date: string
  end_date: string
  target_time: string
  total_days: number
  total_invested: number
  final_value: number
  total_coins: number
  roi: number
  average_cost: number
  profit_loss: number
  current_price: number
  history: Array<DCAHistoryPointResponse>
  profit_pct?: number | null
}

export interface SimulateDcaCommand {
  symbol?: string
  amount?: number
  start_date?: string | null
  investment_time?: string
  timezone?: string
  days?: number | null
  strategy?: "standard" | "ema_deviation" | "rsi_dynamic" | "ahr999" | "fear_greed" | "value_averaging"
  strategy_params?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface PairCompareToolResponse {
  symbol_a: string
  symbol_b: string
  data_a: Array<ToolCandlestickPointResponse>
  data_b: Array<ToolCandlestickPointResponse>
  ratio_ohlc: Array<ToolCandlestickPointResponse>
  ratio_symbol: string
  ratio_price_basis: "close"
  timeframe?: string | null
  relative_strength?: number | null
  statistics: PairCompareStatisticsResponse
}

export interface ComparePairsCommand {
  symbol_a?: string
  symbol_b?: string
  days?: number
  timeframe?: string
}

export interface DCAHistoryPointResponse {
  date: string
  price: number
  invested: number
  value: number
  coins: number
  roi: number
  avg_cost: number
}

export interface PairCompareStatisticsResponse {
  aligned_points: number
  symbol_a_return_pct?: number | null
  symbol_b_return_pct?: number | null
  excess_return_pct?: number | null
  return_correlation?: number | null
  ratio_change_pct?: number | null
}

export interface ToolCandlestickPointResponse {
  time: number
  open: number
  high: number
  low: number
  close: number
}
