// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

export interface BacktestPreviewResponse {
  preview_id: string
  fingerprint: string
  strategy_key: string
  strategy_name: string
  strategy_version: number
  strategy_template: string
  timeframe: string
  symbols: Array<string>
  start_date: string
  end_date: string
  candles?: { [key: string]: Array<OhlcvPointResponse> }
  markers?: { [key: string]: Array<StrategyPreviewMarkerResponse> }
  indicator_series?: { [key: string]: Array<StrategyPreviewIndicatorSeriesResponse> }
  coverage?: { [key: string]: MarketHistoryCoverageResponse }
  diagnostics?: Array<StrategyPreviewDiagnosticResponse>
}

export interface BacktestPreviewCommand {
  strategy_key?: string
  strategy_version?: number | null
  timeframe?: string
  start_date?: string
  end_date?: string
  initial_cash?: number
  fee_rate?: number
  portfolio?: BacktestPortfolioConfig
  research?: BacktestResearchConfig
}

export interface BacktestStartResponse {
  success: boolean
  backtest_id: number
  message: string
}

export interface BacktestStartCommand {
  strategy_key?: string
  strategy_version?: number | null
  timeframe?: string
  start_date?: string
  end_date?: string
  initial_cash?: number
  fee_rate?: number
  portfolio?: BacktestPortfolioConfig
  research?: BacktestResearchConfig
  preview_id: string
  approved_fingerprint: string
}

export interface PaperStartResponse {
  success: boolean
  run_id: number
  message: string
}

export interface PaperStartCommand {
  strategy_key?: string
  strategy_version?: number | null
  timeframe?: string
  initial_cash?: number
  fee_rate?: number
  portfolio?: BacktestPortfolioConfig
}

export interface PaperStopResponse {
  success: boolean
  run_id: number
  message: string
}

export interface BacktestDeleteResponse {
  success: boolean
  run_id: number
  message: string
}

export interface StrategyDefinitionResponse {
  key: string
  name: string
  template: string
  category: string
  description?: string | null
  is_active: boolean
  template_runtime?: StrategyTemplateRuntimeResponse
  versions: Array<StrategyVersionResponse>
}

export interface StrategyTemplateResponse {
  template: string
  name: string
  category: string
  description?: string | null
  is_builtin?: boolean
  template_runtime?: StrategyTemplateRuntimeResponse
  indicator_keys?: Array<string>
  indicator_registry: Array<StrategyIndicatorRegistryResponse>
  operators: Array<StrategyOperatorResponse>
  group_logics: Array<StrategyGroupLogicResponse>
  default_config: StrategyTemplateConfigResponse
  default_parameter_space: { [key: string]: Array<string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null> }
}

export interface StrategyEditorContractResponse {
  operators: Array<StrategyOperatorResponse>
  group_logics: Array<StrategyGroupLogicResponse>
  timeframe_options: Array<StrategyOperatorResponse>
  market_type_options: Array<StrategyOperatorResponse>
  direction_options: Array<StrategyOperatorResponse>
  blank_condition: StrategyConditionNodeResponse
  blank_group: StrategyGroupNodeResponse
  blank_config: StrategyTemplateConfigResponse
  run_defaults: BacktestRunDefaultsResponse
}

export interface CreateStrategyTemplateCommand {
  key: string
  name: string
  category: string
  description?: string | null
  indicator_keys?: Array<string>
  default_config: StrategyTemplateConfigResponse
  default_parameter_space?: { [key: string]: Array<string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null> }
}

export interface StrategyIndicatorRegistryResponse {
  key: string
  engine: string
  name: string
  description?: string | null
  outputs: Array<StrategyIndicatorOutputResponse>
  params: Array<StrategyIndicatorParamResponse>
  is_builtin: boolean
}

export interface StrategyIndicatorEngineResponse {
  key: string
  engine: string
  name: string
  description?: string | null
  outputs: Array<StrategyIndicatorOutputResponse>
  params: Array<StrategyIndicatorParamResponse>
}

