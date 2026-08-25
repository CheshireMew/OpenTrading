import type { PortfolioBalancePortfolio } from './types'

import { createPortfolioBalanceAsset } from './assets'
import { round, sanitizeNumber } from './number'
import { toBaseSymbol } from '@/modules/market'

interface LedgerPositionInput {
  symbol: string
  units: number
  costBasis: number
  marketPrice?: number | null
}

interface LedgerInput {
  transactions?: unknown[]
  summary: { positions?: LedgerPositionInput[] }
}

export const applyPortfolioLedgerHoldings = (
  portfolio: PortfolioBalancePortfolio,
  ledger: LedgerInput,
) => {
  const ledgerIsAuthoritative = Boolean(ledger.transactions?.length) || portfolio.holdingsSource === 'ledger'
  if (!ledgerIsAuthoritative) return false

  const positions = new Map(
    (ledger.summary.positions || [])
      .map((position) => [toBaseSymbol(position.symbol), position] as const)
      .filter(([symbol, position]) => Boolean(symbol) && Math.abs(position.units) > 1e-12),
  )
  let changed = portfolio.holdingsSource !== 'ledger' || portfolio.seedCapital !== null || !portfolio.holdingsInitializedAt

  portfolio.assets.forEach((asset) => {
    const position = positions.get(toBaseSymbol(asset.symbol))
    const nextUnits = round(position?.units || 0, 8)
    const nextSeedValue = round(position?.costBasis || 0, 2)
    const nextPrice = sanitizeNumber(position?.marketPrice, asset.currentPrice)
    if (asset.units !== nextUnits || asset.seedValue !== nextSeedValue || asset.currentPrice !== nextPrice) changed = true
    asset.units = nextUnits
    asset.seedValue = nextSeedValue
    asset.currentPrice = nextPrice
    if (position) positions.delete(toBaseSymbol(asset.symbol))
  })

  positions.forEach((position, symbol) => {
    portfolio.assets.push(createPortfolioBalanceAsset({
      symbol,
      targetWeight: 0,
      units: round(position.units, 8),
      seedValue: round(position.costBasis, 2),
      currentPrice: sanitizeNumber(position.marketPrice),
    }))
    changed = true
  })

  portfolio.holdingsInitializedAt ||= new Date().toISOString()
  portfolio.seedCapital = null
  portfolio.holdingsSource = 'ledger'
  return changed
}

export const applyLatestMarketPrices = (
  portfolio: PortfolioBalancePortfolio,
  priceBySymbol: Map<string, number>,
) => {
  portfolio.assets.forEach((asset) => {
    const symbol = toBaseSymbol(asset.symbol)
    asset.currentPrice = sanitizeNumber(priceBySymbol.get(symbol), asset.currentPrice)
  })
  portfolio.lastPriceUpdatedAt = new Date().toISOString()
}
