import { BASE, type ChartSymbol } from './api'
const QUOTES = ['FDUSD', 'USDT', 'USDC', 'BUSD', 'TUSD', 'USD', 'EUR', 'BTC', 'ETH']
const rawTicker = (value: string) => value.split(':').pop()!.replace(/\.P$/i, '').toUpperCase()

export function symbolAssetCode(symbol?: ChartSymbol, fallback = ''): string {
  const base = symbol?.metadata?.basecurrency
  if (typeof base === 'string' && base.trim()) return base.trim().toUpperCase()
  const name = symbol?.name.split('/')[0]
  if (symbol?.name.includes('/') && name) return name.toUpperCase()
  const ticker = rawTicker(symbol?.symbol || fallback)
  if (symbol?.market === 'index') return ticker
  const separated = ticker.split(/[-/_]/)
  if (separated.length > 1) return separated[0]!
  const quote = [symbol?.currency, ...QUOTES].find(quote => quote && ticker.endsWith(quote) && ticker.length > quote.length)
  return quote ? ticker.slice(0, -quote.length) : ticker
}

export function symbolIconUrl(symbol?: ChartSymbol, fallback = ''): string | undefined {
  const base = symbolAssetCode(symbol, fallback)
  // One automatic, same-origin image endpoint for every asset. The server
  // discovers current official URLs and caches images; no per-coin file list.
  if (symbol?.market !== 'index' && /^[A-Z0-9._-]{1,40}$/.test(base)) return `${BASE}/symbol-icons/${encodeURIComponent(base)}`
  const supplied = symbol?.metadata?.icon_url ?? symbol?.metadata?.logo_url
  if (typeof supplied === 'string' && /^(?:https?:\/\/|\/)/.test(supplied)) return supplied
  return undefined
}

export function catalogSymbolIcon(catalog: readonly ChartSymbol[], ticker: string): string | undefined {
  const id = ticker.replace(/^(?:opentrading|heimdall|replay\d*):/, '')
  const symbol = catalog.find(symbol => symbol.id === id) ?? catalog.find(symbol => symbol.symbol === id)
  return symbolIconUrl(symbol, id)
}
