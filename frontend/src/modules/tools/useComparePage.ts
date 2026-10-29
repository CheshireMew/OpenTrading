import { DARK_PALETTE } from '@/theme/palette.mjs'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, type WatchStopHandle } from 'vue'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import { ensureSymbolCatalogLoaded, isIndexSymbol } from '@/modules/market'
import type { CandlestickData } from '@/modules/market/contracts'
import type { MarketSymbolSearchResponse } from '@/modules/market/contracts'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { apiErrorMessage } from '@/api/request'
import { toolsApi } from './api'
import { buildCompareSnapshot, createDefaultCompareSnapshot, createEmptyCompareSnapshot, normalizeCompareSnapshot } from './pageSnapshots'

interface SyncableChart {
  timeScale: () => {
    setVisibleLogicalRange: (range: unknown) => void
    subscribeVisibleLogicalRangeChange: (handler: (range: unknown) => void) => void
    unsubscribeVisibleLogicalRangeChange: (handler: (range: unknown) => void) => void
  }
}

interface ChartComponentRef {
  chart?: SyncableChart | null
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
  const errorMessage = ref('')
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
    charts.forEach((sourceChart) => {
      const handler = (range: unknown) => {
        if (!range) {
          return
        }
        charts.forEach((targetChart) => {
          if (sourceChart !== targetChart) {
            targetChart.timeScale().setVisibleLogicalRange(range)
          }
        })
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
    if (!canCompare.value) {
      errorMessage.value = t('compare.invalidConfig')
      return
    }
    loading.value = true
    errorMessage.value = ''
    dataA.value = []
    dataB.value = []
    dataRatio.value = []
    statistics.value = null
    try {
      await ensureSymbolCatalogLoaded()
      if (isIndexSymbol(config.symbolA) || isIndexSymbol(config.symbolB)) {
        config.timeframe = '1d'
      }
      const response = await toolsApi.comparePairs({
        symbol_a: config.symbolA,
        symbol_b: config.symbolB,
        days: config.days,
        timeframe: config.timeframe,
      })
      dataA.value = response.data_a || []
      dataB.value = response.data_b || []
      dataRatio.value = response.ratio_ohlc || []
      resultSymbols.symbolA = config.symbolA
      resultSymbols.symbolB = config.symbolB
      statistics.value = response.statistics
      nextTick(() => {
        syncCharts()
      })
    } catch (error) {
      console.error('Comparison fetch failed', error)
      errorMessage.value = apiErrorMessage(error, t('compare.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  const handleSymbolSelect = (item: MarketSymbolSearchResponse) => {
    if (item.asset_class === 'index') config.timeframe = '1d'
  }

  const symbolLabel = (symbol: string) => isIndexSymbol(symbol) ? symbol : `${symbol}/USDT`

  onMounted(async () => {
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
      const queryDays = Number(route.query.days)
      if (typeof route.query.symbol_a === 'string' && route.query.symbol_a) config.symbolA = route.query.symbol_a
      if (typeof route.query.symbol_b === 'string' && route.query.symbol_b) config.symbolB = route.query.symbol_b
      if (Number.isFinite(queryDays) && queryDays >= 1 && queryDays <= 90) config.days = queryDays
      if (typeof route.query.timeframe === 'string' && ['5m', '15m', '1h', '4h', '1d', '1w', '1M'].includes(route.query.timeframe)) config.timeframe = route.query.timeframe
      if (!snapshotStop) {
        snapshotStop = pageSnapshot.bind(
          config,
          () => buildCompareSnapshot(config, defaultSnapshot),
        )
      }
      if (canCompare.value) await fetchComparisonData()
    } catch (error) {
      errorMessage.value = apiErrorMessage(error, t('compare.initializeFailed'))
    } finally {
      initialized.value = true
    }
  })

  onBeforeUnmount(() => {
    disposed = true
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

