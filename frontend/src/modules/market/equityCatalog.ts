import { apiGet } from '@/api/request'
import type { EquityCatalogResponse } from './contracts'
import i18n from '@/i18n'

export function equitySourceLabel(source: { id: string; label: string }) {
  const key = 'equities.sourceLabels.' + source.id
  return i18n.global.te(key) ? i18n.global.t(key) : source.label
}

export function equityProductLabel(product: string) {
  const labels: Record<string, string> = {
    Stocks: 'stocks', Futures: 'futures', 'Unified Tokenized Stocks': 'tokenizedStocks', 'Stock Perpetuals': 'stockPerpetuals',
  }
  return labels[product] ? i18n.global.t('equities.productLabels.' + labels[product]) : product
}

export const equityCatalogApi = {
  getCatalog(refresh = false): Promise<EquityCatalogResponse> {
    return apiGet('get_equity_catalog', { query: { refresh }, timeout: 65000 })
  },
}
