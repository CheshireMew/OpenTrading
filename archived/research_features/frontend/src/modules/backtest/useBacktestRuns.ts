import { computed, ref, type ComputedRef } from 'vue'

import type { BacktestDetailResponse, BacktestRunResponse, StrategyVersionResponse } from './contracts'

import { useBacktestRunChart } from './useBacktestRunChart'
import { useBacktestRunExecution } from './useBacktestRunExecution'
import { useBacktestRunFormatting } from './useBacktestRunFormatting'
import { useBacktestRunHistory } from './useBacktestRunHistory'
import type { BacktestPageConfig, BacktestRunSelectionConfig } from './viewTypes'

export type BacktestRunMode = 'backtest' | 'paper'

interface UseBacktestRunsOptions {
  t: (key: string) => string
  config: BacktestRunSelectionConfig
  executionConfig?: BacktestPageConfig
  selectedStrategyVersions: ComputedRef<StrategyVersionResponse[]>
}

export const useBacktestRuns = ({
  t,
  config,
  executionConfig,
  selectedStrategyVersions,
}: UseBacktestRunsOptions) => {
  const backtestLoading = ref(false)
  const paperLoading = ref(false)
  const previewLoading = ref(false)
  const history = ref<BacktestRunResponse[]>([])
  const paperHistory = ref<BacktestRunResponse[]>([])
  const historyMode = ref<'backtest' | 'paper'>('backtest')
  const selectedRun = ref<BacktestDetailResponse | null>(null)
  const selectedRunMode = ref<'backtest' | 'paper' | null>(null)
  const symbolsText = ref('BTC/USDT, ETH/USDT')
  const compareRunIds = ref<number[]>([])
  const versionCompareSelections = ref<number[]>([])

  const chart = useBacktestRunChart()
  const formatting = useBacktestRunFormatting({
    t,
    config,
    selectedStrategyVersions,
    history,
    paperHistory,
    historyMode,
    selectedRun,
    selectedRunMode,
    compareRunIds,
    versionCompareSelections,
  })
  const historyActions = useBacktestRunHistory({
    t,
    history,
    paperHistory,
    historyMode,
    selectedRun,
    selectedRunMode,
    compareRunIds,
    versionCompareSelections,
    versionCompareOptions: formatting.versionCompareOptions,
    loadChart: chart.loadChart,
    clearChart: chart.clearChart,
  })
  const execution = executionConfig
    ? useBacktestRunExecution({
        t,
        config: executionConfig,
        backtestLoading,
        paperLoading,
        historyMode,
        symbolsText,
        fetchHistory: historyActions.fetchHistory,
        fetchPaperHistory: historyActions.fetchPaperHistory,
      })
    : {
        previewLoading,
        strategyPreview: ref(null),
        previewSymbol: ref(''),
        previewSymbols: computed(() => []),
        previewChartData: computed(() => ({ candles: [], volume: [], markers: [] })),
        previewMarkers: computed(() => []),
        buildPreviewPayload: () => null,
        buildPayload: () => null,
        buildPaperPayload: () => null,
        clearPreview: () => undefined,
        previewBacktest: async () => null,
        startBacktest: async () => null,
        startPaperRun: async () => null,
      }
  return {
    backtestLoading,
    paperLoading,
    isBusy: computed(() => backtestLoading.value || paperLoading.value || execution.previewLoading.value),
    history,
    paperHistory,
    historyMode,
    selectedRun,
    selectedRunMode,
    chartData: chart.chartData,
    symbolsText,
    compareRunIds,
    versionCompareSelections,
    ...formatting,
    ...historyActions,
    ...execution,
  }
}


