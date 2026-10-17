import { apiGet } from '@/api/request'
import type { EquityCatalogResponse } from './contracts'

export const equityCatalogApi = {
  getCatalog(refresh = false): Promise<EquityCatalogResponse> {
    return apiGet('get_equity_catalog', { query: { refresh }, timeout: 65000 })
  },
}
