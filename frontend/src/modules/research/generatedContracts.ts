// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

export interface ResearchReportPageResponse {
  items?: Array<ResearchReportResponse>
  total: number
}

export interface ResearchReportResponse {
  id: string
  title: string
  reportType: string
  symbol?: string | null
  portfolioId?: string | null
  contentMarkdown: string
  dataSnapshot?: { [key: string]: unknown }
  version: number
  archivedAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface ResearchReportGenerateCommand {
  title: string
  reportType?: "daily_brief" | "weekly_brief" | "asset_review" | "portfolio_review" | "decision_review"
  symbol?: string | null
  portfolioId?: string | null
}

export interface ResearchArchiveCommand {
  expectedVersion: number
}

export interface SavedMarketScreenerListResponse {
  items?: Array<SavedMarketScreenerResponse>
}

export interface SavedMarketScreenerResponse {
  id: string
  name: string
  description: string
  filters: MarketScreenerFilters
  version: number
  archivedAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface SavedMarketScreenerCreateCommand {
  name: string
  description?: string
  filters: MarketScreenerFilters
}

export interface SavedMarketScreenerUpdateCommand {
  name: string
  description?: string
  filters: MarketScreenerFilters
  expectedVersion: number
}

export interface MarketScreenerRunResponse {
  id: string
  screenerId: string
  filters: MarketScreenerFilters
  resultItems?: Array<{ [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }>
  resultCount: number
  snapshotAsOf: string
  evaluatedAt: string
  historicalReplay?: boolean
}

export interface MarketScreenerRunCommand {
  asOf?: string | null
}

export interface MarketScreenerRunPageResponse {
  items?: Array<MarketScreenerRunResponse>
  total: number
}

export interface AssetResearchResponse {
  symbol: string
  assetClass: "crypto" | "index" | "cash" | "web3"
  timeframe: string
  currentPrice?: number | null
  updatedAt: string
  indicators?: IndicatorSummaryResponse | null
  history?: Array<OhlcvPointResponse>
  marketContext?: { [key: string]: unknown }
  watchItems?: Array<ResearchWatchItemResponse>
  notes?: Array<ResearchNoteResponse>
  alerts?: Array<ResearchAlertResponse>
  events?: Array<ResearchEventResponse>
  signals?: Array<TradeSignalResponse>
  issues?: Array<string>
}

export interface TradeSignalPageResponse {
  items?: Array<TradeSignalResponse>
  total: number
  offset: number
  limit: number
}

export interface TradeSignalStatsResponse {
  overall: TradeSignalStatGroupResponse
  bySource?: Array<TradeSignalStatGroupResponse>
  byStrategy?: Array<TradeSignalStatGroupResponse>
  confidenceCalibration?: Array<TradeSignalConfidenceBucketResponse>
}

export interface TradeSignalEvaluationRunResponse {
  evaluatedAt: string
  candidateCount: number
  evaluatedCount: number
  resolvedCount: number
  unavailableCount: number
}

export interface TradeSignalEvaluationCommand {
  signalId?: string | null
  force?: boolean
}

export interface TradeSignalResponse {
  id: string
  symbol: string
  timeframe: string
  source: string
  mode: string
  signalStatus: string
  side?: string | null
  entry?: number | null
  target?: number | null
  stop?: number | null
  riskReward?: number | null
  confidence?: number | null
  riskAmount?: number | null
  style?: string | null
  strategy?: string | null
  reason: string
  errorCode?: string | null
  currentPrice?: number | null
  entryTime?: number | null
  marketSnapshot?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  outcomeStatus: "pending" | "target_hit" | "stop_hit" | "ambiguous" | "expired" | "unavailable"
  outcomePrice?: number | null
  targetHitAt?: string | null
  stopHitAt?: string | null
  mfePct?: number | null
  maePct?: number | null
  forwardReturns?: { [key: string]: number | null }
  evaluatedAt?: string | null
  expiresAt?: string | null
  version: number
  archivedAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface ResearchAlertEvaluationResponse {
  evaluatedAt: string
  ruleCount: number
  evaluatedCount: number
  triggeredCount: number
  unavailableCount: number
}

export interface ResearchAlertEvaluateCommand {
  force?: boolean
}

export interface ResearchWorkbenchResponse {
  watchlists?: Array<ResearchWatchlistResponse>
  items?: Array<ResearchWatchItemResponse>
  notes?: Array<ResearchNoteResponse>
  alerts?: Array<ResearchAlertResponse>
  events?: Array<ResearchEventResponse>
  unacknowledgedEventCount: number
}

export interface ResearchEventPageResponse {
  items?: Array<ResearchEventResponse>
  total: number
}

export interface ResearchWatchlistResponse {
  id: string
  name: string
  description: string
  position: number
  version: number
  archivedAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface ResearchWatchlistCreateCommand {
  name: string
  description?: string
}

export interface ResearchWatchlistUpdateCommand {
  name: string
  description?: string
  expectedVersion: number
}

export interface ResearchWatchItemResponse {
  id: string
  watchlistId: string
  symbol: string
  assetClass: "crypto" | "index" | "cash" | "web3"
  displayName: string
  thesis: string
  targetPrice?: number | null
  invalidationPrice?: number | null
  tags?: Array<string>
  sourceContext?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  position: number
  version: number
  archivedAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface ResearchWatchItemCreateCommand {
  watchlistId: string
  symbol: string
  assetClass?: "crypto" | "index" | "cash" | "web3"
  displayName?: string
  thesis?: string
  targetPrice?: number | null
  invalidationPrice?: number | null
  tags?: Array<string>
  sourceContext?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface ResearchWatchItemUpdateCommand {
  watchlistId: string
  symbol: string
  assetClass?: "crypto" | "index" | "cash" | "web3"
  displayName?: string
  thesis?: string
  targetPrice?: number | null
  invalidationPrice?: number | null
  tags?: Array<string>
  sourceContext?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  expectedVersion: number
}

export interface ResearchNoteResponse {
  id: string
  watchItemId?: string | null
  symbol: string
  kind: "thesis" | "update" | "review" | "decision"
  title: string
  content: string
  snapshot?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  version: number
  occurredAt: string
  archivedAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface ResearchNoteCreateCommand {
  watchItemId?: string | null
  symbol: string
  kind?: "thesis" | "update" | "review" | "decision"
  title: string
  content?: string
  snapshot?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  occurredAt?: string | null
}

export interface ResearchNoteUpdateCommand {
  watchItemId?: string | null
  symbol: string
  kind?: "thesis" | "update" | "review" | "decision"
  title: string
  content?: string
  snapshot?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  occurredAt?: string | null
  expectedVersion: number
}

export interface ResearchAlertResponse {
  id: string
  watchItemId?: string | null
  symbol: string
  name: string
  metric: string
  operator: "gt" | "gte" | "lt" | "lte" | "crosses_above" | "crosses_below" | "between" | "outside"
  threshold: number
  secondaryThreshold?: number | null
  enabled: boolean
  cooldownMinutes: number
  notificationChannels?: Array<"in_app" | "windows">
  configuration?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  lastValue?: number | null
  lastEvaluatedAt?: string | null
  lastTriggeredAt?: string | null
  version: number
  archivedAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface ResearchAlertCreateCommand {
  watchItemId?: string | null
  symbol: string
  name: string
  metric: string
  operator: "gt" | "gte" | "lt" | "lte" | "crosses_above" | "crosses_below" | "between" | "outside"
  threshold: number
  secondaryThreshold?: number | null
  enabled?: boolean
  cooldownMinutes?: number
  notificationChannels?: Array<"in_app" | "windows">
  configuration?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface ResearchAlertUpdateCommand {
  watchItemId?: string | null
  symbol: string
  name: string
  metric: string
  operator: "gt" | "gte" | "lt" | "lte" | "crosses_above" | "crosses_below" | "between" | "outside"
  threshold: number
  secondaryThreshold?: number | null
  enabled?: boolean
  cooldownMinutes?: number
  notificationChannels?: Array<"in_app" | "windows">
  configuration?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  expectedVersion: number
}

export interface ResearchEventResponse {
  id: string
  entityType: string
  entityId?: string | null
  symbol?: string | null
  kind: string
  title: string
  body: string
  payload?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  occurredAt: string
  acknowledgedAt?: string | null
  createdAt: string
}

export interface ResearchEventAcknowledgeCommand {
  acknowledged?: boolean
}

export interface ResearchResultPage {
  items: Array<ResearchResultEntry>
  total: number
  offset: number
  mode: "historical" | "same_conditions"
  reference_id?: string | null
  note: string
}

export interface ResearchResultQuery {
  symbol?: string | null
  strategy?: string | null
  family?: string | null
  timeframe?: string | null
  start?: string | null
  end?: string | null
  execution_timeframe?: string | null
  intrabar_profit_protection?: boolean | null
  parameters?: { [key: string]: unknown }
  reference_id?: string | null
  sort?: "return_pct" | "win_rate" | "max_drawdown_pct" | "total_trades"
  descending?: boolean
  minimum_trades?: number
  include_archived?: boolean
  offset?: number
  limit?: number
}

export interface LocalBacktestPreview {
  config: { [key: string]: unknown }
  warmup_bars: number
  warmup_explanation: string
  rules_summary: Array<string>
  signal_data: DataCoverage
  execution_data?: DataCoverage | null
  comparable_intervals: Array<CachedInterval>
  warnings: Array<string>
}

export interface LocalBacktestCommand {
  strategy: string
  parameters?: { [key: string]: unknown }
  symbol?: string
  timeframe?: "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d"
  start: string
  end: string
  initial_cash?: number
  position_pct?: number
  data_gap_policy?: "reject" | "observed_bars"
  execution_timeframe?: "1m" | "5m" | "15m" | "30m" | "1h" | null
  intrabar_profit_protection?: boolean
  execution_gap_policy?: "reject" | "coarse_fallback"
}

export interface ResearchResultRefresh {
  native_runs: number
  scanned_files: number
  imported_references: number
  unchanged_files: number
  issues: Array<{ [key: string]: unknown }>
  index: string
  note: string
}

export interface ResearchResultImport {
  roots?: Array<string>
}

export interface ResearchResultEntry {
  id: string
  run_id?: string | null
  source_type: "native" | "legacy"
  label: string
  family?: string | null
  archived: boolean
  config: { [key: string]: unknown }
  report: { [key: string]: unknown }
  metadata: { [key: string]: unknown }
  missing: Array<string>
  cohort?: string | null
  execution_summary: { [key: string]: unknown }
  sources: Array<{ [key: string]: unknown }>
  context_note?: string | null
}

export interface LocalBacktestCatalog {
  strategies: Array<LocalBacktestStrategy>
  symbols: Array<string>
  timeframes: { [key: string]: Array<string> }
}

export interface ParameterSweepPreview {
  count: number
  new_runs: number
  reused_runs: number
  axes: { [key: string]: Array<unknown> }
  fixed_parameters: { [key: string]: unknown }
  warnings: Array<string>
  data_previews?: Array<SweepDataPreview>
  comparable_intervals?: Array<CachedInterval>
}

export interface ParameterSweepCommand {
  title: string
  base: LocalBacktestCommand
  axes?: { [key: string]: Array<unknown> | ParameterRange }
  source_run?: string | null
  parent?: string | null
  max_runs?: number
}

export interface ParameterSweepView {
  id: string
  title: string
  created_at: string
  status: string
  total: number
  counts: { [key: string]: number }
  progress: number
  request: ParameterSweepCommand
  axes: { [key: string]: Array<unknown> }
  warnings: Array<string>
  path: string
  items: Array<ParameterSweepItem>
  offset: number
  filtered_total: number
  strategy?: LocalBacktestStrategy | null
}

export interface ParameterSweepList {
  items: Array<{ [key: string]: unknown }>
  total: number
}

export interface ParameterSweepAction {
  action: "resume" | "cancel"
}

export interface ParameterSweepEffects {
  effects: Array<{ [key: string]: unknown }>
}

export interface LocalBacktestExport {
  filename: string
  content: string
  media_type: string
}

export interface LocalBacktestRun {
  id: string
  status: string
  progress: number
  created_at: string
  parent_id?: string | null
  archived?: boolean
  error?: string | null
  config: { [key: string]: unknown }
  metadata?: { [key: string]: unknown }
  report?: { [key: string]: unknown } | null
  execution_summary?: { [key: string]: unknown }
  progress_detail?: { [key: string]: unknown }
  resume_available?: boolean
}

export interface LocalBacktestRuns {
  items: Array<LocalBacktestRun>
  total: number
}

export interface BacktestDiagnosticSummary {
  run_id: string
  report: { [key: string]: unknown }
  trade_summary: { [key: string]: unknown }
  median_holding_minutes: number | null
  mean_holding_minutes: number | null
  top_10_gross_profit_share_pct: number | null
  groups: { [key: string]: { [key: string]: TradeGroupSummary } }
  basis: string
  equity_kind: "equity" | "execution_equity"
  available: boolean
  annual: Array<AccountPeriod>
  monthly: Array<AccountPeriod>
  drawdown: DrawdownSummary
  normalized: NormalizedTradeStats
  account_basis: string
}

export interface BacktestTradeChanges {
  comparison: ComparisonAssessment
  total: number
  offset: number
  items: Array<TradeChange>
  unchanged: number
  added: NormalizedTradeStats
  dropped: NormalizedTradeStats
  changed: number
  note: string
}

export interface BacktestTradeTimeline {
  run_id: string
  trade: { [key: string]: unknown }
  signals: Array<{ [key: string]: unknown }>
  fills: Array<{ [key: string]: unknown }>
  total: number
  offset: number
  items: Array<{ [key: string]: unknown }>
  lineage: "recorded_events" | "legacy_fills"
  fallback_intervals?: Array<number> | null
  limitations: Array<string>
  basis: string
}

export interface LocalBacktestRecords {
  items: Array<{ [key: string]: unknown }>
  total: number
  offset: number
}

export interface LocalBacktestAction {
}

export interface AccountPeriod {
  label: string
  start: number
  end: number
  start_equity: number
  end_equity: number
  return_pct: number | null
  start_mark_time: number
  end_mark_time: number
  partial: boolean
  boundary_carried: boolean
}

export interface CachedInterval {
  start_ms: number
  end_ms: number
}

export interface ComparisonAssessment {
  issues: Array<string>
  [key: string]: unknown
}

export interface DataCoverage {
  timeframe: string
  required_start_ms: number
  required_end_ms: number
  first_cached_ms: number | null
  last_cached_close_ms: number | null
  expected_bars: number
  cached_bars: number
  missing_bars: number
  complete_intervals: Array<CachedInterval>
}

export interface DrawdownEpisode {
  peak_time: number
  peak_equity: number
  trough_time: number
  trough_equity: number
  drawdown_pct: number
  recovery_time: number | null
  end_time: number
  recovered: boolean
  duration_ms: number
  recovery_duration_ms: number | null
}

export interface DrawdownSummary {
  total_episodes?: number
  max_drawdown?: DrawdownEpisode | null
  longest?: DrawdownEpisode | null
  unrecovered?: DrawdownEpisode | null
  worst_episodes?: Array<DrawdownEpisode>
  basis?: string
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

export interface LocalBacktestParameter {
  type: "int" | "float" | "bool" | "str"
  default: unknown
  min?: number | null
  max?: number | null
  label?: string
  options?: Array<ParameterOption>
  unit?: string
  enabled_when?: Array<ParameterCondition>
  help?: string
}

export interface LocalBacktestStrategy {
  id: string
  name: string
  description: string
  api_version: string
  warmup_bars: number
  parameters: { [key: string]: LocalBacktestParameter }
  error?: string | null
  rules?: Array<string>
  warmup_rule?: WarmupRule | null
  parameter_constraints?: Array<ParameterConstraint>
}

export interface MACDResponse {
  dif: number | null
  dea: number | null
  histogram: number | null
}

export interface MarketScreenerFilters {
  market?: "spot" | "usdm" | "all"
  quoteAsset?: string
  minPriceChangePct?: number | null
  maxPriceChangePct?: number | null
  minQuoteVolume?: number | null
  maxFundingRatePct?: number | null
  minBreakoutScore?: number | null
  minOiChange1hPct?: number | null
  minRsi?: number | null
  maxRsi?: number | null
  includeWeb3?: boolean
  web3ChainId?: string | null
  maxWeb3RiskLevel?: number | null
  symbols?: Array<string>
  limit?: number
}

export interface NormalizedTradeStats {
  trades: number
  wins: number
  losses: number
  gross_profit: number
  gross_loss: number
  profit_factor: number | null
  principal_per_trade: number
  net_profit: number
  top_1_gross_profit_share_pct: number | null
  top_10_gross_profit_share_pct: number | null
  basis: string
  [key: string]: unknown
}

export interface OhlcvPointResponse {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ParameterCondition {
  parameter: string
  operator?: "eq" | "ne" | "in" | "gt"
  value: unknown
}

export interface ParameterConstraint {
  parameter: string
  operator: "lt" | "le" | "eq" | "gt" | "integer"
  other_parameter?: string | null
  value?: unknown
  enabled_when?: Array<ParameterCondition>
  message: string
}

export interface ParameterOption {
  value: unknown
  label: string
}

export interface ParameterRange {
  start: number
  end: number
  step: number
}

export interface ParameterSweepItem {
  case: string
  name: string
  parameters: { [key: string]: unknown }
  timeframe: string
  run_id: string | null
  status: string
  progress: number
  report: { [key: string]: unknown } | null
  error: string | null
  chart_path: string | null
  execution_summary?: { [key: string]: unknown }
  config?: { [key: string]: unknown }
}

export interface SweepDataPreview {
  config: { [key: string]: unknown }
  warmup_bars: number
  warmup_explanation: string
  rules_summary: Array<string>
  signal_data: DataCoverage
  execution_data?: DataCoverage | null
  comparable_intervals: Array<CachedInterval>
  warnings: Array<string>
  case: string
}

export interface TradeChange {
  kind: "added" | "dropped" | "changed"
  entry_time: number
  side: string
  occurrence: number
  before: TradeSnapshot | null
  after: TradeSnapshot | null
  changed_fields: Array<string>
}

export interface TradeGroupSummary {
  trades: number
  wins: number
  losses: number
  gross_profit: number
  gross_loss: number
  profit_factor: number | null
  [key: string]: unknown
}

export interface TradeSignalConfidenceBucketResponse {
  key: string
  minConfidence: number
  maxConfidence: number
  total: number
  resolved: number
  targetHits: number
  stopHits: number
  winRatePct?: number | null
  expectedWinRatePct?: number | null
  calibrationGapPct?: number | null
}

export interface TradeSignalStatGroupResponse {
  key: string
  total: number
  resolved: number
  targetHits: number
  stopHits: number
  ambiguous: number
  expired: number
  winRatePct?: number | null
  averageConfidence?: number | null
  averageMfePct?: number | null
  averageMaePct?: number | null
}

export interface TradeSnapshot {
  trade_id: number
  entry_time: number
  side: string
  return_pct: number
  [key: string]: unknown
}

export interface WarmupRule {
  version: "1"
  seed_weight_tolerance?: number
  minimum_bars?: number
  terms: Array<WarmupTerm>
  explanation: string
}

export interface WarmupTerm {
  kind: "ema" | "rma" | "window"
  period: number | string
  extra_bars?: number | string
  enabled_when?: Array<ParameterCondition>
}

export interface ExportLocalBacktestQueryParams {
  format?: "json" | "trades" | "equity"
}

export interface GetAssetResearchQueryParams {
  timeframe?: string
  history_days?: number
  asset_class?: string | null
  chain_id?: string | null
  platform?: string | null
}

export interface GetParameterSweepQueryParams {
  offset?: number
  limit?: number
  sort?: "return_pct" | "win_rate" | "max_drawdown_pct" | "total_trades"
  descending?: boolean
  minimum_trades?: number
}

export interface GetResearchWorkbenchQueryParams {
  event_limit?: number
  note_limit?: number
}

export interface ListLocalBacktestsQueryParams {
  offset?: number
  limit?: number
  archived?: boolean
}

export interface ListMarketScreenerRunsQueryParams {
  offset?: number
  limit?: number
}

export interface ListMarketScreenersQueryParams {
  include_archived?: boolean
}

export interface ListParameterSweepsQueryParams {
  offset?: number
  limit?: number
}

export interface ListResearchEventsQueryParams {
  kind?: string | null
  unacknowledged_only?: boolean
  since?: string | null
  limit?: number
}

export interface ListResearchReportsQueryParams {
  include_archived?: boolean
  offset?: number
  limit?: number
}

export interface ListTradeSignalsQueryParams {
  symbol?: string | null
  outcome_status?: string | null
  source?: string | null
  include_archived?: boolean
  offset?: number
  limit?: number
}

export interface LocalBacktestDiagnosticsQueryParams {
  equity_kind?: "equity" | "execution_equity"
}

export interface LocalBacktestRecordsQueryParams {
  offset?: number
  limit?: number
  start?: number | null
  end?: number | null
  sampled?: boolean
}

export interface LocalBacktestTradeChangesQueryParams {
  offset?: number
  limit?: number
}

export interface LocalBacktestTradeTimelineQueryParams {
  offset?: number
  limit?: number
}
