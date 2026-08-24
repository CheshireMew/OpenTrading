import { ensureSymbolCatalogLoaded, isIndexSymbol, marketHistoryApi, marketIndexApi, toBaseSymbol } from '@/modules/market'
import type { MarketHistoryBatchItemResponse, OhlcvPointResponse } from '@/modules/market/contracts'
import type { PortfolioBalancePortfolio } from './types'

import { buildPortfolioSyntheticHistory } from './simulation'
import { collectPortfolioMarketTargets, readPortfolioSyntheticPrice } from './assets'
import { localIsoDateDaysAgo, toLocalIsoDate } from '@/utils/localDate'
import { PortfolioDataError } from './errors'
import { createPromiseLruCache } from './promiseCache'

type PortfolioHistoryPoint = { date: string; close: number }
type PortfolioHistoryMap = Record<string, PortfolioHistoryPoint[]>

const HISTORY_CACHE_LIMIT = 80
const HISTORY_CACHE_TTL_MS = 5 * 60 * 1000
const HISTORY_DATA_VERSION = 'v1'

const cloneHistory = (history: PortfolioHistoryPoint[]) => history.map((point) => ({ ...point }))
const cloneHistoryMap = (historyMap: PortfolioHistoryMap) => Object.fromEntries(
  Object.entries(historyMap).map(([symbol, history]) => [symbol, cloneHistory(history)]),
)

const portfolioHistoryCache = createPromiseLruCache({
  maxEntries: HISTORY_CACHE_LIMIT,
  ttlMs: HISTORY_CACHE_TTL_MS,
  clone: cloneHistory,
})
const portfolioHistoryMapCache = createPromiseLruCache({
  maxEntries: HISTORY_CACHE_LIMIT,
  ttlMs: HISTORY_CACHE_TTL_MS,
  clone: cloneHistoryMap,
})

const currentHistoryDataWindow = () => `${HISTORY_DATA_VERSION}:${toLocalIsoDate(new Date())}`

const rowsToHistory = (rows: OhlcvPointResponse[]): PortfolioHistoryPoint[] => rows
  .map((row) => {
    const timestamp = Number(row.timestamp || 0)
    const close = Number(row.close || 0)
    return {
      date: toLocalIsoDate(new Date(timestamp)),
      close,
    }
  })
  .filter((point) => point.date && point.close > 0)

const loadCryptoHistoryMap = async (symbols: string[], startText: string) => {
  const cacheKey = `crypto:${symbols.slice().sort().join(',')}:1d:${startText}:${currentHistoryDataWindow()}`
  return portfolioHistoryMapCache.load(cacheKey, async () => {
    const response = await marketHistoryApi.getBatchPriceHistory({
      symbols,
      timeframe: '1d',
      start_date: startText,
      fetch_policy: 'hydrate',
    })
    const seriesBySymbol = new Map(
      (response.items || []).map((item: MarketHistoryBatchItemResponse) => [item.symbol, item.items || []]),
    )
    return Object.fromEntries(
      symbols.map((symbol) => [symbol, rowsToHistory(seriesBySymbol.get(symbol) || [])]),
    )
  })
}

const loadIndexHistory = async (symbol: string, startText: string) => {
  const cacheKey = `index-pricing:${symbol}:1d:${startText}:${currentHistoryDataWindow()}`
  return portfolioHistoryCache.load(cacheKey, async () => {
    const response = await marketIndexApi.getIndexPricingHistory({
      symbol,
      timeframe: '1d',
      start_date: startText,
    })
    return rowsToHistory(response.data || [])
  })
}

