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

export interface LocalBacktestCatalog {
  strategies: Array<LocalBacktestStrategy>
  symbols: Array<string>
  timeframes: { [key: string]: Array<string> }
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
}

export interface LocalBacktestRuns {
  items: Array<LocalBacktestRun>
  total: number
}

export interface LocalBacktestRecords {
  items: Array<{ [key: string]: unknown }>
  total: number
  offset: number
}

export interface LocalBacktestAction {
}

export interface LocalBacktestExport {
  filename: string
  content: string
  media_type: string
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
}

export interface LocalBacktestStrategy {
  id: string
  name: string
  description: string
  api_version: string
  warmup_bars: number
  parameters: { [key: string]: LocalBacktestParameter }
  error?: string | null
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

export interface OhlcvPointResponse {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
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

export interface LocalBacktestRecordsQueryParams {
  offset?: number
  limit?: number
  start?: number | null
  end?: number | null
  sampled?: boolean
}
