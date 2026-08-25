export type PortfolioReviewFrequency = 'daily' | 'weekly' | 'monthly' | 'quarterly'
export type PortfolioSuggestedAction = 'wait' | 'cashflow' | 'full'
export type PortfolioSuggestedReason = 'on_track' | 'scheduled_review' | 'band_breach' | 'cashflow_first' | 'full_rebalance' | 'below_threshold'
export type PortfolioHoldingsSource = 'virtual' | 'ledger'

export interface PortfolioBalanceAssetInput {
  id: string
  symbol: string
  targetWeight: number
  units: number
  currentPrice: number
  seedValue: number
}

export interface PortfolioBalanceStrategyConfig {
  rebalanceBand: number
  minTradeAmount: number
  reviewFrequency: PortfolioReviewFrequency
}

export interface PortfolioBalanceTrackingConfig {
  virtualCapital: number
  inceptionDate: string
}

export interface PortfolioBalanceSimulationConfig {
  initialCapital: number
  simulationStartDate: string
}

export interface PortfolioBalancePortfolio {
  id: string
  name: string
  assets: PortfolioBalanceAssetInput[]
  strategy: PortfolioBalanceStrategyConfig
  tracking: PortfolioBalanceTrackingConfig
  simulation: PortfolioBalanceSimulationConfig
  holdingsInitializedAt?: string | null
  lastPriceUpdatedAt?: string | null
  seedCapital?: number | null
  holdingsSource?: PortfolioHoldingsSource | null
  createdAt: string
  updatedAt: string
}

export interface PortfolioBalanceAssetPlan {
  id: string
  symbol: string
  units: number
  seedValue: number
  currentValue: number
  trackingDiffValue: number
  price: number
  currentWeight: number
  normalizedTargetWeight: number
  targetValue: number
  driftValue: number
  driftWeight: number
  rebalanceAmount: number
  rebalanceUnits: number
  primaryAction: 'buy' | 'sell' | 'hold'
  bandLowerWeight: number
  bandUpperWeight: number
  bandLowerValue: number
  bandUpperValue: number
  isOutOfBand: boolean
  cashflowAmount: number
  projectedValue: number
  projectedWeight: number
  projectedIsOutOfBand: boolean
}

export interface PortfolioBalancePlan {
  totalValue: number
  trackingCapital: number
  targetWeightInputSum: number
  usesEqualWeightFallback: boolean
  totalBuyAmount: number
  totalSellAmount: number
  turnoverAmount: number
  maxDriftWeight: number
  outOfBandCount: number
  projectedOutOfBandCount: number
  reviewDue: boolean
  shouldReviewNow: boolean
  reviewFrequency: PortfolioReviewFrequency
  nextReviewDate: string
  daysUntilReview: number
  suggestedAction: PortfolioSuggestedAction
  suggestedReason: PortfolioSuggestedReason
  assets: PortfolioBalanceAssetPlan[]
}

export interface PortfolioSimulationSummary {
  startDate: string
  endDate: string
  initialValue: number
  finalValue: number
  totalReturnPct: number
  annualizedReturnPct: number | null
  maxDrawdownPct: number
  reviewCount: number
  outOfBandReviewCount: number
  rebalanceCount: number
  equityCurve: PortfolioSimulationEquityPoint[]
}

export interface PortfolioSimulationEquityPoint {
  id: number
  timestamp: string
  equity: number
  pnl_abs: number
  drawdown_pct: number
}

export interface PortfolioBalanceSnapshot {
  activePortfolioId: string
  portfolios: PortfolioBalancePortfolio[]
}