export interface CreateIndicatorDefinitionCommand {
  key: string
  name: string
  engine_key: string
  description?: string | null
  params?: Array<StrategyIndicatorParamResponse>
}

export interface StrategyVersionResponse {
  id: number | null
  version: number
  name: string
  notes?: string | null
  is_default: boolean
  config: StrategyTemplateConfigResponse
  parameter_space: { [key: string]: Array<string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null> }
  runtime: StrategyRunProfileResponse
}

export interface CreateStrategyVersionCommand {
  key: string
  name: string
  template: string
  category: string
  description?: string | null
  config: StrategyTemplateConfigResponse
  parameter_space?: { [key: string]: Array<string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null> }
  notes?: string | null
  make_default?: boolean
}

export interface StrategyEvolutionResponse {
  source_backtest_id: number
  strategy_key: string
  source_version?: number | null
  created: boolean
  message: string
  defects?: Array<StrategyEvolutionDefectResponse>
  changes?: Array<StrategyEvolutionChangeResponse>
  evolved_version?: StrategyVersionResponse | null
  base_config: StrategyTemplateConfigResponse
  evolved_config: StrategyTemplateConfigResponse
}

export interface EvolveStrategyFromBacktestCommand {
  backtest_id?: number | null
  version_name?: string | null
  notes?: string | null
  make_default?: boolean
  dry_run?: boolean
}

export interface BacktestRunResponse {
  id: number
  symbol: string
  timeframe: string
  start_date: string | null
  end_date: string | null
  status: string
  metadata?: BacktestExecutionMetadataResponse | PaperLiveExecutionMetadataResponse | null
  report?: BacktestReportResponse | null
  created_at: string | null
  metrics: BacktestMetricsResponse
  signals?: Array<BacktestSignalResponse> | null
}

export interface BacktestDetailResponse {
  id: number
  symbol: string
  timeframe: string
  start_date: string | null
  end_date: string | null
  status: string
  metadata?: BacktestExecutionMetadataResponse | PaperLiveExecutionMetadataResponse | null
  report?: BacktestReportResponse | null
  created_at: string | null
  metrics: BacktestMetricsResponse
  signals: Array<BacktestSignalResponse>
  trades: Array<BacktestTradeResponse>
  equity_curve: Array<BacktestEquityPointResponse>
  pagination: PaginationResponse
}

export interface BacktestDateRangeResponse {
  start: string
  end: string
}

export interface BacktestEquityPointResponse {
  timestamp: string | null
  equity: number
  pnl_abs: number
  drawdown_pct: number
  id: number
}

