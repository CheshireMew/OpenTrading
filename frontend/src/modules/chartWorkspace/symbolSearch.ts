import type { ChartSymbol } from './api'

export const marketLabelKey = (market?: ChartSymbol['market']) => ({
  spot: 'spot', usdm: 'perpetual', alpha: 'alpha', web3: 'web3', index: 'index', fx: 'fx', commodity: 'commodity',
})[market ?? 'spot']

export const marketSymbolType = (market: ChartSymbol['market']) => ({
  spot: 'crypto', usdm: 'futures', alpha: 'crypto', web3: 'crypto', index: 'index', fx: 'forex', commodity: 'futures',
})[market]

export function matchesChartSymbol(symbol: ChartSymbol, query: string): boolean {
  if (isOnchainAddressQuery(query)) {
    const parts = query.trim().split(':')
    const address = parts[parts.length - 1]!
    const contract = symbol.metadata?.contract_address ?? (symbol.market === 'web3' ? symbol.symbol : undefined)
    const platform = symbol.metadata?.platform ?? (symbol.market === 'web3' ? symbol.exchange : undefined)
    if (typeof contract !== 'string' || (parts.length === 2 && parts[0]!.toLowerCase() !== platform)) return false
    return platform === 'solana' || symbol.metadata?.chain_id === 'CT_501'
      ? contract === address : contract.toLowerCase() === address.toLowerCase()
  }
  return [symbol.id, symbol.symbol, symbol.name, symbol.exchange, ...(symbol.aliases ?? [])]
    .join(' ').toLowerCase().includes(query.trim().toLowerCase())
}

export function isOnchainAddressQuery(query: string): boolean {
  const parts = query.trim().split(':')
  if (parts.length > 2 || (parts.length === 2 && !['ethereum', 'bsc', 'base', 'solana'].includes(parts[0]!.toLowerCase()))) return false
  const address = parts[parts.length - 1]!
  return /^0x[0-9a-fA-F]{40}$/.test(address) || /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address)
}