export const fetchPortfolioPriceMap = async (portfolio: PortfolioBalancePortfolio) => {
  await ensureSymbolCatalogLoaded()
  const priceBySymbol = new Map<string, number>()
  portfolio.assets.forEach((asset) => {
    const symbol = toBaseSymbol(asset.symbol)
    const syntheticPrice = readPortfolioSyntheticPrice(symbol)
    if (!symbol || syntheticPrice === null || priceBySymbol.has(symbol)) return
    priceBySymbol.set(symbol, syntheticPrice)
  })

  const targets = collectPortfolioMarketTargets(portfolio.assets)
  if (!targets.length && !priceBySymbol.size) throw new PortfolioDataError('portfolioBalance.feedback.addTargetFirst')

  const latestStartDate = localIsoDateDaysAgo(30)
  const cryptoTargets = targets.filter((item) => !isIndexSymbol(item.marketSymbol))
  const indexTargets = targets.filter((item) => isIndexSymbol(item.marketSymbol))
  const cryptoPriceByMarketSymbol = new Map<string, number>()
  let cryptoFailed = false

  if (cryptoTargets.length) {
    try {
      const response = await marketHistoryApi.getCurrentPriceBatch({
        symbols: cryptoTargets.map((item) => item.marketSymbol),
        timeframe: '1d',
      })
      ;(response.items || []).forEach((item) => {
        const currentPrice = Number(item.current_price || 0)
        if (currentPrice > 0) cryptoPriceByMarketSymbol.set(item.symbol, currentPrice)
      })
    } catch {
      cryptoFailed = true
    }
  }

  const indexResponses = await Promise.allSettled(
    indexTargets.map((item) => loadIndexHistory(item.marketSymbol, latestStartDate)),
  )

  let successCount = priceBySymbol.size
  const failedSymbols: string[] = []
  cryptoTargets.forEach((target) => {
    const currentPrice = cryptoPriceByMarketSymbol.get(target.marketSymbol) || 0
    if (cryptoFailed || !currentPrice) {
      failedSymbols.push(target.symbol)
      return
    }
    priceBySymbol.set(target.symbol, currentPrice)
    successCount += 1
  })

  indexResponses.forEach((result, index) => {
    if (result.status !== 'fulfilled') {
      failedSymbols.push(indexTargets[index].symbol)
      return
    }
    const indexRows = Array.isArray(result.value) ? result.value : []
    const currentPrice = Number(indexRows[indexRows.length - 1]?.close || 0)
    if (!currentPrice) {
      failedSymbols.push(indexTargets[index].symbol)
      return
    }
    priceBySymbol.set(indexTargets[index].symbol, currentPrice)
    successCount += 1
  })

  if (!successCount) throw new PortfolioDataError('portfolioBalance.feedback.noLivePrices')
  return { priceBySymbol, successCount, failedSymbols }
}

export const loadPortfolioSimulationHistory = async (
  portfolio: PortfolioBalancePortfolio,
  startText: string,
) => {
  await ensureSymbolCatalogLoaded()
  const historyBySymbol: Record<string, Array<{ date: string; close: number }>> = {}

  portfolio.assets.forEach((asset) => {
    const symbol = toBaseSymbol(asset.symbol)
    if (!symbol || historyBySymbol[symbol]) return
    const syntheticHistory = buildPortfolioSyntheticHistory(symbol, startText)
    if (syntheticHistory.length) historyBySymbol[symbol] = syntheticHistory
  })

  const targets = collectPortfolioMarketTargets(portfolio.assets)
  if (!targets.length && !Object.keys(historyBySymbol).length) throw new PortfolioDataError('portfolioBalance.feedback.addTargetFirst')

  if (!targets.length) return historyBySymbol

  const cryptoTargets = targets.filter((item) => !isIndexSymbol(item.marketSymbol))
  const indexTargets = targets.filter((item) => isIndexSymbol(item.marketSymbol))
  const responseMap: PortfolioHistoryMap = {}

  if (cryptoTargets.length) {
    Object.assign(responseMap, await loadCryptoHistoryMap(
      cryptoTargets.map((item) => item.marketSymbol),
      startText,
    ))
  }

  const indexResponses = await Promise.allSettled(
    indexTargets.map((item) => loadIndexHistory(item.marketSymbol, startText)),
  )
  indexResponses.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      responseMap[indexTargets[index].marketSymbol] = result.value
    }
  })

  const failedSymbols = targets
    .filter((item) => !Array.isArray(responseMap[item.marketSymbol]))
    .map((item) => item.symbol)

  if (failedSymbols.length) {
    throw new PortfolioDataError('portfolioBalance.feedback.historySymbolsFailed', { symbols: failedSymbols.join(', ') })
  }

  targets.forEach((item) => {
    historyBySymbol[item.symbol] = cloneHistory(responseMap[item.marketSymbol] || [])
  })

  return historyBySymbol
}

