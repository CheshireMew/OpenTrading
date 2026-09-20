import { apiGet, apiPost } from '@/api/request'
import type { ResearchResultQuery } from './generatedContracts'

export const researchResultsApi = {
  query: (body: ResearchResultQuery) => apiPost('query_research_results', body),
  refresh: () => apiPost('refresh_research_results', { roots: [] }, { client: 'longTask' }),
  get: (entryId: string) => apiGet('get_research_result', { path: { entry_id: entryId } }),
}
