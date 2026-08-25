// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

export interface PortfolioAnalyticsResponse {
  portfolioId: string
  startDate: string
  endDate: string
  periodDays: number
  totalEquity: number
  timeWeightedReturnPct?: number | null
  moneyWeightedReturnPct?: number | null
  benchmarkSymbol: string
  benchmarkReturnPct?: number | null
  excessReturnPct?: number | null
  annualizedVolatilityPct?: number | null
  valueAtRisk95?: number | null
  maxDrawdownPct?: number | null
  concentrationHhi: number
  effectivePositionCount?: number | null
  topPositionWeightPct: number
  symbols?: Array<string>
  correlation?: Array<PortfolioCorrelationRowResponse>
  assets?: Array<PortfolioAssetRiskResponse>
  performance?: Array<PortfolioPerformancePointResponse>
  scenarios?: Array<PortfolioScenarioResponse>
  issues?: Array<string>
}

export interface PortfolioAnalyticsCommand {
  periodDays?: number
  benchmarkSymbol?: string
  customShocks?: { [key: string]: number }
}

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

export interface PortfolioCollectionResponse {
  revision: number
  snapshot: PortfolioBalanceSnapshot
}

export interface PortfolioLedgerResponse {
  portfolioId: string
  transactions?: Array<PortfolioTransactionResponse>
  archivedTransactions?: Array<PortfolioTransactionResponse>
  summary: PortfolioLedgerSummaryResponse
}

export interface PortfolioTransactionResponse {
  id: string
  portfolioId: string
  transactionType: "buy" | "sell" | "deposit" | "withdrawal" | "fee" | "transfer_in" | "transfer_out"
  symbol: string
  quantity: number
  unitPrice: number
  cashAmount: number
  fee: number
  currency: string
  feeCurrency: string
  externalId?: string | null
  note: string
  metadata?: { [key: string]: string | number | boolean | null }
  version: number
  occurredAt: string
  archivedAt?: string | null
  createdAt: string
  updatedAt: string
}

export interface PortfolioTransactionCreateCommand {
  transactionType: "buy" | "sell" | "deposit" | "withdrawal" | "fee" | "transfer_in" | "transfer_out"
  symbol?: string
  quantity?: number
  unitPrice?: number
  cashAmount?: number
  fee?: number
  currency?: string
  feeCurrency?: string
  externalId?: string | null
  note?: string
  metadata?: { [key: string]: string | number | boolean | null }
  occurredAt: string
}

export interface PortfolioTransactionUpdateCommand {
  transactionType: "buy" | "sell" | "deposit" | "withdrawal" | "fee" | "transfer_in" | "transfer_out"
  symbol?: string
  quantity?: number
  unitPrice?: number
  cashAmount?: number
  fee?: number
  currency?: string
  feeCurrency?: string
  externalId?: string | null
  note?: string
  metadata?: { [key: string]: string | number | boolean | null }
  occurredAt: string
  expectedVersion: number
}

export interface PortfolioTransactionArchiveCommand {
  expectedVersion: number
}

export interface PortfolioTransactionImportResponse {
  importedCount: number
  archivedCount: number
  ledger: PortfolioLedgerResponse
}

export interface PortfolioTransactionImportCommand {
  mode?: "append" | "replace"
  transactions: Array<PortfolioTransactionCreateCommand>
}

export interface PortfolioCollectionSaveCommand {
  expectedRevision: number
  snapshot: PortfolioBalanceSnapshot
}

export interface PortfolioCollectionChangeCommand {
  expectedRevision: number
  activePortfolioId: string
  changedPortfolios?: Array<PortfolioBalancePortfolio>
  portfolioOrder: Array<string>
}

export interface PortfolioDeletedPage {
  items?: Array<PortfolioDeletedSummary>
  offset: number
  limit: number
  total: number
}

export interface PortfolioExportDocument {
  schemaVersion: 2
  exportedAt: string
  snapshot: PortfolioBalanceSnapshot
  deletedPortfolios?: Array<PortfolioBalancePortfolio>
  simulationResults?: Array<PortfolioSimulationArtifact>
}

export interface PortfolioCollectionImportCommand {
  expectedRevision: number
  mode?: "merge" | "replace"
  document: PortfolioExportDocument | LegacyPortfolioExportDocument
}

export interface PortfolioSimulationResultResponse {
  portfolioId: string
  result?: PortfolioSimulationSummary | null
  updatedAt?: string | null
}

export interface PortfolioSimulationResultCommand {
  expectedRevision: number
  result: PortfolioSimulationSummary
}

