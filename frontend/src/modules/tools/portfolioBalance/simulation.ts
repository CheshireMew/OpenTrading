import type {
  PortfolioBalanceAssetInput,
  PortfolioBalancePortfolio,
  PortfolioSimulationSummary,
  PortfolioSimulationEquityPoint,
  PortfolioBalanceSimulationConfig,
  PortfolioBalanceStrategyConfig,
} from './types'

import {
  buildNormalizedPortfolioWeights,
  readPortfolioSyntheticPrice,
} from './assets'
import { normalizePortfolioBalanceAsset } from './snapshot'
import {
  clamp,
  PERCENT_BASE,
  round,
} from './number'
import {
  parseIsoDate,
  shiftReviewDate,
  todayIso,
} from './schedule'
import { diffLocalIsoDateDays, toLocalIsoDate } from '@/utils/localDate'

export interface PortfolioHistoryPoint {
  date: string
  close: number
}

export const portfolioSimulationInputKey = (portfolio: PortfolioBalancePortfolio) => JSON.stringify({
  assets: portfolio.assets.map((asset) => ({
    symbol: asset.symbol,
    targetWeight: asset.targetWeight,
  })),
  strategy: portfolio.strategy,
  simulation: portfolio.simulation,
})

export const buildPortfolioSyntheticHistory = (
  symbol: string,
  startDateText: string,
  endDateText = todayIso(),
): PortfolioHistoryPoint[] => {
  const price = readPortfolioSyntheticPrice(symbol)
  const startDate = parseIsoDate(startDateText)
  const endDate = parseIsoDate(endDateText)
  if (price === null || !startDate || !endDate || startDate.getTime() > endDate.getTime()) return []

  const points: PortfolioHistoryPoint[] = []
  const cursor = new Date(startDate)
  while (cursor.getTime() <= endDate.getTime()) {
    points.push({
      date: toLocalIsoDate(cursor),
      close: price,
    })
    cursor.setDate(cursor.getDate() + 1)
  }
  return points
}

const annualizedReturn = (initialValue: number, finalValue: number, totalDays: number) => {
  if (initialValue <= 0 || finalValue <= 0 || totalDays <= 0) return null
  return round(((finalValue / initialValue) ** (365 / totalDays) - 1) * 100, 2)
}

const toPortfolioSimulationTimestamp = (date: string) => `${date}T00:00:00`

export const buildPortfolioSimulationSummary = (
  historyBySymbol: Record<string, PortfolioHistoryPoint[]>,
  assets: PortfolioBalanceAssetInput[],
  strategy: PortfolioBalanceStrategyConfig,
  simulation: PortfolioBalanceSimulationConfig,
  startDateText: string,
): PortfolioSimulationSummary | null => {
  const normalizedAssets = assets
    .map(normalizePortfolioBalanceAsset)
    .filter((asset) => asset.symbol && asset.targetWeight > 0)
  const { normalizedWeights } = buildNormalizedPortfolioWeights(normalizedAssets)
  if (!normalizedAssets.length) return null

  const slicedSeries = normalizedAssets.map((asset, index) => ({
    symbol: asset.symbol,
    weight: normalizedWeights[index] || 0,
    points: (historyBySymbol[asset.symbol] || []).filter((point) => point.date >= startDateText),
  }))

  if (slicedSeries.some((series) => series.points.length < 2)) return null

  const commonDates = slicedSeries
    .map((series) => new Set(series.points.map((point) => point.date)))
    .reduce<string[]>((dates, dateSet, index) => {
      if (index === 0) return [...dateSet].sort()
      return dates.filter((date) => dateSet.has(date))
    }, [])

  if (commonDates.length < 2) return null

  const priceMapBySymbol = new Map<string, Map<string, number>>(
    slicedSeries.map((series) => [
      series.symbol,
      new Map(series.points.map((point) => [point.date, point.close])),
    ]),
  )

  const startDate = commonDates[0]
  const endDate = commonDates[commonDates.length - 1]
  const initialValue = simulation.initialCapital
  const holdings = normalizedAssets.map((asset, index) => {
    const startPrice = priceMapBySymbol.get(asset.symbol)?.get(startDate) || 0
    return startPrice > 0 ? (initialValue * (normalizedWeights[index] || 0)) / startPrice : 0
  })

  let peakValue = initialValue
  let maxDrawdownPct = 0
  let reviewCount = 0
  let outOfBandReviewCount = 0
  let rebalanceCount = 0
  let nextReviewDate = shiftReviewDate(startDate, strategy.reviewFrequency)
  let finalValue = initialValue
  const equityCurve: PortfolioSimulationEquityPoint[] = []

  commonDates.forEach((date, dateIndex) => {
    const prices = normalizedAssets.map((asset) => priceMapBySymbol.get(asset.symbol)?.get(date) || 0)
    const values = holdings.map((units, index) => units * prices[index])
    const portfolioValue = values.reduce((sum, value) => sum + value, 0)
    finalValue = portfolioValue
    peakValue = Math.max(peakValue, portfolioValue)
    if (peakValue > 0) {
      maxDrawdownPct = Math.max(maxDrawdownPct, ((peakValue - portfolioValue) / peakValue) * 100)
    }

    equityCurve.push({
      id: dateIndex + 1,
      timestamp: toPortfolioSimulationTimestamp(date),
      equity: round(portfolioValue, 2),
      pnl_abs: round(portfolioValue - initialValue, 2),
      drawdown_pct: round(peakValue > 0 ? ((peakValue - portfolioValue) / peakValue) * 100 : 0, 2),
    })

    if (dateIndex === 0) return

    const reviewDue = date >= nextReviewDate
    if (!reviewDue) return
    reviewCount += 1

    const currentWeights = portfolioValue > 0 ? values.map((value) => value / portfolioValue) : values.map(() => 0)
    const outOfBand = currentWeights.some((weight, index) => {
      const target = normalizedWeights[index] || 0
      const lower = clamp(target - strategy.rebalanceBand / PERCENT_BASE, 0, 1)
      const upper = clamp(target + strategy.rebalanceBand / PERCENT_BASE, 0, 1)
      return weight < lower || weight > upper
    })

    if (outOfBand) outOfBandReviewCount += 1
    if (!outOfBand) {
      nextReviewDate = shiftReviewDate(date, strategy.reviewFrequency)
      return
    }

    const targetValues = normalizedWeights.map((weight) => portfolioValue * weight)
    const turnoverAmount = targetValues.reduce((sum, targetValue, index) => sum + Math.abs(targetValue - values[index]), 0) / 2
    if (turnoverAmount < strategy.minTradeAmount) {
      nextReviewDate = shiftReviewDate(date, strategy.reviewFrequency)
      return
    }

    targetValues.forEach((targetValue, index) => {
      holdings[index] = prices[index] > 0 ? targetValue / prices[index] : holdings[index]
    })
    rebalanceCount += 1
    nextReviewDate = shiftReviewDate(date, strategy.reviewFrequency)
  })

  const totalDays = Math.max(diffLocalIsoDateDays(startDate, endDate), 1)

  return {
    startDate,
    endDate,
    initialValue: round(initialValue, 2),
    finalValue: round(finalValue, 2),
    totalReturnPct: round(((finalValue / initialValue) - 1) * 100, 2),
    annualizedReturnPct: annualizedReturn(initialValue, finalValue, totalDays),
    maxDrawdownPct: round(maxDrawdownPct, 2),
    reviewCount,
    outOfBandReviewCount,
    rebalanceCount,
    equityCurve,
  }
}

