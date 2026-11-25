import type { ChartSymbol } from './api'

export const marketLabelKey = (market?: ChartSymbol['market']) => ({
  spot: 'spot', usdm: 'perpetual', index: 'index', fx: 'fx', commodity: 'commodity',
})[market ?? 'spot']

export const marketSymbolType = (market: ChartSymbol['market']) => ({
  spot: 'crypto', usdm: 'futures', index: 'index', fx: 'forex', commodity: 'futures',
})[market]

export function matchesChartSymbol(symbol: ChartSymbol, query: string): boolean {
  return [symbol.id, symbol.symbol, symbol.name, symbol.exchange, ...(symbol.aliases ?? [])]
    .join(' ').toLowerCase().includes(query.trim().toLowerCase())
}
