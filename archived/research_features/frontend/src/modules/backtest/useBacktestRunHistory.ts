import type { ComputedRef, Ref } from 'vue'

import type { BacktestDetailResponse, BacktestRunResponse } from './contracts'

import { backtestApi } from './api'
import type { BacktestRunMode } from './useBacktestRuns'
import type { BacktestVersionCompareOption } from './viewTypes'

const PAPER_HISTORY_REFRESH_INTERVAL_MS = 10000

interface BacktestRunTarget {
  id: number
  mode: BacktestRunMode
}

interface UseBacktestRunHistoryOptions {
  t: (key: string) => string
  history: Ref<BacktestRunResponse[]>
  paperHistory: Ref<BacktestRunResponse[]>
  historyMode: Ref<'backtest' | 'paper'>
  selectedRun: Ref<BacktestDetailResponse | null>
  selectedRunMode: Ref<'backtest' | 'paper' | null>
  compareRunIds: Ref<number[]>
  versionCompareSelections: Ref<number[]>
  versionCompareOptions: ComputedRef<BacktestVersionCompareOption[]>
  loadChart: (run: BacktestDetailResponse) => Promise<void>
  clearChart: () => void
}

export const useBacktestRunHistory = ({
  t,
  history,
  paperHistory,
  historyMode,
  selectedRun,
  selectedRunMode,
  compareRunIds,
  versionCompareSelections,
  versionCompareOptions,
  loadChart,
  clearChart,
}: UseBacktestRunHistoryOptions) => {
  let paperHistoryPromise: Promise<void> | null = null
  let paperSelectionRefreshPromise: Promise<void> | null = null
  let paperRefreshTimer: number | null = null

  const fetchHistory = async () => {
    try {
      const res = await backtestApi.listRuns()
      history.value = res
      const validRunIds = new Set(history.value.map((run) => run.id))
      compareRunIds.value = compareRunIds.value.filter((item) => validRunIds.has(item))
      const validVersions = new Set(versionCompareOptions.value.map((item) => item.version))
      versionCompareSelections.value = versionCompareSelections.value.filter((item) => validVersions.has(item))
    } catch {
      // Transport failures are logged by the API client; this hook only keeps the last successful list.
    }
  }

  const loadPaperHistory = async () => {
    try {
      const res = await backtestApi.listPaperRuns()
      paperHistory.value = res
    } catch {
      // Transport failures are logged by the API client; this hook only keeps the last successful list.
    }
  }

  const fetchPaperHistory = async () => {
    if (paperHistoryPromise) return paperHistoryPromise
    paperHistoryPromise = loadPaperHistory().finally(() => {
      paperHistoryPromise = null
    })
    return paperHistoryPromise
  }

  const loadResult = async (id: number) => {
    try {
      const res = await backtestApi.getRun(id)
      selectedRun.value = res
      selectedRunMode.value = 'backtest'
      historyMode.value = 'backtest'
      if (!compareRunIds.value.includes(id)) compareRunIds.value = [...compareRunIds.value, id]
      await loadChart(res)
      return res
    } catch (error) {
      console.error(error)
      return null
    }
  }

  const loadPaperResult = async (id: number) => {
    try {
      const res = await backtestApi.getPaperRun(id)
      selectedRun.value = res
      selectedRunMode.value = 'paper'
      historyMode.value = 'paper'
      await loadChart(res)
      return res
    } catch (error) {
      console.error(error)
      return null
    }
  }

  const loadRunTarget = async (target: BacktestRunTarget) => {
    if (target.mode === 'paper') return loadPaperResult(target.id)
    return loadResult(target.id)
  }

  const clearSelectedRun = () => {
    selectedRun.value = null
    selectedRunMode.value = null
    clearChart()
  }

  const stopPaperRun = async (runId: number) => {
    try {
      await backtestApi.stopPaperRun(runId)
      await fetchPaperHistory()
      if (selectedRunMode.value === 'paper' && selectedRun.value?.id === runId) {
        await loadPaperResult(runId)
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      alert(`${t('backtest.paperStopFailed')}: ${detail}`)
    }
  }

  const clearDeletedSelection = (runId: number, mode: BacktestRunMode) => {
    if (mode === 'backtest') {
      compareRunIds.value = compareRunIds.value.filter((item) => item !== runId)
    }
    if (selectedRun.value?.id === runId && selectedRunMode.value === mode) {
      clearSelectedRun()
    }
  }

  const deleteRun = async (runId: number, mode: BacktestRunMode) => {
    const confirmed = window.confirm(
      mode === 'paper'
        ? t('backtest.confirmDeletePaperRun')
        : t('backtest.confirmDeleteRun')
    )
    if (!confirmed) return

    try {
      if (mode === 'paper') {
        await backtestApi.deletePaperRun(runId)
        clearDeletedSelection(runId, 'paper')
        await fetchPaperHistory()
        return
      }

      await backtestApi.deleteRun(runId)
      clearDeletedSelection(runId, 'backtest')
      await fetchHistory()
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      alert(
        mode === 'paper'
          ? `${t('backtest.deletePaperRunFailed')}: ${detail}`
          : `${t('backtest.deleteRunFailed')}: ${detail}`
      )
    }
  }

  const refreshPaperSelection = async () => {
    if (paperSelectionRefreshPromise) return paperSelectionRefreshPromise
    paperSelectionRefreshPromise = (async () => {
      await fetchPaperHistory()
      if (selectedRunMode.value === 'paper' && selectedRun.value?.id) {
        await loadPaperResult(selectedRun.value.id)
      }
    })().finally(() => {
      paperSelectionRefreshPromise = null
    })
    return paperSelectionRefreshPromise
  }

  const startPaperHistoryPolling = (intervalMs = PAPER_HISTORY_REFRESH_INTERVAL_MS) => {
    if (paperRefreshTimer !== null) return
    paperRefreshTimer = window.setInterval(() => {
      refreshPaperSelection().catch((error) => console.error(error))
    }, intervalMs)
  }

  const stopPaperHistoryPolling = () => {
    if (paperRefreshTimer === null) return
    window.clearInterval(paperRefreshTimer)
    paperRefreshTimer = null
  }

  return {
    fetchHistory,
    fetchPaperHistory,
    loadResult,
    loadPaperResult,
    loadRunTarget,
    clearSelectedRun,
    stopPaperRun,
    deleteRun,
    refreshPaperSelection,
    startPaperHistoryPolling,
    stopPaperHistoryPolling,
  }
}


