import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Chart } from 'chart.js'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import { useDateTime } from '@/composables/useDateTime'
import { useMoney } from '@/composables/useMoney'
import { useTheme } from '@/composables/useTheme'
import { formatMoney as formatDisplayMoney } from '@/modules/format'
import { loadHalvingChartRuntime } from './halvingChartRuntime'
import { buildHalvingChartConfig, buildHalvingTimeline, daysUntil } from './halvingTimeline'
import { buildHalvingSnapshot, createDefaultHalvingSnapshot, normalizeHalvingSnapshot } from './pageSnapshots'
import { useHalvingMarketData } from './useHalvingMarketData'


const nextAnimationFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

export function useHalvingPage() {
  const { t } = useI18n()
  const translate = (key: string, params?: Record<string, unknown>) => String(t(key, params ?? {}))
  const { theme } = useTheme()
  const { formatDate } = useDateTime()
  const { displayCurrency, toDisplayAmount, formatMoney } = useMoney()
  const marketData = useHalvingMarketData(translate)
  const snapshot = createPersistentPageSnapshot(
    PAGE_SNAPSHOT_KEYS.halving,
    normalizeHalvingSnapshot,
    createDefaultHalvingSnapshot(),
  )
  const chartCanvas = ref<HTMLCanvasElement | null>(null)
  const chartHeight = ref<number>()
  const showPhases = ref(snapshot.initial.showPhases)
  const scaleType = ref<'logarithmic' | 'linear'>(snapshot.initial.scaleType)
  const compactChart = ref(false)
  const now = ref(Date.now())
  let clockTimer: number | null = null
  let chartInstance: Chart | null = null
  let renderToken = 0
  let resizeObserver: ResizeObserver | null = null
  let resizeFrame = 0

  const timeline = computed(() => buildHalvingTimeline(marketData.halvingEstimate.value))
  const lastHalvingDate = computed(() => new Date(timeline.value.last.timestamp).toISOString().slice(0, 10))
  const nextHalvingDate = computed(() => timeline.value.next ? formatDate(timeline.value.next.timestamp) : null)
  const daysToHalving = computed(() => timeline.value.next ? daysUntil(timeline.value.next.timestamp, now.value) : null)
  const cycleProgress = computed(() => {
    const { last, next } = timeline.value
    if (!next) return null
    const totalDuration = next.timestamp - last.timestamp
    const elapsed = now.value - last.timestamp
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
      timeline: timeline.value,
      now: now.value,
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

  watch([seriesData, showPhases, scaleType, theme, displayCurrency, compactChart, timeline, now], () => {
    void syncChart()
  }, { deep: true })
  onMounted(() => {
    clockTimer = window.setInterval(() => { now.value = Date.now() }, 60_000)
    const container = chartCanvas.value?.parentElement
    if (container) {
      const scrollport = container.closest<HTMLElement>('.app-main')
      const page = container.closest<HTMLElement>('.app-page-inner-wide')
      const updateSize = () => {
        cancelAnimationFrame(resizeFrame)
        resizeFrame = requestAnimationFrame(() => {
          compactChart.value = container.clientWidth < 640
          if (!scrollport || !page || !container.clientWidth) return
          const top = container.getBoundingClientRect().top - scrollport.getBoundingClientRect().top + scrollport.scrollTop
          const panelStyle = getComputedStyle(container.parentElement!)
          const bottom = parseFloat(panelStyle.paddingBottom) + parseFloat(panelStyle.borderBottomWidth) + parseFloat(getComputedStyle(page).paddingBottom)
          const preferred = window.innerWidth >= 1024 ? 600 : window.innerWidth >= 640 ? 520 : 420
          // Keep the chart readable when the content above it fills a small screen.
          chartHeight.value = Math.floor(Math.min(preferred, Math.max(260, scrollport.clientHeight - top - bottom)))
        })
      }
      updateSize()
      resizeObserver = new ResizeObserver(updateSize)
      resizeObserver.observe(container)
      if (scrollport) resizeObserver.observe(scrollport)
      if (page) resizeObserver.observe(page)
    }
    void loadHalvingChartRuntime().then(syncChart)
  })
  onDeactivated(() => {
    if (clockTimer !== null) window.clearInterval(clockTimer)
    clockTimer = null
  })
  onActivated(() => {
    if (clockTimer === null) {
      now.value = Date.now()
      clockTimer = window.setInterval(() => { now.value = Date.now() }, 60_000)
    }
  })
  snapshot.bind(
    [showPhases, scaleType],
    () => buildHalvingSnapshot({ showPhases: showPhases.value, scaleType: scaleType.value }),
  )
  onBeforeUnmount(() => {
    if (clockTimer !== null) window.clearInterval(clockTimer)
    renderToken += 1
    resizeObserver?.disconnect()
    cancelAnimationFrame(resizeFrame)
    resizeObserver = null
    chartInstance?.destroy()
    chartInstance = null
  })

  return {
    loading: marketData.loading,
    error: marketData.error,
    retry: marketData.retry,
    chartCanvas,
    chartHeight,
    currentPrice: marketData.currentPrice,
    currentPriceUpdatedAt: marketData.currentPriceUpdatedAt,
    showPhases,
    scaleType,
    halvingEstimateFailed: marketData.halvingEstimateFailed,
    lastHalvingDate,
    nextHalvingDate,
    daysToHalving,
    cycleProgress,
    formatPrice: (price: number | null) => price === null ? '—' : formatDisplayMoney(price, 'USDT', { maximumFractionDigits: 2 }),
  }
}
