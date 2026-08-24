import { watch } from 'vue'
import type { FactorResearchRunDetailResponse } from './contracts'

import type { FactorResearchState } from './state'


export const useFactorResearchSelection = (state: FactorResearchState) => {
  const applyRun = (run: FactorResearchRunDetailResponse) => {
    const previousSelectedFactorId = state.selectedFactorId.value
    state.selectedRunId.value = run.id
    state.summary.value = run.summary
    state.ranking.value = run.ranking || []
    state.details.value = run.details || []
    state.blend.value = run.blend || null
    state.selectedFactorId.value = state.details.value.find((item) => item.factor_id === previousSelectedFactorId)?.factor_id
      || state.details.value[0]?.factor_id
      || ''

    const request = run.request || {}
    state.form.symbol = String(request.symbol || state.form.symbol)
    state.form.timeframe = (request.timeframe as typeof state.form.timeframe) || state.form.timeframe
    state.form.days = Number(request.days || state.form.days)
    state.form.horizon_bars = Number(request.horizon_bars || state.form.horizon_bars)
    state.form.max_lag_bars = Number(request.max_lag_bars || state.form.max_lag_bars)
    state.form.categories = Array.isArray(request.categories) ? [...(request.categories as string[])] : []
    state.form.factor_ids = Array.isArray(request.factor_ids) ? [...(request.factor_ids as string[])] : []

    state.executionForm.entry_threshold = typeof run.blend?.entry_threshold === 'number' ? run.blend.entry_threshold : null
    state.executionForm.exit_threshold = typeof run.blend?.exit_threshold === 'number' ? run.blend.exit_threshold : null
  }

  const toggleCategory = (category: string) => {
    if (state.form.categories.includes(category)) {
      state.form.categories = state.form.categories.filter((item) => item !== category)
      return
    }
    state.form.categories = [...state.form.categories, category]
  }

  const resetFactorSelection = () => {
    state.form.factor_ids = []
  }

  const toggleFactor = (factorId: string) => {
    if (state.form.factor_ids.includes(factorId)) {
      state.form.factor_ids = state.form.factor_ids.filter((item) => item !== factorId)
      return
    }
    state.form.factor_ids = [...state.form.factor_ids, factorId]
  }

  const selectFactor = (factorId: string) => {
    state.selectedFactorId.value = factorId
  }

  watch(
    () => state.form.categories,
    () => {
      const poolIds = new Set(state.factorPool.value.map((item) => item.factor_id))
      state.form.factor_ids = state.form.factor_ids.filter((item) => poolIds.has(item))
    },
    { deep: true },
  )

  return {
    applyRun,
    toggleCategory,
    resetFactorSelection,
    toggleFactor,
    selectFactor,
  }
}


