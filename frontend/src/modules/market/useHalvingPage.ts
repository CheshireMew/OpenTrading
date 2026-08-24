import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Chart } from 'chart.js'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import { useMoney } from '@/composables/useMoney'
import { useTheme } from '@/composables/useTheme'
import { formatMoney as formatDisplayMoney } from '@/modules/format'
import { loadHalvingChartRuntime } from './halvingChartRuntime'
import {
  buildHalvingChartConfig,
  LAST_HALVING_DATE,
  NEXT_HALVING_DATE_TEXT,
  NEXT_HALVING_ESTIMATE,
  ONE_DAY_MS,
} from './halvingTimeline'
import { buildHalvingSnapshot, createDefaultHalvingSnapshot, normalizeHalvingSnapshot } from './pageSnapshots'
import { useHalvingMarketData } from './useHalvingMarketData'


const nextAnimationFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

export function useHalvingPage() {
  const { t } = useI18n()
  const translate = (key: string, params?: Record<string, unknown>) => String(t(key, params ?? {}))
  const { theme } = useTheme()
  const { displayCurrency, toDisplayAmount, formatMoney } = useMoney()
  const marketData = useHalvingMarketData(translate)
  const snapshot = createPersistentPageSnapshot(
    PAGE_SNAPSHOT_KEYS.halving,
    normalizeHalvingSnapshot,
    createDefaultHalvingSnapshot(),
  )
  const chartCanvas = ref<HTMLCanvasElement | null>(null)
  const showPhases = ref(snapshot.initial.showPhases)
  const scaleType = ref<'logarithmic' | 'linear'>(snapshot.initial.scaleType)
  const compactChart = ref(false)
  let chartInstance: Chart | null = null
  let renderToken = 0
  let resizeObserver: ResizeObserver | null = null

  const nextHalvingDate = computed(() => NEXT_HALVING_DATE_TEXT)
  const daysToHalving = computed(() => Math.ceil((NEXT_HALVING_ESTIMATE.getTime() - Date.now()) / ONE_DAY_MS))
  const cycleProgress = computed(() => {
    const totalDuration = NEXT_HALVING_ESTIMATE.getTime() - LAST_HALVING_DATE.getTime()
    const elapsed = Date.now() - LAST_HALVING_DATE.getTime()
    return Math.min(Math.max((elapsed / totalDuration) * 100, 0), 100).toFixed(1)
  })
  const seriesData = computed(() => marketData.historyData.value.map((row) => ({
    x: row.timestamp,
    y: toDisplayAmount(row.close, 'USDT') ?? 0,
  })))

  const syncChart = async () => {
    if (!chartCanvas.value || !seriesData.value.length) return
    const token = ++renderToken
    await nextTick()
    await nextAnimationFrame()
    if (token !== renderToken || !chartCanvas.value) return
    const runtime = await loadHalvingChartRuntime()
    if (token !== renderToken || !chartCanvas.value) return
    const context = chartCanvas.value.getContext('2d')
    if (!context) return

    const config = buildHalvingChartConfig({
      t: translate,
      isDark: theme.value === 'dark',
      showPhases: showPhases.value,
      scaleType: scaleType.value,
      seriesData: seriesData.value,
      formatTick: (value) => formatMoney(value, displayCurrency.value, { maximumFractionDigits: 0 }),
      compact: compactChart.value,
    })
    if (!chartInstance) {
      chartInstance = new runtime.Chart(context, config)
      return
    }
    chartInstance.data = config.data
    chartInstance.options = config.options ?? {}
    chartInstance.update('none')
  }

  watch([seriesData, showPhases, scaleType, theme, displayCurrency, compactChart], () => { void syncChart() }, { deep: true })
  onMounted(() => {
    const container = chartCanvas.value?.parentElement
    if (container) {
      const updateCompact = () => { compactChart.value = container.clientWidth < 640 }
      updateCompact()
      resizeObserver = new ResizeObserver(updateCompact)
      resizeObserver.observe(container)
    }
    void loadHalvingChartRuntime().then(syncChart)
  })
  snapshot.bind(
    [showPhases, scaleType],
    () => buildHalvingSnapshot({ showPhases: showPhases.value, scaleType: scaleType.value }),
  )
  onBeforeUnmount(() => {
    renderToken += 1
    resizeObserver?.disconnect()
    resizeObserver = null
    chartInstance?.destroy()
    chartInstance = null
  })

  return {
    loading: marketData.loading,
    error: marketData.error,
    retry: marketData.retry,
    chartCanvas,
    currentPrice: marketData.currentPrice,
    showPhases,
    scaleType,
    nextHalvingDate,
    daysToHalving,
    cycleProgress,
    formatPrice: (price: number) => formatDisplayMoney(price, 'USDT', { maximumFractionDigits: 2 }),
  }
}
