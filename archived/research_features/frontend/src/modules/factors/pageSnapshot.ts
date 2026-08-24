import { isRecord, readNumber, readString, readStringArray } from '@/composables/pageSnapshot'

import {
  createEmptyFactorExecutionForm,
  createEmptyFactorResearchForm,
  type FactorExecutionForm,
  type FactorResearchForm,
} from './state'

export interface FactorResearchSnapshot {
  form: FactorResearchForm
  executionForm: FactorExecutionForm
  selectedRunId: number | null
  selectedFactorId: string
}

export const createDefaultFactorResearchSnapshot = (): FactorResearchSnapshot => ({
  form: createEmptyFactorResearchForm(),
  executionForm: createEmptyFactorExecutionForm(),
  selectedRunId: null,
  selectedFactorId: '',
})

export const normalizeFactorResearchSnapshot = (
  value: unknown,
  fallback = createDefaultFactorResearchSnapshot(),
): FactorResearchSnapshot => {
  const defaults = fallback
  if (!isRecord(value)) return defaults

  const form = isRecord(value.form) ? value.form : {}
  const executionForm = isRecord(value.executionForm) ? value.executionForm : {}

  return {
    form: {
      symbol: readString(form.symbol, defaults.form.symbol),
      timeframe: ['1h', '4h', '1d'].includes(readString(form.timeframe, defaults.form.timeframe))
        ? readString(form.timeframe, defaults.form.timeframe) as typeof defaults.form.timeframe
        : defaults.form.timeframe,
      days: readNumber(form.days, defaults.form.days),
      horizon_bars: readNumber(form.horizon_bars, defaults.form.horizon_bars),
      max_lag_bars: readNumber(form.max_lag_bars, defaults.form.max_lag_bars),
      categories: readStringArray(form.categories),
      factor_ids: readStringArray(form.factor_ids),
    },
    executionForm: {
      initial_cash: readNumber(executionForm.initial_cash, defaults.executionForm.initial_cash),
      fee_rate: readNumber(executionForm.fee_rate, defaults.executionForm.fee_rate),
      position_size_pct: readNumber(executionForm.position_size_pct, defaults.executionForm.position_size_pct),
      stake_mode: readString(executionForm.stake_mode, defaults.executionForm.stake_mode) === 'unlimited' ? 'unlimited' : 'fixed',
      entry_threshold: typeof executionForm.entry_threshold === 'number' ? executionForm.entry_threshold : null,
      exit_threshold: typeof executionForm.exit_threshold === 'number' ? executionForm.exit_threshold : null,
      stoploss_pct: readNumber(executionForm.stoploss_pct, defaults.executionForm.stoploss_pct),
      takeprofit_pct: readNumber(executionForm.takeprofit_pct, defaults.executionForm.takeprofit_pct),
      max_hold_bars: readNumber(executionForm.max_hold_bars, defaults.executionForm.max_hold_bars),
    },
    selectedRunId: typeof value.selectedRunId === 'number' ? value.selectedRunId : null,
    selectedFactorId: readString(value.selectedFactorId, defaults.selectedFactorId),
  }
}

export const buildFactorResearchSnapshot = (snapshot: FactorResearchSnapshot): FactorResearchSnapshot => (
  normalizeFactorResearchSnapshot(snapshot)
)

