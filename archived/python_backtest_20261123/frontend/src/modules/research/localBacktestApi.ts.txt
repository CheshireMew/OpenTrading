import { apiGet, apiPost } from '@/api/request'
import type { LocalBacktestCommand, LocalBacktestRecordsQueryParams } from './generatedContracts'

export const localBacktestApi = {
  catalog: () => apiGet('local_backtest_strategies'),
  list: (offset = 0, archived = false) => apiGet('list_local_backtests', { query: { offset, limit: 30, archived } }),
  create: (body: LocalBacktestCommand) => apiPost('create_local_backtest', body),
  preview: (body: LocalBacktestCommand) => apiPost('preview_local_backtest', body, { client: 'longTask' }),
  get: (id: string) => apiGet('get_local_backtest', { path: { run_id: id } }),
  diagnostics: (id: string, equityKind: 'equity' | 'execution_equity' = 'equity') => apiGet('local_backtest_diagnostics', { path: { run_id: id }, query: { equity_kind: equityKind }, client: 'longTask' }),
  tradeChanges: (id: string, otherId: string, offset = 0) => apiGet('local_backtest_trade_changes', { path: { run_id: id, other_id: otherId }, query: { offset, limit: 100 }, client: 'longTask' }),
  tradeTimeline: (id: string, tradeId: number, offset = 0) => apiGet('local_backtest_trade_timeline', { path: { run_id: id, trade_id: tradeId }, query: { offset, limit: 100 }, client: 'longTask' }),
  records: (id: string, kind: 'trades' | 'signals' | 'fills' | 'equity' | 'levels' | 'candles' | 'indicators' | 'events' | 'execution_equity', query: LocalBacktestRecordsQueryParams = {}) =>
    apiGet('local_backtest_records', { path: { run_id: id, kind }, query }),
  cancel: (id: string) => apiPost('cancel_local_backtest', {}, { path: { run_id: id } }),
  rerun: (id: string) => apiPost('rerun_local_backtest', {}, { path: { run_id: id } }),
  migrate: (id: string) => apiPost('migrate_local_backtest', {}, { path: { run_id: id } }),
  resume: (id: string) => apiPost('resume_local_backtest', {}, { path: { run_id: id } }),
  archive: (id: string) => apiPost('archive_local_backtest', {}, { path: { run_id: id } }),
  export: (id: string, format: 'json' | 'trades' | 'equity') => apiGet('export_local_backtest', { path: { run_id: id }, query: { format } }),
  log: (id: string) => apiGet('log_local_backtest', { path: { run_id: id } }),
}
