import { isRecord, readNumber, readString } from '@/composables/pageSnapshot'
import { toBaseSymbol } from '@/modules/market'
import { createDefaultPortfolioBalanceAssets, createPortfolioBalanceAsset } from './assets'
import { clamp, sanitizeNumber } from './number'
import { DEFAULT_REVIEW_FREQUENCY, daysAgoIso, todayIso } from './schedule'
import type {
  PortfolioSimulationEquityPoint,
  PortfolioSimulationSummary,
  PortfolioBalanceAssetInput,
  PortfolioBalanceSimulationConfig,
  PortfolioBalancePortfolio,
  PortfolioBalanceSnapshot,
  PortfolioBalanceStrategyConfig,
  PortfolioBalanceTrackingConfig,
  PortfolioHoldingsSource,
  PortfolioReviewFrequency,
} from './types'

let portfolioSequence = 0

const createPortfolioId = () => `portfolio-${Date.now()}-${portfolioSequence++}`

export const createDefaultPortfolioBalanceStrategyConfig = (): PortfolioBalanceStrategyConfig => ({
  rebalanceBand: 5,
  minTradeAmount: 10,
  reviewFrequency: DEFAULT_REVIEW_FREQUENCY,
})

export const createDefaultPortfolioBalanceTrackingConfig = (): PortfolioBalanceTrackingConfig => ({
  virtualCapital: 100000,
  inceptionDate: todayIso(),
})

export const createDefaultPortfolioBalanceSimulationConfig = (): PortfolioBalanceSimulationConfig => ({
  initialCapital: 100000,
  simulationStartDate: daysAgoIso(365),
})

export const normalizePortfolioBalanceAsset = (value: unknown): PortfolioBalanceAssetInput => {
  if (!isRecord(value)) return createPortfolioBalanceAsset()
  return createPortfolioBalanceAsset({
    id: readString(value.id, ''),
    symbol: toBaseSymbol(readString(value.symbol, '')),
    targetWeight: sanitizeNumber(value.targetWeight),
    units: sanitizeNumber(value.units),
    currentPrice: sanitizeNumber(value.currentPrice),
    seedValue: sanitizeNumber(value.seedValue),
  })
}

export const normalizePortfolioBalanceStrategyConfig = (value: unknown): PortfolioBalanceStrategyConfig => {
  const defaults = createDefaultPortfolioBalanceStrategyConfig()
  if (!isRecord(value)) return defaults

  const rawFrequency = readString(value.reviewFrequency, defaults.reviewFrequency)
  const reviewFrequency: PortfolioReviewFrequency =
    rawFrequency === 'daily' || rawFrequency === 'weekly' || rawFrequency === 'monthly' || rawFrequency === 'quarterly'
      ? rawFrequency
      : DEFAULT_REVIEW_FREQUENCY

  return {
    rebalanceBand: clamp(readNumber(value.rebalanceBand, defaults.rebalanceBand), 0, 100),
    minTradeAmount: sanitizeNumber(value.minTradeAmount, defaults.minTradeAmount),
    reviewFrequency,
  }
}

export const normalizePortfolioBalanceTrackingConfig = (value: unknown): PortfolioBalanceTrackingConfig => {
  const defaults = createDefaultPortfolioBalanceTrackingConfig()
  if (!isRecord(value)) return defaults

  return {
    virtualCapital: sanitizeNumber(value.virtualCapital, defaults.virtualCapital),
    inceptionDate: readString(value.inceptionDate, defaults.inceptionDate),
  }
}

export const normalizePortfolioBalanceSimulationConfig = (value: unknown): PortfolioBalanceSimulationConfig => {
  const defaults = createDefaultPortfolioBalanceSimulationConfig()
  if (!isRecord(value)) return defaults

  return {
    initialCapital: sanitizeNumber(value.initialCapital, defaults.initialCapital),
    simulationStartDate: readString(value.simulationStartDate, defaults.simulationStartDate),
  }
}

