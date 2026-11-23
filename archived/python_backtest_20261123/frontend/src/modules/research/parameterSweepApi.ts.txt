import { apiGet, apiPost } from '@/api/request'
import type { ParameterSweepCommand, GetParameterSweepQueryParams } from './generatedContracts'

export const parameterSweepApi = {
  preview: (body: ParameterSweepCommand) => apiPost('preview_parameter_sweep', body, { client: 'longTask' }),
  create: (body: ParameterSweepCommand) => apiPost('create_parameter_sweep', body, { client: 'longTask' }),
  list: (offset = 0) => apiGet('list_parameter_sweeps', { query: { offset, limit: 10 } }),
  get: (id: string, query: GetParameterSweepQueryParams = {}) => apiGet('get_parameter_sweep', { path: { sweep_id: id }, query }),
  action: (id: string, action: 'resume' | 'cancel') => apiPost('act_parameter_sweep', { action }, { path: { sweep_id: id }, client: 'longTask' }),
  effects: (id: string) => apiGet('parameter_sweep_effects', { path: { sweep_id: id }, client: 'longTask' }),
  export: (id: string) => apiGet('export_parameter_sweep', { path: { sweep_id: id } }),
}
