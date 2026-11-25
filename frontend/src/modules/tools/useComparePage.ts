import { DARK_PALETTE } from '@/theme/palette.mjs'
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, reactive, ref, watch, type WatchStopHandle } from 'vue'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import { ensureSymbolCatalogLoaded, isIndexSymbol } from '@/modules/market'
import type { CandlestickData } from '@/modules/market/contracts'
import type { MarketSymbolSearchResponse } from '@/modules/market/contracts'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useRequestError } from '@/composables/useRequestError'
import { toolsApi } from './api'
import { buildCompareSnapshot, createDefaultCompareSnapshot, createEmptyCompareSnapshot, normalizeCompareSnapshot } from './pageSnapshots'

interface SyncableChart {
  timeScale: () => {
    getVisibleLogicalRange: () => { from: number; to: number } | null
    setVisibleLogicalRange: (range: unknown) => void
    subscribeVisibleLogicalRangeChange: (handler: (range: unknown) => void) => void
    unsubscribeVisibleLogicalRangeChange: (handler: (range: unknown) => void) => void
  }
}

interface ChartComponentRef {
  chart?: SyncableChart | null
  isVisible?: () => boolean
  isResizing?: () => boolean
  setVisibleLogicalRange?: (range: { from: number; to: number }) => void
}

