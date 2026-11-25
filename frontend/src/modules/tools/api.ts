import { apiGet, apiPost } from '@/api/request'
import type {
  DCAResponse, ComparePairsCommand, PairCompareToolResponse,
  SimulateDcaCommand, ToolsPageContractResponse,
} from './contracts'

export const toolsApi = {
  getContract(): Promise<ToolsPageContractResponse> {
    return apiGet('get_tools_contract')
  },
  runSimulation(config: SimulateDcaCommand, signal?: AbortSignal): Promise<DCAResponse> {
    return apiPost('dca_simulate', config, { client: 'longTask', signal })
  },
  comparePairs(params: ComparePairsCommand, signal?: AbortSignal): Promise<PairCompareToolResponse> {
    return apiPost('compare_pairs', params, { client: 'longTask', signal })
  },
}
