import { computed, onBeforeUnmount, onMounted, reactive, ref, watch, type WatchStopHandle } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import { addDaysToLocalIsoDate, todayLocalIsoDate } from '@/utils/localDate'
import type { BacktestRunResponse, StrategyDefinitionResponse, StrategyEditorContractResponse, StrategyVersionResponse } from './contracts'
import { backtestApi } from './api'
import {
  applyBacktestPageSnapshot,
  buildBacktestPageSnapshot,
  createBacktestPageSnapshotDefaults,
  createEmptyBacktestPageSnapshot,
  normalizeBacktestPageSnapshot,
} from './pageSnapshots'
import { profitColorClass, syncStrategyVersionSelection } from './selection'
import { supportsPaperTrading, supportsVersionEditing } from './templateRuntime'
import { useBacktestRuns } from './useBacktestRuns'
import { defineReactiveView, type BacktestControlPanelView, type BacktestHistoryPanelView } from './viewTypes'

export const useBacktestPage = () => {
  const { t } = useI18n()
  const router = useRouter()
  let snapshotStopHandle: WatchStopHandle | null = null

  const ready = ref(false)
  const editorContract = ref<StrategyEditorContractResponse | null>(null)
  const strategies = ref<StrategyDefinitionResponse[]>([])
  const config = reactive(createEmptyBacktestPageSnapshot().config)

  const selectedStrategy = computed<StrategyDefinitionResponse | null>(() => strategies.value.find((item) => item.key === config.strategy_key) || null)
  const selectedStrategyVersions = computed<StrategyVersionResponse[]>(() => {
    const versions = selectedStrategy.value?.versions
    return Array.isArray(versions) ? versions.filter(Boolean) : []
  })
  const selectedVersion = computed<StrategyVersionResponse | null>(() => selectedStrategyVersions.value.find((item) => item.version === config.strategy_version) || null)
  const canCopyCurrentStrategy = computed(() => Boolean(selectedVersion.value) && Boolean(supportsVersionEditing(selectedStrategy.value)))
  const canStartPaperRun = computed(() => Boolean(supportsPaperTrading(selectedStrategy.value)))
  const strategyCapabilityHint = computed(() => {
    if (!selectedStrategy.value) return ''
    if (!supportsVersionEditing(selectedStrategy.value) && !supportsPaperTrading(selectedStrategy.value)) {
      return t('backtest.scriptedReadonlyHint')
    }
    if (!supportsPaperTrading(selectedStrategy.value)) {
      return t('backtest.paperUnsupportedHint')
    }
    return ''
  })

  const runs = useBacktestRuns({
    t,
    config,
    executionConfig: config,
    selectedStrategyVersions,
  })

  const timeframes = computed(() => (
    editorContract.value?.timeframe_options
      ?.filter((item) => item?.key && item.key !== 'base')
      .map((item) => item.key) || []
  ))
  const optimizeMetrics = computed(() => (
    editorContract.value?.run_defaults?.optimize_metric_options?.map((item) => item.key) || []
  ))

  const syncRunTimeframe = () => {
    const runtime = selectedVersion.value?.runtime
    const preferred = runtime?.preferred_run_timeframe
    if (!preferred) return
    const allowed = new Set(runtime.allowed_run_timeframes || [])
    if (!allowed.size || !allowed.has(config.timeframe)) {
      config.timeframe = preferred
    }
  }

  const syncStrategyVersion = () => {
    const versions = selectedStrategyVersions.value
    if (!versions.length) return
    syncStrategyVersionSelection(config, versions)
    syncRunTimeframe()
    const validVersions = new Set(runs.versionCompareOptions.value.map((item) => item.version))
    runs.versionCompareSelections.value = runs.versionCompareSelections.value.filter((item) => validVersions.has(item))
  }

  const bindSnapshot = (contract: StrategyEditorContractResponse) => {
    const defaults = createBacktestPageSnapshotDefaults(contract.run_defaults)
    const pageSnapshot = createPersistentPageSnapshot(
      PAGE_SNAPSHOT_KEYS.backtest,
      (value) => normalizeBacktestPageSnapshot(value, defaults),
      defaults,
    )
    applyBacktestPageSnapshot(config, pageSnapshot.initial, runs.symbolsText, runs.historyMode)
    snapshotStopHandle?.()
    snapshotStopHandle = pageSnapshot.bind(
      [config, runs.symbolsText, runs.historyMode],
      () => buildBacktestPageSnapshot(config, runs.symbolsText.value, runs.historyMode.value, defaults),
    )
  }

  const hydratePage = async () => {
    const [contractResponse, strategiesResponse] = await Promise.all([
      backtestApi.getEditorContract(),
      backtestApi.listStrategies(),
    ])

    editorContract.value = contractResponse
    bindSnapshot(contractResponse)

    strategies.value = strategiesResponse
    if (strategies.value.length && !strategies.value.find((item) => item.key === config.strategy_key)) {
      config.strategy_key = strategies.value[0].key
    }
    syncStrategyVersion()
    ready.value = true
    await Promise.all([runs.fetchHistory(), runs.fetchPaperHistory()])
  }

  const openCopyEditor = () => {
    if (!selectedStrategy.value || !selectedVersion.value || !canCopyCurrentStrategy.value) return
    router.push({
      path: '/backtest/editor',
      query: {
        mode: 'copy',
        strategy: config.strategy_key,
        version: String(config.strategy_version),
      },
    })
  }

  const openBlankEditor = () => {
    router.push({
      path: '/backtest/editor',
      query: {
        mode: 'blank',
        strategy: config.strategy_key,
      },
    })
  }

  const openRunDetail = (run: BacktestRunResponse, mode: 'backtest' | 'paper' = runs.historyMode.value) => {
    if (!run?.id) return
    router.push(mode === 'paper' ? `/backtest/paper/${run.id}` : `/backtest/runs/${run.id}`)
  }

  const startBacktest = async () => {
    const target = await runs.startBacktest()
    if (!target) return
    router.push(`/backtest/runs/${target.id}`)
  }

  const startPaperRun = async () => {
    if (!canStartPaperRun.value) return
    const target = await runs.startPaperRun()
    if (!target) return
    router.push(`/backtest/paper/${target.id}`)
  }

  onMounted(async () => {
    try {
      await hydratePage()
      runs.startPaperHistoryPolling()
    } catch (error) {
      console.error(error)
    }
  })

  watch(() => config.strategy_key, () => {
    runs.clearPreview()
    syncStrategyVersion()
  })

  watch(() => config.strategy_version, () => {
    runs.clearPreview()
    syncRunTimeframe()
  })

  watch(
    () => [
      config.timeframe,
      config.start_date,
      config.end_date,
      config.initial_cash,
      config.fee_rate,
      config.portfolio.max_open_trades,
      config.portfolio.position_size_pct,
      config.portfolio.stake_mode,
      config.research.slippage_bps,
      config.research.funding_rate_daily,
      config.research.in_sample_ratio,
      config.research.optimize_metric,
      config.research.optimize_trials,
      config.research.rolling_windows,
      runs.symbolsText.value,
    ],
    () => {
      runs.clearPreview()
    },
  )

  watch(() => config.start_date, (value) => {
    if (!value) return
    if (!config.end_date || config.end_date <= value) {
      config.end_date = addDaysToLocalIsoDate(value, 1)
    }
  })

  watch(() => config.end_date, (value) => {
    if (!value || !config.start_date) return
    if (value <= config.start_date) {
      config.start_date = addDaysToLocalIsoDate(value, -1)
    }
  })

  onBeforeUnmount(() => {
    snapshotStopHandle?.()
    runs.stopPaperHistoryPolling()
  })

  const controlPanel = defineReactiveView<BacktestControlPanelView>({
    config,
    today: todayLocalIsoDate(),
    ready,
    strategies,
    selectedStrategy,
    selectedStrategyVersions,
    selectedVersion,
    canCopyCurrentStrategy,
    canStartPaperRun,
    strategyCapabilityHint,
    timeframes,
    optimizeMetrics,
    symbolsText: runs.symbolsText,
    backtestLoading: runs.backtestLoading,
    previewLoading: runs.previewLoading,
    paperLoading: runs.paperLoading,
    isBusy: runs.isBusy,
    strategyPreview: runs.strategyPreview,
    previewSymbol: runs.previewSymbol,
    previewSymbols: runs.previewSymbols,
    previewChartData: runs.previewChartData,
    previewMarkers: runs.previewMarkers,
    syncStrategyVersion,
    openCopyEditor,
    openBlankEditor,
    previewBacktest: runs.previewBacktest,
    startBacktest,
    startPaperRun,
  })

  const historyPanel = defineReactiveView<BacktestHistoryPanelView>({
    historyMode: runs.historyMode,
    enableHistoryCompare: false,
    visibleHistory: runs.visibleHistory,
    compareRunIds: runs.compareRunIds,
    openRunDetail,
    toggleCompareRun: runs.toggleCompareRun,
    portfolioLabel: runs.portfolioLabel,
    runStatusLabel: runs.runStatusLabel,
    profitColorClass,
    stopPaperRun: runs.stopPaperRun,
    deleteRun: runs.deleteRun,
  })

  return {
    ready,
    controlPanel,
    historyPanel,
  }
}

export type BacktestPageState = ReturnType<typeof useBacktestPage>