export function useComparePage() {
  const { theme } = useTheme()
  const { t } = useI18n()
  const route = useRoute()
  const pageSnapshot = createPersistentPageSnapshot(PAGE_SNAPSHOT_KEYS.compare, normalizeCompareSnapshot, createEmptyCompareSnapshot())
  const restoredSnapshot = pageSnapshot.initial
  let snapshotStop: WatchStopHandle | null = null
  let disposed = false

  const chartColors = computed(() => {
    const isDark = theme.value === 'dark'
    return {
      bg: isDark ? DARK_PALETTE.canvas : '#ffffff',
      grid: isDark ? DARK_PALETTE.grid : '#e5e7eb',
      text: isDark ? DARK_PALETTE.muted : '#4b5563',
      upColor: '#3b82f6',
      downColor: '#1d4ed8',
    }
  })

  const config = reactive(createEmptyCompareSnapshot().config)

  const loading = ref(false)
  const initialized = ref(false)
  const { error: errorMessage, setError, clearError } = useRequestError(t)
  const initializing = ref(false)
  const ready = ref(false)
  const dataA = ref<CandlestickData[]>([])
  const dataB = ref<CandlestickData[]>([])
  const dataRatio = ref<CandlestickData[]>([])
  const chartARef = ref<ChartComponentRef | null>(null)
  const chartBRef = ref<ChartComponentRef | null>(null)
  const chartRatioRef = ref<ChartComponentRef | null>(null)
  const syncUnsubscribers = ref<Array<() => void>>([])
  const resultSymbols = reactive({ symbolA: '', symbolB: '' })
  const statistics = ref<Awaited<ReturnType<typeof toolsApi.comparePairs>>['statistics'] | null>(null)
  const hasData = computed(() => dataA.value.length > 0 && dataB.value.length > 0 && dataRatio.value.length > 0)
  let inputVersion = 0, requestVersion = 0
  let requestController: AbortController | undefined
  watch(config, () => {
    inputVersion++
    if (requestController) { requestController.abort(); requestController = undefined; loading.value = false }
    dataA.value = []; dataB.value = []; dataRatio.value = []; statistics.value = null
    resultSymbols.symbolA = ''; resultSymbols.symbolB = ''
  }, { deep: true, flush: 'sync' })

  const syncCharts = () => {
    syncUnsubscribers.value.forEach((fn) => fn())
    syncUnsubscribers.value = []

    const chartA = chartARef.value?.chart
    const chartB = chartBRef.value?.chart
    const chartRatio = chartRatioRef.value?.chart
    if (!chartA || !chartB || !chartRatio) {
      return
    }

    const charts = [chartA, chartB, chartRatio]
    const refs = [chartARef, chartBRef, chartRatioRef]
    const initialRange = { from: -0.5, to: Math.max(0.5, dataRatio.value.length - 0.5) }
    refs.forEach(chartRef => chartRef.value?.setVisibleLogicalRange?.(initialRange))
    let synchronizing = false
    charts.forEach((sourceChart, index) => {
      const handler = (range: unknown) => {
        const next = range as { from: number; to: number } | null
        if (!next || synchronizing || !refs[index]?.value?.isVisible?.() || refs[index]?.value?.isResizing?.()
          || !Number.isFinite(next.from) || !Number.isFinite(next.to) || next.to <= next.from) return
        synchronizing = true
        try {
          charts.forEach((targetChart, targetIndex) => {
            const current = targetChart.timeScale().getVisibleLogicalRange()
            if (targetChart !== sourceChart && (!current
              || Math.abs(current.from - next.from) > 0.00001 || Math.abs(current.to - next.to) > 0.00001)) {
              refs[targetIndex]?.value?.setVisibleLogicalRange?.(next)
            }
          })
        } finally { synchronizing = false }
      }
      sourceChart.timeScale().subscribeVisibleLogicalRangeChange(handler)
      syncUnsubscribers.value.push(() => {
        try {
          sourceChart.timeScale().unsubscribeVisibleLogicalRangeChange(handler)
        } catch {}
      })
    })
  }

  const fetchComparisonData = async () => {
    if (disposed) return
    if (!canCompare.value) {
      setError(null, 'compare.invalidConfig')
      return
    }
    loading.value = true
    requestController?.abort(); requestController = undefined
    const request = ++requestVersion
    let inputs = inputVersion
    const current = () => !disposed && request === requestVersion && inputs === inputVersion
    clearError()
    dataA.value = []
    dataB.value = []
    dataRatio.value = []
    statistics.value = null
    try {
      await ensureSymbolCatalogLoaded()
      if (!current()) return
      if (isIndexSymbol(config.symbolA) || isIndexSymbol(config.symbolB)) {
        config.timeframe = '1d'
      }
      inputs = inputVersion
      const payload = {
        symbol_a: config.symbolA,
        symbol_b: config.symbolB,
        days: config.days,
        timeframe: config.timeframe,
      }
      const controller = requestController = new AbortController()
      const response = await toolsApi.comparePairs(payload, controller.signal)
      if (!current()) return
      dataA.value = response.data_a || []
      dataB.value = response.data_b || []
      dataRatio.value = response.ratio_ohlc || []
      resultSymbols.symbolA = payload.symbol_a
      resultSymbols.symbolB = payload.symbol_b
      statistics.value = response.statistics
      nextTick(() => {
        if (current()) syncCharts()
      })
    } catch (error) {
      console.error('Comparison fetch failed', error)
      if (current()) setError(error, 'compare.loadFailed')
    } finally {
      if (request === requestVersion) { loading.value = false; requestController = undefined }
    }
  }

  const handleSymbolSelect = (item: MarketSymbolSearchResponse) => {
    if (item.asset_class === 'index') config.timeframe = '1d'
  }

  const symbolLabel = (symbol: string) => isIndexSymbol(symbol) ? symbol : `${symbol}/USDT`

  const applyRouteInputs = () => {
    const previous = JSON.stringify(config)
    const queryDays = Number(route.query.days)
    if (typeof route.query.symbol_a === 'string' && route.query.symbol_a) config.symbolA = route.query.symbol_a
    if (typeof route.query.symbol_b === 'string' && route.query.symbol_b) config.symbolB = route.query.symbol_b
    if (Number.isFinite(queryDays) && queryDays >= 1 && queryDays <= 90) config.days = queryDays
    if (typeof route.query.timeframe === 'string' && ['5m', '15m', '1h', '4h', '1d', '1w', '1M'].includes(route.query.timeframe)) config.timeframe = route.query.timeframe
    return previous !== JSON.stringify(config)
  }
  const applyActiveRoute = () => {
    if (route.name === 'Compare' && ready.value && applyRouteInputs() && canCompare.value) void fetchComparisonData()
  }
  onActivated(applyActiveRoute)
  watch(() => [route.name, route.query.symbol_a, route.query.symbol_b, route.query.days, route.query.timeframe], applyActiveRoute)

  const initialize = async () => {
    if (initializing.value || disposed) return
    initializing.value = true
    clearError()
    try {
      const [response] = await Promise.all([
        toolsApi.getContract(),
        ensureSymbolCatalogLoaded(),
      ])
      if (disposed) return
      const defaultSnapshot = createDefaultCompareSnapshot(response)
      Object.assign(
        config,
        pageSnapshot.hasStoredData
          ? normalizeCompareSnapshot(restoredSnapshot, defaultSnapshot).config
          : defaultSnapshot.config,
      )
      applyRouteInputs()
      if (!snapshotStop) {
        snapshotStop = pageSnapshot.bind(
          config,
          () => buildCompareSnapshot(config, defaultSnapshot),
        )
      }
      ready.value = true
      if (canCompare.value) await fetchComparisonData()
    } catch (error) {
      if (!disposed) setError(error, 'compare.initializeFailed')
    } finally {
      initialized.value = true
      initializing.value = false
    }
  }
  onMounted(() => { void initialize() })

  onBeforeUnmount(() => {
    disposed = true
    requestController?.abort()
    snapshotStop?.()
    snapshotStop = null
    syncUnsubscribers.value.forEach((fn) => fn())
    syncUnsubscribers.value = []
  })

  const canCompare = computed(() => (
    Boolean(config.symbolA)
    && Boolean(config.symbolB)
    && config.symbolA !== config.symbolB
    && Number.isFinite(config.days)
    && config.days >= 1
    && config.days <= 90
    && ['5m', '15m', '1h', '4h', '1d', '1w', '1M'].includes(config.timeframe)
  ))

  return {
    chartColors,
    config,
    loading,
    initialized,
    initializing,
    ready,
    initialize,
    errorMessage,
    hasData,
    resultSymbols,
    dataA,
    dataB,
    dataRatio,
    statistics,
    chartARef,
    chartBRef,
    chartRatioRef,
    fetchComparisonData,
    handleSymbolSelect,
    symbolLabel,
    canCompare,
  }
}