export interface PortfolioRestoreCommand {
  expectedRevision: number
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

export interface LegacyPortfolioBalancePortfolio {
  id: string
  name: string
  assets: Array<PortfolioBalanceAsset>
  strategy: PortfolioBalanceStrategy
  tracking: PortfolioBalanceTracking
  simulation: PortfolioBalanceSimulation
  holdingsInitializedAt?: string | null
  lastPriceUpdatedAt?: string | null
  seedCapital?: number | null
  holdingsSource?: "virtual" | "ledger" | null
  createdAt: string
  updatedAt: string
  lastSimulationResult?: PortfolioSimulationSummary | null
}

export interface LegacyPortfolioBalanceSnapshot {
  activePortfolioId?: string
  portfolios?: Array<LegacyPortfolioBalancePortfolio>
}

export interface LegacyPortfolioExportDocument {
  schemaVersion: 1
  exportedAt: string
  snapshot: LegacyPortfolioBalanceSnapshot
  deletedPortfolios?: Array<LegacyPortfolioBalancePortfolio>
}

export interface PairCompareStatisticsResponse {
  aligned_points: number
  symbol_a_return_pct?: number | null
  symbol_b_return_pct?: number | null
  excess_return_pct?: number | null
  return_correlation?: number | null
  ratio_change_pct?: number | null
}

export interface PortfolioAssetRiskResponse {
  symbol: string
  weightPct: number
  annualizedVolatilityPct?: number | null
  riskContributionPct?: number | null
  periodReturnPct?: number | null
  returnContributionPct?: number | null
}

export interface PortfolioBalanceAsset {
  id: string
  symbol?: string
  targetWeight?: number
  units?: number
  currentPrice?: number
  seedValue?: number
}

export interface PortfolioBalancePortfolio {
  id: string
  name: string
  assets: Array<PortfolioBalanceAsset>
  strategy: PortfolioBalanceStrategy
  tracking: PortfolioBalanceTracking
  simulation: PortfolioBalanceSimulation
  holdingsInitializedAt?: string | null
  lastPriceUpdatedAt?: string | null
  seedCapital?: number | null
  holdingsSource?: "virtual" | "ledger" | null
  createdAt: string
  updatedAt: string
}

export interface PortfolioBalanceSimulation {
  initialCapital?: number
  simulationStartDate: string
}

export interface PortfolioBalanceSnapshot {
  activePortfolioId?: string
  portfolios?: Array<PortfolioBalancePortfolio>
}

export interface PortfolioBalanceStrategy {
  rebalanceBand?: number
  minTradeAmount?: number
  reviewFrequency?: "daily" | "weekly" | "monthly" | "quarterly"
}

export interface PortfolioBalanceTracking {
  virtualCapital?: number
  inceptionDate: string
}

export interface PortfolioCorrelationRowResponse {
  symbol: string
  values?: Array<number | null>
}

export interface PortfolioDeletedSummary {
  id: string
  name: string
  deletedAt: string
}

export interface PortfolioLedgerPositionResponse {
  symbol: string
  units: number
  averageCost: number
  costBasis: number
  marketPrice?: number | null
  marketValue: number
  realizedPnl: number
  unrealizedPnl: number
  fees: number
}

export interface PortfolioLedgerSummaryResponse {
  cashBalance: number
  contributions: number
  withdrawals: number
  netContributions: number
  totalFees: number
  costBasis: number
  marketValue: number
  totalEquity: number
  realizedPnl: number
  unrealizedPnl: number
  totalPnl: number
  simpleReturnPct?: number | null
  moneyWeightedReturnPct?: number | null
  timeWeightedReturnPct?: number | null
  positions?: Array<PortfolioLedgerPositionResponse>
  issues?: Array<string>
  reliability: "complete" | "incomplete"
}

export interface PortfolioPerformancePointResponse {
  date: string
  equity: number
  externalCashFlow: number
  dailyReturnPct?: number | null
  drawdownPct: number
}

export interface PortfolioScenarioResponse {
  id: string
  name: string
  shocks?: { [key: string]: number }
  projectedPnl: number
  projectedReturnPct?: number | null
  projectedEquity: number
}

export interface PortfolioSimulationArtifact {
  portfolioId: string
  result: PortfolioSimulationSummary
}

export interface PortfolioSimulationEquityPoint {
  id: number
  timestamp: string
  equity: number
  pnl_abs: number
  drawdown_pct: number
}

export interface PortfolioSimulationSummary {
  startDate: string
  endDate: string
  initialValue: number
  finalValue: number
  totalReturnPct: number
  annualizedReturnPct?: number | null
  maxDrawdownPct: number
  reviewCount: number
  outOfBandReviewCount: number
  rebalanceCount: number
  equityCurve?: Array<PortfolioSimulationEquityPoint>
}

export interface ToolCandlestickPointResponse {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export interface ListDeletedPortfoliosQueryParams {
  offset?: number
  limit?: number
}
