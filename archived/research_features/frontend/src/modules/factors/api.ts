import { apiGet, apiPost } from '@/api/request'
import type {
  FactorCatalogResponse,
  FactorResearchContractResponse,
  FactorExecutionConfig,
  FactorExecutionResponse,
  FactorResearchRequest,
  FactorResearchResponse,
  FactorResearchRunDetailResponse,
  FactorResearchRunListItemResponse,
} from './contracts'

export const factorApi = {
  getContract(): Promise<FactorResearchContractResponse> {
    return apiGet('get_factor_contract')
  },

  getCatalog(): Promise<FactorCatalogResponse> {
    return apiGet('get_factor_catalog')
  },

  analyze(body: FactorResearchRequest): Promise<FactorResearchResponse> {
    return apiPost('analyze_factors', body, { client: 'longTask' })
  },

  listRuns(limit: number = 20): Promise<FactorResearchRunListItemResponse[]> {
    return apiGet('list_factor_runs', { query: { limit } })
  },

  getRun(runId: number): Promise<FactorResearchRunDetailResponse> {
    return apiGet('get_factor_run', { path: { run_id: runId } })
  },

  startBacktest(runId: number, body: FactorExecutionConfig): Promise<FactorExecutionResponse> {
    return apiPost('start_factor_backtest', body, {
      client: 'longTask',
      path: { run_id: runId },
    })
  },

  startPaper(runId: number, body: FactorExecutionConfig): Promise<FactorExecutionResponse> {
    return apiPost('start_factor_paper_run', body, {
      client: 'longTask',
      path: { run_id: runId },
    })
  },
}


