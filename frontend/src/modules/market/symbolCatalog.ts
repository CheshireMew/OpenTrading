import { computed, ref } from 'vue'

import { marketCatalogApi } from './api'
import type { MarketSymbolSearchResponse } from './contracts'

const symbols = ref<MarketSymbolSearchResponse[]>([])
const loading = ref(false)
let loaded = false
let loadingPromise: Promise<void> | null = null

export const toBaseSymbol = (symbol: string) => {
  const value = String(symbol || '').trim().toUpperCase()
  if (/^(BINANCE|OKX):(SPOT|USDM):/.test(value)) return String(symbol).trim()
  const [base] = value.split('/')
  const [assetCode] = base.split(':')
  return assetCode.trim()
}

const lookupCatalogItem = (symbol: string) => {
  const normalized = String(symbol || '').trim().toUpperCase()
  if (!normalized) return null
  const base = toBaseSymbol(normalized)
  return symbols.value.find((item) => {
    const itemSymbol = String(item.symbol || '').trim().toUpperCase()
    return itemSymbol === normalized || toBaseSymbol(itemSymbol) === base
  }) || null
}

export const findSymbolCatalogItem = (symbol: string) => {
  return lookupCatalogItem(symbol)
}

export const isIndexSymbol = (symbol: string) => lookupCatalogItem(symbol)?.asset_class === 'index'

export const isUsdEquivalentSymbol = (symbol: string) => lookupCatalogItem(symbol)?.asset_class === 'cash'

export const toSlashMarketSymbol = (symbol: string, quoteAsset = 'USDT') => {
  const value = String(symbol || '').trim().toUpperCase()
  const normalizedQuote = String(quoteAsset || '').trim().toUpperCase()
  if (!value) return ''
  if (value.includes('/')) return value
  if (normalizedQuote && value.endsWith(normalizedQuote) && value.length > normalizedQuote.length) {
    return `${value.slice(0, -normalizedQuote.length)}/${normalizedQuote}`
  }
  return value
}

export const readCashSymbolPrices = () => (
  Object.fromEntries(
    symbols.value
      .filter((item) => item.asset_class === 'cash')
      .map((item) => [toBaseSymbol(item.symbol), 1]),
  ) as Record<string, number>
)

export const ensureSymbolCatalogLoaded = async () => {
  if (loaded) return
  if (loadingPromise) return loadingPromise
  loading.value = true
  loadingPromise = marketCatalogApi.getSymbols()
    .then((response) => {
      if (Array.isArray(response)) {
        symbols.value = response
        loaded = true
      }
    })
    .catch((error) => {
      console.warn('Symbol catalog load failed', error)
      throw error
    })
    .finally(() => {
      loading.value = false
      loadingPromise = null
    })
  return loadingPromise
}

export function useSymbolCatalog() {
  return {
    symbols: computed(() => symbols.value),
    loading,
    loadSymbols: ensureSymbolCatalogLoaded,
  }
}

