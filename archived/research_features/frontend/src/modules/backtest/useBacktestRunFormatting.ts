import { computed, type ComputedRef, type Ref } from 'vue'

import type {
  BacktestDetailResponse,
  BacktestRunResponse,
  BacktestOptimizationTrialResponse,
  BacktestPairBreakdownResponse,
  BacktestRollingWindowResponse,
  StrategyVersionResponse,
} from './contracts'

import { asNumber } from '@/utils/number'
import type {
  BacktestComparisonChart,
  BacktestDisplayRun,
  BacktestRunSelectionConfig,
  BacktestVersionCompareOption,
} from './viewTypes'


interface UseBacktestRunFormattingOptions {
  t: (key: string) => string
  config: BacktestRunSelectionConfig
  selectedStrategyVersions: ComputedRef<StrategyVersionResponse[]>
  history: Ref<BacktestRunResponse[]>
  paperHistory: Ref<BacktestRunResponse[]>
  historyMode: Ref<'backtest' | 'paper'>
  selectedRun: Ref<BacktestDetailResponse | null>
  selectedRunMode: Ref<'backtest' | 'paper' | null>
  compareRunIds: Ref<number[]>
  versionCompareSelections: Ref<number[]>
}

export const useBacktestRunFormatting = ({
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
}: UseBacktestRunFormattingOptions) => {
  const visibleHistory = computed<BacktestRunResponse[]>(() => (historyMode.value === 'paper' ? paperHistory.value : history.value))
  const isPaperRun = computed(() => selectedRunMode.value === 'paper' || selectedRun.value?.metadata?.execution_mode === 'paper_live')
  const pairBreakdown = computed<BacktestPairBreakdownResponse[]>(() => selectedRun.value?.report?.pair_breakdown || [])
  const optimizationTrials = computed<BacktestOptimizationTrialResponse[]>(() => (isPaperRun.value ? [] : (selectedRun.value?.report?.research?.optimization?.trials || [])))
  const rollingWindows = computed<BacktestRollingWindowResponse[]>(() => (isPaperRun.value ? [] : (selectedRun.value?.report?.research?.rolling_windows || [])))
  const selectedCompareRuns = computed<BacktestRunResponse[]>(() => compareRunIds.value.map((id) => history.value.find((run) => run.id === id)).filter((run): run is BacktestRunResponse => Boolean(run)))
  const latestRunsByVersion = computed(() => {
    const runs = [...history.value]
      .filter((run) => run.metadata?.strategy_key === config.strategy_key && run.metadata?.strategy_version)
      .sort((left, right) => {
        const leftTime = new Date(left.created_at || 0).getTime()
        const rightTime = new Date(right.created_at || 0).getTime()
        if (leftTime !== rightTime) return rightTime - leftTime
        return right.id - left.id
      })
    const map = new Map()
    for (const run of runs) {
      const version = Number(run.metadata?.strategy_version)
      if (!map.has(version)) map.set(version, run)
    }
    return map as Map<number, BacktestRunResponse>
  })
  const versionCompareOptions = computed<BacktestVersionCompareOption[]>(() => selectedStrategyVersions.value
    .map((version) => {
      const run = latestRunsByVersion.value.get(version.version)
      return run ? { version: version.version, name: version.name, run } : null
    })
    .filter((item): item is BacktestVersionCompareOption => item !== null))
  const selectedVersionCompareRuns = computed<BacktestRunResponse[]>(() => versionCompareSelections.value
    .map((version) => versionCompareOptions.value.find((item) => item.version === version)?.run)
    .filter((run): run is BacktestRunResponse => Boolean(run)))

  const buildComparisonChart = (runs: BacktestRunResponse[], labeler: (run: BacktestRunResponse) => string): BacktestComparisonChart => ({
    performance: {
      categories: runs.map(labeler),
      series: [
        { name: t('backtest.totalReturn'), color: '#2563eb', data: runs.map((run) => asNumber(run.report?.profit_pct) ?? 0) },
        { name: t('backtest.maxDrawdown'), color: '#ef4444', data: runs.map((run) => asNumber(run.report?.max_drawdown_pct) ?? 0) },
      ],
    },
    quality: {
      categories: runs.map(labeler),
      series: [
        { name: t('backtest.sharpe'), color: '#14b8a6', data: runs.map((run) => asNumber(run.report?.sharpe) ?? 0) },
        { name: t('backtest.winRate'), color: '#8b5cf6', data: runs.map((run) => asNumber(run.report?.win_rate) ?? 0) },
      ],
    },
  })

  const compareRunLabel = (run: BacktestDisplayRun) => `#${run.id} · v${run.metadata?.strategy_version || '-'}`
  const recentRunCompare = computed(() => buildComparisonChart(selectedCompareRuns.value, compareRunLabel))
  const versionRunCompare = computed(() => buildComparisonChart(selectedVersionCompareRuns.value, (run) => `v${run.metadata?.strategy_version || '-'}`))

  const toggleCompareRun = (runId: number) => {
    if (compareRunIds.value.includes(runId)) {
      compareRunIds.value = compareRunIds.value.filter((item) => item !== runId)
      return
    }
    compareRunIds.value = [...compareRunIds.value, runId]
  }

  const toggleVersionCompare = (version: number) => {
    if (versionCompareSelections.value.includes(version)) {
      versionCompareSelections.value = versionCompareSelections.value.filter((item) => item !== version)
      return
    }
    versionCompareSelections.value = [...versionCompareSelections.value, version]
  }

  const joinSymbols = (symbols: string[] | undefined) => (Array.isArray(symbols) && symbols.length ? symbols.join(', ') : '-')
  const portfolioLabel = (run: BacktestDisplayRun) => run?.metadata?.portfolio_label || joinSymbols(run?.metadata?.symbols) || run?.symbol || '-'
  const previewValue = (value: unknown) => {
    if (Array.isArray(value)) return `${value.length}项`
    if (value && typeof value === 'object') return `${Object.keys(value as Record<string, unknown>).length}项`
    return value ?? '-'
  }
  const configLabel = (value: Record<string, unknown> | null | undefined) => (
    value
      ? Object.entries(value).slice(0, 3).map(([key, item]) => `${key}:${previewValue(item)}`).join(' · ')
      : '-'
  )
  const runStatusLabel = (run: BacktestDisplayRun) => (run?.status || '-').toUpperCase()

  return {
    visibleHistory,
    isPaperRun,
    pairBreakdown,
    optimizationTrials,
    rollingWindows,
    selectedCompareRuns,
    latestRunsByVersion,
    versionCompareOptions,
    selectedVersionCompareRuns,
    recentRunCompare,
    versionRunCompare,
    toggleCompareRun,
    toggleVersionCompare,
    joinSymbols,
    portfolioLabel,
    configLabel,
    compareRunLabel,
    runStatusLabel,
  }
}



