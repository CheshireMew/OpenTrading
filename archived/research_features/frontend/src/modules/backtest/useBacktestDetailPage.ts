import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useTheme } from '@/composables/useTheme'
import type { BacktestRunResponse, StrategyDefinitionResponse, StrategyEvolutionResponse, StrategyVersionResponse } from './contracts'

import { backtestApi } from './api'
import { profitColorClass } from './selection'
import { useBacktestRuns, type BacktestRunMode } from './useBacktestRuns'
import { defineReactiveView, type BacktestDetailHeroView, type BacktestHistoryPanelView, type BacktestResultPanelView } from './viewTypes'


export const useBacktestDetailPage = () => {
  const { t } = useI18n()
  const { theme } = useTheme()
  const route = useRoute()
  const router = useRouter()

  const strategies = ref<StrategyDefinitionResponse[]>([])
  const evolutionLoading = ref(false)
  const evolutionResult = ref<StrategyEvolutionResponse | null>(null)
  const config = reactive({
    strategy_key: '',
    strategy_version: 1,
  })

  const isDark = computed(() => theme.value === 'dark')
  const chartColors = computed(() => ({
    bg: isDark.value ? '#1f2937' : '#ffffff',
    grid: isDark.value ? '#374151' : '#e5e7eb',
    text: isDark.value ? '#9ca3af' : '#4b5563',
    upColor: '#10b981',
    downColor: '#ef4444',
  }))

  const selectedStrategy = computed<StrategyDefinitionResponse | null>(() => strategies.value.find((item) => item.key === config.strategy_key) || null)
  const selectedStrategyVersions = computed<StrategyVersionResponse[]>(() => {
    const versions = selectedStrategy.value?.versions
    if (!Array.isArray(versions)) return []
    return versions.filter(Boolean)
  })

  const runs = useBacktestRuns({
    t,
    config,
    selectedStrategyVersions,
  })

  const fetchStrategies = async () => {
    try {
      const res = await backtestApi.listStrategies()
      strategies.value = res
    } catch (error) {
      console.error(error)
    }
  }

  const syncConfigFromSelectedRun = () => {
    const metadata = runs.selectedRun.value?.metadata
    config.strategy_key = metadata?.strategy_key || ''
    config.strategy_version = Number(metadata?.strategy_version || 1)
  }

  const currentTarget = computed(() => {
    const mode = route.params.mode === 'paper' ? 'paper' : 'backtest'
    const id = Number(route.params.id)
    if (!Number.isFinite(id) || id <= 0) return null
    return { id, mode: mode as BacktestRunMode }
  })

  const loadCurrentTarget = async () => {
    const target = currentTarget.value
    if (!target) {
      runs.clearSelectedRun()
      return
    }
    const result = await runs.loadRunTarget(target)
    if (!result) return
    evolutionResult.value = null
    syncConfigFromSelectedRun()
  }

  const openRunDetail = (run: BacktestRunResponse, mode: 'backtest' | 'paper' = runs.historyMode.value) => {
    if (!run?.id) return
    const path = mode === 'paper' ? `/backtest/paper/${run.id}` : `/backtest/runs/${run.id}`
    if (router.currentRoute.value.fullPath === path) {
      loadCurrentTarget().catch((error) => console.error(error))
      return
    }
    router.push(path)
  }

  const goBackToCenter = () => {
    router.push('/backtest')
  }

  const deleteRun = async (runId: number, mode: BacktestRunMode) => {
    const deletingCurrentRun = currentTarget.value?.id === runId && currentTarget.value?.mode === mode
    await runs.deleteRun(runId, mode)
    if (deletingCurrentRun && runs.selectedRun.value === null) {
      goBackToCenter()
    }
  }

  const evolveStrategy = async () => {
    const run = runs.selectedRun.value
    if (!run?.id || runs.isPaperRun.value || evolutionLoading.value) return
    evolutionLoading.value = true
    try {
      const res = await backtestApi.evolveStrategyFromBacktest(run.id, {
        make_default: true,
        dry_run: false,
      })
      evolutionResult.value = res
      await fetchStrategies()
    } catch (error) {
      console.error(error)
    } finally {
      evolutionLoading.value = false
    }
  }

  onMounted(async () => {
    await Promise.all([fetchStrategies(), runs.fetchHistory(), runs.fetchPaperHistory()])
    await loadCurrentTarget()
    runs.startPaperHistoryPolling()
  })

  watch(
    () => [route.params.mode, route.params.id],
    () => {
      loadCurrentTarget().catch((error) => console.error(error))
    },
  )

  onBeforeUnmount(() => {
    runs.stopPaperHistoryPolling()
  })

  const hero = defineReactiveView<BacktestDetailHeroView>({
    selectedRun: runs.selectedRun,
    isPaperRun: runs.isPaperRun,
    goBackToCenter,
    portfolioLabel: runs.portfolioLabel,
    runStatusLabel: runs.runStatusLabel,
  })

  const historyPanel = defineReactiveView<BacktestHistoryPanelView>({
    historyMode: runs.historyMode,
    enableHistoryCompare: true,
    visibleHistory: runs.visibleHistory,
    compareRunIds: runs.compareRunIds,
    openRunDetail,
    toggleCompareRun: runs.toggleCompareRun,
    portfolioLabel: runs.portfolioLabel,
    runStatusLabel: runs.runStatusLabel,
    profitColorClass,
    stopPaperRun: runs.stopPaperRun,
    deleteRun,
  })

  const resultPanel = defineReactiveView<BacktestResultPanelView>({
    selectedRun: runs.selectedRun,
    isPaperRun: runs.isPaperRun,
    isDark,
    chartColors,
    chartData: runs.chartData,
    pairBreakdown: runs.pairBreakdown,
    optimizationTrials: runs.optimizationTrials,
    rollingWindows: runs.rollingWindows,
    evolutionLoading,
    evolutionResult,
    selectedCompareRuns: runs.selectedCompareRuns,
    recentRunCompare: runs.recentRunCompare,
    versionCompareOptions: runs.versionCompareOptions,
    versionCompareSelections: runs.versionCompareSelections,
    selectedVersionCompareRuns: runs.selectedVersionCompareRuns,
    versionRunCompare: runs.versionRunCompare,
    profitColorClass,
    runStatusLabel: runs.runStatusLabel,
    portfolioLabel: runs.portfolioLabel,
    joinSymbols: runs.joinSymbols,
    configLabel: runs.configLabel,
    compareRunLabel: runs.compareRunLabel,
    toggleVersionCompare: runs.toggleVersionCompare,
    evolveStrategy,
  })

  return {
    hero,
    historyPanel,
    resultPanel,
  }
}


export type BacktestDetailPageState = ReturnType<typeof useBacktestDetailPage>