export const normalizePortfolioSimulationEquityPoint = (value: unknown): PortfolioSimulationEquityPoint => {
  if (!isRecord(value)) {
    return {
      id: 0,
      timestamp: '',
      equity: 0,
      pnl_abs: 0,
      drawdown_pct: 0,
    }
  }

  return {
    id: Math.max(readNumber(value.id, 0), 0),
    timestamp: readString(value.timestamp, ''),
    equity: sanitizeNumber(value.equity),
    pnl_abs: readNumber(value.pnl_abs, 0),
    drawdown_pct: sanitizeNumber(value.drawdown_pct),
  }
}

export const normalizePortfolioSimulationSummary = (value: unknown): PortfolioSimulationSummary | null => {
  if (!isRecord(value)) return null

  return {
    startDate: readString(value.startDate, ''),
    endDate: readString(value.endDate, ''),
    initialValue: sanitizeNumber(value.initialValue),
    finalValue: sanitizeNumber(value.finalValue),
    totalReturnPct: readNumber(value.totalReturnPct, 0),
    annualizedReturnPct: value.annualizedReturnPct === null ? null : readNumber(value.annualizedReturnPct, 0),
    maxDrawdownPct: sanitizeNumber(value.maxDrawdownPct),
    reviewCount: Math.max(readNumber(value.reviewCount, 0), 0),
    outOfBandReviewCount: Math.max(readNumber(value.outOfBandReviewCount, 0), 0),
    rebalanceCount: Math.max(readNumber(value.rebalanceCount, 0), 0),
    equityCurve: Array.isArray(value.equityCurve)
      ? value.equityCurve.map((item) => normalizePortfolioSimulationEquityPoint(item))
      : [],
  }
}

type PortfolioBalancePortfolioOverrides = Omit<Partial<PortfolioBalancePortfolio>, 'assets'> & {
  assets?: Partial<PortfolioBalanceAssetInput>[]
}

export const createPortfolioBalancePortfolio = (
  overrides: PortfolioBalancePortfolioOverrides = {},
): PortfolioBalancePortfolio => {
  const timestamp = todayIso()
  const holdingsSource: PortfolioHoldingsSource | null =
    overrides.holdingsSource === 'virtual' || overrides.holdingsSource === 'ledger'
      ? overrides.holdingsSource
      : null

  return {
    id: overrides.id || createPortfolioId(),
    name: readString(overrides.name, '新组合'),
    assets: Array.isArray(overrides.assets) && overrides.assets.length
      ? overrides.assets.map((asset) => normalizePortfolioBalanceAsset(asset))
      : [createPortfolioBalanceAsset()],
    strategy: normalizePortfolioBalanceStrategyConfig(overrides.strategy),
    tracking: normalizePortfolioBalanceTrackingConfig(overrides.tracking),
    simulation: normalizePortfolioBalanceSimulationConfig(overrides.simulation),
    holdingsInitializedAt: typeof overrides.holdingsInitializedAt === 'string' ? overrides.holdingsInitializedAt : null,
    lastPriceUpdatedAt: typeof overrides.lastPriceUpdatedAt === 'string' ? overrides.lastPriceUpdatedAt : null,
    seedCapital: typeof overrides.seedCapital === 'number' ? overrides.seedCapital : null,
    holdingsSource,
    createdAt: readString(overrides.createdAt, timestamp),
    updatedAt: readString(overrides.updatedAt, timestamp),
  }
}

export const copyPortfolioBalancePortfolio = (
  source: PortfolioBalancePortfolio,
  overrides: Pick<Partial<PortfolioBalancePortfolio>, 'name'> = {},
): PortfolioBalancePortfolio => createPortfolioBalancePortfolio({
  name: readString(overrides.name, source.name),
  assets: source.assets.map((asset) => ({
    symbol: asset.symbol,
    targetWeight: asset.targetWeight,
    units: asset.units,
    currentPrice: asset.currentPrice,
    seedValue: asset.seedValue,
  })),
  strategy: { ...source.strategy },
  tracking: { ...source.tracking },
  simulation: { ...source.simulation },
  holdingsInitializedAt: source.holdingsInitializedAt,
  lastPriceUpdatedAt: source.lastPriceUpdatedAt,
  seedCapital: source.seedCapital,
  holdingsSource: source.holdingsSource,
})