export interface BacktestExecutionMetadataResponse {
  schema_version?: number | null
  execution_model?: string | null
  engine?: string | null
  exchange?: string | null
  market_type?: string | null
  direction?: string | null
  strategy_key?: string | null
  strategy_name?: string | null
  strategy_version?: number | null
  strategy_template?: string | null
  strategy_notes?: string | null
  symbols?: Array<string>
  execution_symbols?: Array<string>
  price_source?: string | null
  portfolio_label?: string | null
  initial_cash?: number | null
  fee_rate?: number | null
  fee_ratio?: number | null
  timeframe?: string | null
  stake_currency?: string | null
  portfolio?: BacktestPortfolioConfig | null
  selected_config?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  raw_stats?: BacktestReportSnapshotResponse | null
  error?: string | null
  preview?: BacktestPreviewApprovalResponse | null
  execution_mode: "backtest"
  research?: BacktestResearchReportResponse | BacktestResearchConfig | null
  sample_ranges?: BacktestSampleRangesResponse | null
  report?: BacktestReportResponse | null
  factor_research?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface BacktestIterationSummaryResponse {
  range?: BacktestDateRangeResponse | null
  config: StrategyTemplateConfigResponse
  report?: BacktestReportSnapshotResponse | null
}

export interface BacktestMetricsResponse {
  total_candles: number
  total_signals: number
  buy_signals: number
  sell_signals: number
  hold_signals: number
}

export interface BacktestOptimizationSummaryResponse {
  metric: string
  trial_count: number
  best_score?: number | null
  best_config?: StrategyTemplateConfigResponse | null
  trials?: Array<BacktestOptimizationTrialResponse>
}

export interface BacktestOptimizationTrialResponse {
  trial: number
  score?: number | null
  config: StrategyTemplateConfigResponse
  report?: BacktestReportSnapshotResponse | null
}

export interface BacktestPairBreakdownResponse {
  pair: string
  trades: number
  profit_abs: number
  profit_pct: number
  win_rate: number
}

export interface BacktestPaperLiveResponse {
  cash_balance: number
  open_positions: number
  positions?: Array<BacktestPaperPositionResponse>
  last_updated: string
  stop_reason?: string | null
}

export interface BacktestPaperPositionResponse {
  symbol: string
  side?: string
  opened_at: string
  entry_price: number
  entry_score?: number | null
  remaining_amount: number
  remaining_cost: number
  highest_price: number
  lowest_price: number
  last_price: number
  taken_partial_ids?: Array<string>
}

export interface BacktestPortfolioConfig {
  symbols?: Array<string>
  max_open_trades?: number
  position_size_pct?: number
  stake_mode?: "fixed" | "unlimited"
}

export interface BacktestPortfolioSummaryResponse {
  symbols?: Array<string>
  max_open_trades?: number
  position_size_pct?: number
  stake_mode?: "fixed" | "unlimited"
  stake_currency?: string | null
}

export interface BacktestPreviewApprovalResponse {
  id: string
  fingerprint: string
  strategy_key?: string | null
  strategy_version?: number | null
  timeframe?: string | null
  symbols?: Array<string>
  markers?: { [key: string]: Array<{ [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }> }
  diagnostics?: Array<{ [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }>
}

export interface BacktestReportResponse {
  initial_cash: number
  final_balance: number
  profit_abs: number
  profit_pct: number
  annualized_return_pct?: number | null
  max_drawdown_pct: number
  sharpe?: number | null
  sortino?: number | null
  calmar?: number | null
  profit_factor?: number | null
  expectancy_ratio?: number | null
  win_rate: number
  total_trades: number
  wins: number
  losses: number
  draws: number
  avg_trade_pct?: number | null
  avg_trade_duration_minutes?: number | null
  best_trade_pct?: number | null
  worst_trade_pct?: number | null
  pair_breakdown?: Array<BacktestPairBreakdownResponse>
  symbols?: Array<string>
  timeframe?: string | null
  strategy?: BacktestStrategySummaryResponse | null
  portfolio?: BacktestPortfolioSummaryResponse | null
  research?: BacktestResearchReportResponse | null
}

export interface BacktestReportSnapshotResponse {
  profit_pct?: number | null
  profit_abs?: number | null
  final_balance?: number | null
  max_drawdown_pct?: number | null
  sharpe?: number | null
  calmar?: number | null
  profit_factor?: number | null
  win_rate?: number | null
  total_trades?: number | null
}

export interface BacktestResearchConfig {
  slippage_bps?: number
  funding_rate_daily?: number
  in_sample_ratio?: number
  optimize_metric?: "sharpe" | "profit_pct" | "calmar" | "profit_factor"
  optimize_trials?: number
  rolling_windows?: number
}

export interface BacktestResearchReportResponse {
  selected_config?: StrategyTemplateConfigResponse | null
  in_sample_ratio: number
  slippage_bps: number
  funding_rate_daily: number
  optimization?: BacktestOptimizationSummaryResponse | null
  in_sample?: BacktestIterationSummaryResponse | null
  out_of_sample?: BacktestIterationSummaryResponse | null
  rolling_windows?: Array<BacktestRollingWindowResponse>
}

export interface BacktestRollingWindowResponse {
  index: number
  train?: BacktestDateRangeResponse | null
  test: BacktestDateRangeResponse
  config: StrategyTemplateConfigResponse
  optimization?: BacktestOptimizationSummaryResponse | null
  report?: BacktestReportSnapshotResponse | null
}

export interface BacktestRunDefaultsResponse {
  strategy_key?: string
  timeframe?: string
  start_date?: string
  end_date?: string
  initial_cash?: number
  fee_rate?: number
  portfolio?: BacktestPortfolioConfig
  research?: BacktestResearchConfig
  history_mode?: "backtest" | "paper"
  optimize_metric_options?: Array<StrategyOperatorResponse>
}

export interface BacktestRuntimeStateResponse {
  cash_balance: number
  last_processed?: { [key: string]: number | null }
  last_synced_end?: number | null
  positions?: { [key: string]: BacktestPaperPositionResponse }
  held_bars?: number
}

export interface BacktestSampleRangesResponse {
  requested?: BacktestDateRangeResponse | null
  displayed?: BacktestDateRangeResponse | null
  in_sample?: BacktestDateRangeResponse | null
  out_of_sample?: BacktestDateRangeResponse | null
}

export interface BacktestSignalResponse {
  id: number
  timestamp: string | null
  price: number
  signal: string
  confidence: number
  indicators?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null } | null
  reasoning?: string | null
}

export interface BacktestStrategySummaryResponse {
  key: string
  name: string
  version: number
  template: string
}

export interface BacktestTradeResponse {
  opened_at: string | null
  closed_at: string | null
  entry_price: number
  exit_price: number | null
  stake_amount: number
  amount: number
  profit_abs: number
  profit_pct: number
  max_drawdown_pct?: number | null
  duration_minutes?: number | null
  entry_tag?: string | null
  exit_reason?: string | null
  leverage?: number
  pair: string
  side?: string
  id: number
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

export interface PaginationResponse {
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface PaperLiveExecutionMetadataResponse {
  schema_version?: number | null
  execution_model?: string | null
  engine?: string | null
  exchange?: string | null
  market_type?: string | null
  direction?: string | null
  strategy_key?: string | null
  strategy_name?: string | null
  strategy_version?: number | null
  strategy_template?: string | null
  strategy_notes?: string | null
  symbols?: Array<string>
  execution_symbols?: Array<string>
  price_source?: string | null
  portfolio_label?: string | null
  initial_cash?: number | null
  fee_rate?: number | null
  fee_ratio?: number | null
  timeframe?: string | null
  stake_currency?: string | null
  portfolio?: BacktestPortfolioConfig | null
  selected_config?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  raw_stats?: BacktestReportSnapshotResponse | null
  error?: string | null
  preview?: BacktestPreviewApprovalResponse | null
  execution_mode: "paper_live"
  runtime_state?: BacktestRuntimeStateResponse | null
  paper_live?: BacktestPaperLiveResponse | null
  report?: BacktestReportResponse | null
  factor_research?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface StrategyConditionNodeResponse {
  id: string
  node_type: "condition"
  label: string
  left: StrategyPriceSourceResponse | StrategyIndicatorSourceResponse | StrategyValueSourceResponse | StrategyIndicatorMultiplierSourceResponse | StrategyIndicatorOffsetSourceResponse
  operator: "gt" | "gte" | "lt" | "lte"
  right: StrategyPriceSourceResponse | StrategyIndicatorSourceResponse | StrategyValueSourceResponse | StrategyIndicatorMultiplierSourceResponse | StrategyIndicatorOffsetSourceResponse
  enabled?: boolean
}

export interface StrategyEvolutionChangeResponse {
  path: string
  before?: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null
  after?: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null
  reason: string
}

export interface StrategyEvolutionDefectResponse {
  key: string
  severity: "info" | "warning" | "critical"
  title: string
  evidence?: Array<string>
  recommendation: string
}

export interface StrategyExecutionConfigResponse {
  market_type?: "spot" | "futures"
  direction?: "long_only" | "long_short"
}

export interface StrategyGroupLogicResponse {
  key: string
  label: string
}

export interface StrategyGroupNodeResponse {
  id: string
  node_type: "group"
  label: string
  logic: "and" | "or"
  enabled?: boolean
  children?: Array<StrategyConditionNodeResponse | StrategyGroupNodeResponse>
}

export interface StrategyIndicatorConfigResponse {
  label: string
  type: string
  timeframe?: string
  params?: { [key: string]: number | boolean }
}

export interface StrategyIndicatorMultiplierSourceResponse {
  kind: "indicator_multiplier"
  indicator: string
  output?: string
  multiplier?: number
  bars_ago?: number
}

export interface StrategyIndicatorOffsetSourceResponse {
  kind: "indicator_offset"
  base_indicator: string
  base_output?: string
  offset_indicator: string
  offset_output?: string
  offset_multiplier?: number
  bars_ago?: number
}

export interface StrategyIndicatorOutputResponse {
  key: string
  label: string
}

export interface StrategyIndicatorParamResponse {
  key: string
  label: string
  type: "int" | "float" | "bool"
  default: number | boolean
  min?: number | null
  max?: number | null
  step?: number | null
}

export interface StrategyIndicatorSourceResponse {
  kind: "indicator"
  indicator: string
  output?: string
  bars_ago?: number
}

export interface StrategyOperatorResponse {
  key: string
  label: string
}

export interface StrategyPartialExitResponse {
  id: string
  profit: number
  size_pct: number
  enabled?: boolean
}

export interface StrategyPreviewDiagnosticResponse {
  severity: "info" | "warning" | "critical"
  title: string
  message: string
}

export interface StrategyPreviewIndicatorPointResponse {
  time: number
  value: number
}

export interface StrategyPreviewIndicatorSeriesResponse {
  symbol: string
  indicator_id: string
  output: string
  label: string
  points?: Array<StrategyPreviewIndicatorPointResponse>
}

export interface StrategyPreviewMarkerResponse {
  symbol: string
  time: number
  price: number
  kind: "long_entry" | "long_exit" | "short_entry" | "short_exit"
  side: "long" | "short"
  label: string
  active_regime?: string | null
  indicators?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface StrategyPriceSourceResponse {
  kind: "price"
  field?: "open" | "high" | "low" | "close" | "volume"
  bars_ago?: number
}

export interface StrategyRiskConfigResponse {
  stoploss: number
  roi_targets?: Array<StrategyRoiTargetResponse>
  trailing: StrategyTrailingConfigResponse
  partial_exits?: Array<StrategyPartialExitResponse>
  trade_plan?: StrategyTradePlanConfigResponse
}

export interface StrategyRoiTargetResponse {
  id: string
  minutes: number
  profit: number
  enabled?: boolean
}

export interface StrategyRunProfileResponse {
  indicator_timeframes?: Array<string>
  allowed_run_timeframes?: Array<string>
  preferred_run_timeframe: string
}

export interface StrategyStateBranchResponse {
  id: string
  label: string
  enabled?: boolean
  regime: StrategyGroupNodeResponse
  long_entry: StrategyGroupNodeResponse
  long_exit: StrategyGroupNodeResponse
  short_entry: StrategyGroupNodeResponse
  short_exit: StrategyGroupNodeResponse
}

export interface StrategyTemplateCapabilitiesResponse {
  paper?: boolean
  version_editing?: boolean
}

export interface StrategyTemplateConfigResponse {
  indicators?: { [key: string]: StrategyIndicatorConfigResponse }
  execution: StrategyExecutionConfigResponse
  regime_priority?: Array<"trend" | "range">
  trend: StrategyStateBranchResponse
  range: StrategyStateBranchResponse
  risk: StrategyRiskConfigResponse
}

export interface StrategyTemplateRuntimeResponse {
  builder_kind?: string
  capabilities?: StrategyTemplateCapabilitiesResponse
}

export interface StrategyTradePlanConfigResponse {
  enabled?: boolean
  stop_multiplier?: number
  min_stop_pct?: number
  reward_multiplier?: number
  atr_indicator?: string
  support_indicator?: string
  resistance_indicator?: string
}

export interface StrategyTrailingConfigResponse {
  enabled?: boolean
  positive: number
  offset: number
  only_offset_reached?: boolean
}

export interface StrategyValueSourceResponse {
  kind: "value"
  value: number
  bars_ago?: number
}

export interface GetBacktestQueryParams {
  page?: number
  page_size?: number
}

export interface GetPaperRunQueryParams {
  page?: number
  page_size?: number
}
