import { onMounted } from 'vue'
import type { Router } from 'vue-router'

import { factorApi } from './api'
import { factorExecutionPayload, factorResearchPayload, type FactorResearchState } from './state'
import type { FactorResearchRunDetailResponse } from './contracts'

const responseErrorDetail = (error: unknown): string | null => {
  if (!error || typeof error !== 'object' || !('response' in error)) return null
  const response = (error as { response?: { data?: { detail?: unknown } } }).response
  const detail = response?.data?.detail
  return typeof detail === 'string' ? detail : null
}

export const useFactorResearchData = (
  state: FactorResearchState,
  applyRun: (run: FactorResearchRunDetailResponse) => void,
  t: (key: string) => string,
  router: Router,
  initializeContract: () => Promise<void>,
) => {
  const fetchCatalog = async () => {
    state.catalogLoading.value = true
    try {
      const response = await factorApi.getCatalog()
      state.catalog.symbols = response.symbols || []
      state.catalog.timeframes = response.timeframes || []
      state.catalog.categories = response.categories || []
      state.catalog.factors = response.factors || []
      state.catalog.forward_horizons = response.forward_horizons || []
      state.catalog.cleaning = response.cleaning || {}
      if (state.catalog.symbols.length && !state.catalog.symbols.includes(state.form.symbol)) state.form.symbol = state.catalog.symbols[0]
      if (state.catalog.timeframes.length && !state.catalog.timeframes.includes(state.form.timeframe)) state.form.timeframe = state.catalog.timeframes[0] as typeof state.form.timeframe
      if (!state.form.categories.length) state.form.categories = [...state.catalog.categories]
    } catch (err) {
      console.error('Failed to load factor catalog', err)
      state.error.value = t('factorResearch.catalogFailed')
    } finally {
      state.catalogLoading.value = false
    }
  }

  const fetchRuns = async () => {
    state.runsLoading.value = true
    try {
      const response = await factorApi.listRuns()
      state.runs.value = response || []
      if (!state.selectedRunId.value && state.runs.value.length) {
        const latest = await factorApi.getRun(state.runs.value[0].id)
        applyRun(latest)
      }
    } catch (err) {
      console.error('Failed to load factor runs', err)
    } finally {
      state.runsLoading.value = false
    }
  }

  const loadRun = async (runId: number) => {
    const response = await factorApi.getRun(runId)
    const run = response
    const existingIndex = state.runs.value.findIndex((item) => item.id === run.id)
    if (existingIndex >= 0) state.runs.value.splice(existingIndex, 1, run)
    else state.runs.value.unshift(run)
    applyRun(run)
  }

  const runAnalysis = async () => {
    state.loading.value = true
    state.error.value = ''
    try {
      const response = await factorApi.analyze(factorResearchPayload(state.form))
      state.summary.value = response.summary
      state.ranking.value = response.ranking || []
      state.details.value = response.details || []
      state.blend.value = response.blend || null
      state.selectedRunId.value = response.run_id
      if (!state.selectedDetail.value || !state.details.value.find((item) => item.factor_id === state.selectedFactorId.value)) {
        state.selectedFactorId.value = state.details.value[0]?.factor_id || ''
      }
      state.executionForm.entry_threshold = response.blend?.entry_threshold ?? null
      state.executionForm.exit_threshold = response.blend?.exit_threshold ?? null
      await fetchRuns()
      if (response.run_id) {
        await loadRun(response.run_id)
      }
    } catch (err: unknown) {
      console.error('Failed to analyze factors', err)
      state.error.value = responseErrorDetail(err) || t('factorResearch.analysisFailed')
      state.ranking.value = []
      state.details.value = []
      state.summary.value = null
      state.blend.value = null
      state.selectedFactorId.value = ''
    } finally {
      state.loading.value = false
    }
  }

  const startExecution = async (mode: 'backtest' | 'paper') => {
    if (!state.selectedRunId.value) return
    state.executionLoading.value = mode
    state.error.value = ''
    try {
      const body = factorExecutionPayload(state.executionForm)
      const response = mode === 'backtest'
        ? await factorApi.startBacktest(state.selectedRunId.value, body)
        : await factorApi.startPaper(state.selectedRunId.value, body)
      router.push(mode === 'backtest' ? `/backtest/runs/${response.run_id}` : `/backtest/paper/${response.run_id}`)
    } catch (err: unknown) {
      console.error('Failed to start factor execution', err)
      state.error.value = responseErrorDetail(err) || t('factorResearch.executionFailed')
    } finally {
      state.executionLoading.value = ''
    }
  }

  onMounted(async () => {
    try {
      await initializeContract()
    } catch (err) {
      console.error('Failed to load factor contract', err)
      state.error.value = t('factorResearch.catalogFailed')
      return
    }
    await Promise.all([fetchCatalog(), fetchRuns()])
    if (state.error.value) return
    if (state.selectedRunId.value) {
      try {
        await loadRun(state.selectedRunId.value)
        return
      } catch (err) {
        console.warn('Failed to restore factor run, clearing selection', err)
        state.selectedRunId.value = null
      }
    }
  })

  return {
    fetchCatalog,
    fetchRuns,
    loadRun,
    runAnalysis,
    startExecution,
  }
}