export const createDefaultPortfolioCollection = (defaultName = '长期核心组合'): PortfolioBalancePortfolio[] => ([
  createPortfolioBalancePortfolio({
    name: defaultName,
    assets: createDefaultPortfolioBalanceAssets(),
  }),
])

export const normalizePortfolioBalancePortfolio = (value: unknown): PortfolioBalancePortfolio => {
  const defaults = createPortfolioBalancePortfolio()
  if (!isRecord(value)) return defaults

  const rawHoldingsSource = readString(value.holdingsSource, '')
  const holdingsSource: PortfolioHoldingsSource | null =
    rawHoldingsSource === 'virtual' || rawHoldingsSource === 'ledger'
      ? rawHoldingsSource
      : null

  return {
    id: readString(value.id, defaults.id),
    name: readString(value.name, defaults.name),
    assets: Array.isArray(value.assets) && value.assets.length
      ? value.assets.map((asset) => normalizePortfolioBalanceAsset(asset))
      : defaults.assets,
    strategy: normalizePortfolioBalanceStrategyConfig(value.strategy),
    tracking: normalizePortfolioBalanceTrackingConfig(value.tracking),
    simulation: normalizePortfolioBalanceSimulationConfig(value.simulation),
    holdingsInitializedAt: typeof value.holdingsInitializedAt === 'string' ? value.holdingsInitializedAt : null,
    lastPriceUpdatedAt: typeof value.lastPriceUpdatedAt === 'string' ? value.lastPriceUpdatedAt : null,
    seedCapital: typeof value.seedCapital === 'number' ? value.seedCapital : null,
    holdingsSource,
    createdAt: readString(value.createdAt, defaults.createdAt),
    updatedAt: readString(value.updatedAt, defaults.updatedAt),
  }
}

export const createDefaultPortfolioBalanceSnapshot = (defaultName?: string): PortfolioBalanceSnapshot => {
  const portfolios = createDefaultPortfolioCollection(defaultName)
  return {
    activePortfolioId: portfolios[0].id,
    portfolios,
  }
}

export const createEmptyPortfolioBalanceSnapshot = (): PortfolioBalanceSnapshot => ({
  activePortfolioId: '',
  portfolios: [],
})

export const normalizePortfolioBalanceSnapshot = (
  value: unknown,
  fallback = createEmptyPortfolioBalanceSnapshot(),
): PortfolioBalanceSnapshot => {
  const defaults = fallback
  if (!isRecord(value)) return defaults

  const portfolios = Array.isArray(value.portfolios) && value.portfolios.length
    ? value.portfolios.map((item) => normalizePortfolioBalancePortfolio(item))
    : defaults.portfolios
  const nextActivePortfolioId = readString(value.activePortfolioId, portfolios[0]?.id || defaults.activePortfolioId)

  return {
    activePortfolioId: nextActivePortfolioId,
    portfolios,
  }
}

export const buildPortfolioBalanceSnapshot = (snapshot: PortfolioBalanceSnapshot): PortfolioBalanceSnapshot => (
  normalizePortfolioBalanceSnapshot(snapshot, createEmptyPortfolioBalanceSnapshot())
)

export const touchPortfolio = (portfolio: PortfolioBalancePortfolio) => {
  portfolio.updatedAt = new Date().toISOString()
}

export const hasMarketGap = (portfolio: PortfolioBalancePortfolio) => (
  portfolio.assets.some((asset) => toBaseSymbol(asset.symbol) && (!asset.currentPrice || asset.currentPrice <= 0))
)

export const hasActiveAssets = (portfolio: PortfolioBalancePortfolio) => (
  portfolio.assets.some((asset) => Boolean(toBaseSymbol(asset.symbol)))
)

