import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Chart, ChartConfiguration, ChartDataset } from 'chart.js'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import { useTheme } from '@/composables/useTheme'
import { useMoney } from '@/composables/useMoney'
import { formatMoney as formatDisplayMoney } from '@/modules/format'
import type { OhlcvPointResponse } from './contracts'
import { marketHistoryApi } from './api'
import { buildHalvingSnapshot, createDefaultHalvingSnapshot, normalizeHalvingSnapshot } from './pageSnapshots'
import { parseLocalIsoDate } from '@/utils/localDate'
import { usePriceHistoryStore } from './priceHistoryStore'

interface HalvingChartRuntime {
  Chart: typeof import('chart.js').Chart
}

type HalvingAnnotationMap = Record<string, Record<string, unknown>>

const HALVING_DATES = [
  { date: '2012-11-28', label: 'H1' },
  { date: '2016-07-09', label: 'H2' },
  { date: '2020-05-11', label: 'H3' },
  { date: '2024-04-20', label: 'H4' },
  { date: '2028-04-17', label: 'H5 (Est)', future: true },
] as const

const LAST_HALVING_DATE_TEXT = '2024-04-20'
const NEXT_HALVING_DATE_TEXT = '2028-04-17'
const LAST_HALVING_DATE = parseLocalIsoDate(LAST_HALVING_DATE_TEXT) ?? new Date(2024, 3, 20)
const NEXT_HALVING_ESTIMATE = parseLocalIsoDate(NEXT_HALVING_DATE_TEXT) ?? new Date(2028, 3, 17)
const ONE_DAY = 24 * 60 * 60 * 1000
const CURRENT_PRICE_REFRESH_INTERVAL_MS = 15_000
const HALVING_PRICE_SYMBOL = 'BTC/USDT'
const HALVING_PRICE_TIMEFRAME = '1d'
const HALVING_HISTORY_START_DATE = '2010-07-01'

const nextAnimationFrame = () => new Promise<void>((resolve) => {
  requestAnimationFrame(() => resolve())
})

let halvingChartRuntimePromise: Promise<HalvingChartRuntime> | null = null

const loadHalvingChartRuntime = async (): Promise<HalvingChartRuntime> => {
  if (!halvingChartRuntimePromise) {
    halvingChartRuntimePromise = Promise.all([
      import('chart.js'),
      import('chartjs-plugin-annotation'),
      import('chartjs-adapter-date-fns'),
    ]).then(([chartJs, annotationPlugin]) => {
      chartJs.Chart.register(
        chartJs.LineController,
        chartJs.LineElement,
        chartJs.PointElement,
        chartJs.LinearScale,
        chartJs.LogarithmicScale,
        chartJs.TimeScale,
        chartJs.Tooltip,
        chartJs.Legend,
        chartJs.Decimation,
        annotationPlugin.default,
      )
      return { Chart: chartJs.Chart }
    })
  }
  return halvingChartRuntimePromise
}

export function useHalvingPage() {
  const { t } = useI18n()
  const { theme } = useTheme()
  const { displayCurrency, toDisplayAmount, formatMoney } = useMoney()
  const priceHistoryStore = usePriceHistoryStore()
  const pageSnapshot = createPersistentPageSnapshot(PAGE_SNAPSHOT_KEYS.halving, normalizeHalvingSnapshot, createDefaultHalvingSnapshot())
  const restoredSnapshot = pageSnapshot.initial

  const chartCanvas = ref<HTMLCanvasElement | null>(null)
  const currentPrice = ref(0)
  const showPhases = ref(restoredSnapshot.showPhases)
  const scaleType = ref<'logarithmic' | 'linear'>(restoredSnapshot.scaleType)

  let chartInstance: Chart | null = null
  let renderToken = 0
  let priceRefreshTimer: number | null = null
  let priceRefreshPending = false

  const nextHalvingDate = computed(() => NEXT_HALVING_DATE_TEXT)
  const daysToHalving = computed(() => Math.ceil((NEXT_HALVING_ESTIMATE.getTime() - Date.now()) / ONE_DAY))
  const cycleProgress = computed(() => {
    const totalDuration = NEXT_HALVING_ESTIMATE.getTime() - LAST_HALVING_DATE.getTime()
    const elapsed = Date.now() - LAST_HALVING_DATE.getTime()
    return Math.min(Math.max((elapsed / totalDuration) * 100, 0), 100).toFixed(1)
  })
  const historyResponse = computed(() => (
    priceHistoryStore.readPriceHistory(HALVING_PRICE_SYMBOL, HALVING_PRICE_TIMEFRAME, HALVING_HISTORY_START_DATE)
  ))
  const historyData = computed<OhlcvPointResponse[]>(() => (
    (historyResponse.value?.items || []).filter((row) => row.close > 0)
  ))
  const historyError = computed(() => {
    const key = priceHistoryStore.getPriceHistoryError(HALVING_PRICE_SYMBOL, HALVING_PRICE_TIMEFRAME, HALVING_HISTORY_START_DATE)
    return key ? t(key) : ''
  })
  const loading = computed(() => (
    priceHistoryStore.isPriceHistoryLoading(HALVING_PRICE_SYMBOL, HALVING_PRICE_TIMEFRAME, HALVING_HISTORY_START_DATE)
    || (!historyResponse.value && !historyError.value)
  ))

  const seriesData = computed(() =>
    historyData.value.map((row) => ({
      x: row.timestamp,
      y: toDisplayAmount(row.close, 'USDT') ?? 0,
    })),
  )

  const buildPhaseAnnotations = (isDark: boolean): HalvingAnnotationMap => {
    if (!showPhases.value) return {}

    return Object.fromEntries(
      HALVING_DATES.flatMap((halving, index) => {
        const halvingTime = new Date(halving.date).getTime()
        return [
          [`acc_${index}`, {
            type: 'box',
            xMin: halvingTime - (500 * ONE_DAY),
            xMax: halvingTime,
            backgroundColor: 'rgba(34, 197, 94, 0.1)',
            borderWidth: 0,
            label: {
              display: true,
              content: t('halving.accumulation'),
              color: isDark ? 'rgba(34, 197, 94, 0.8)' : 'rgba(21, 128, 61, 0.8)',
              font: { size: 10 },
              position: 'start',
              yAdjust: -20,
            },
          }],
          [`exp_${index}`, {
            type: 'box',
            xMin: halvingTime,
            xMax: halvingTime + (540 * ONE_DAY),
            backgroundColor: 'rgba(249, 115, 22, 0.1)',
            borderWidth: 0,
            label: {
              display: true,
              content: t('halving.bullRun'),
              color: isDark ? 'rgba(249, 115, 22, 0.8)' : 'rgba(194, 65, 12, 0.8)',
              font: { size: 10 },
              position: 'start',
              yAdjust: -20,
            },
          }],
        ]
      }),
    )
  }

  const buildChartAnnotations = (isDark: boolean): HalvingAnnotationMap => {
    const annotations: HalvingAnnotationMap = Object.fromEntries(
      HALVING_DATES.map((halving, index) => [
        `halving_${index}`,
        {
          type: 'line',
          scaleID: 'x',
          value: new Date(halving.date).getTime(),
          borderColor: isDark ? 'rgba(255, 255, 255, 0.3)' : 'rgba(0,0,0,0.3)',
          borderWidth: 2,
          borderDash: [6, 6],
          label: {
            display: true,
            content: halving.label,
            position: 'start',
            backgroundColor: isDark ? 'rgba(30, 41, 59, 1)' : 'rgba(255, 255, 255, 1)',
            color: isDark ? '#fff' : '#000',
            font: { size: 11, weight: 'bold' },
            yAdjust: 0,
          },
        },
      ]),
    )

    Object.assign(annotations, buildPhaseAnnotations(isDark))

    const now = Date.now()
    const h4 = new Date(HALVING_DATES[3].date).getTime()
    const h5 = new Date(HALVING_DATES[4].date).getTime()
    const bullEnd = h4 + (540 * ONE_DAY)
    const accStart = h5 - (500 * ONE_DAY)

    let nextPhaseLabel = ''
    let nextPhaseDays = 0

    if (now < bullEnd) {
      nextPhaseLabel = t('halving.bullRunEnds')
      nextPhaseDays = Math.ceil((bullEnd - now) / ONE_DAY)
    } else if (now < accStart) {
      nextPhaseLabel = t('halving.accStarts')
      nextPhaseDays = Math.ceil((accStart - now) / ONE_DAY)
    } else {
      nextPhaseLabel = t('halving.nextHalvingPhase')
      nextPhaseDays = Math.ceil((h5 - now) / ONE_DAY)
    }

    if (now > h4) {
      annotations.current_countdown = {
        type: 'line',
        scaleID: 'x',
        value: now,
        borderColor: isDark ? '#3B82F6' : '#2563EB',
        borderWidth: 2,
        borderDash: [2, 4],
        label: {
          display: true,
          content: [t('halving.today'), t('halving.daysTo', { days: nextPhaseDays, phase: nextPhaseLabel })],
          position: 'center',
          backgroundColor: isDark ? 'rgba(59, 130, 246, 0.9)' : 'rgba(37, 99, 235, 0.9)',
          color: '#fff',
          font: { size: 12, weight: 'bold' },
          yAdjust: 100,
        },
      }
    }

    return annotations
  }

  const buildChartConfig = (): ChartConfiguration<'line'> => {
    const isDark = theme.value === 'dark'
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)'
    const textColor = isDark ? '#9CA3AF' : '#6B7280'
    const datasets: ChartDataset<'line'>[] = [{
      label: t('halving.btcPrice'),
      data: seriesData.value,
      borderColor: isDark ? '#FCD34D' : '#F59E0B',
      borderWidth: 1.5,
      pointRadius: 0,
      pointHitRadius: 10,
      tension: 0,
      parsing: false,
      normalized: true,
    }]

    return {
      type: 'line',
      data: { datasets },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'nearest',
          axis: 'x',
          intersect: false,
        },
        scales: {
          x: {
            type: 'time',
            time: { unit: 'year' },
            grid: { color: gridColor },
            border: { color: gridColor },
            ticks: { color: textColor },
          },
          y: {
            type: scaleType.value,
            position: 'right',
            grid: { color: gridColor },
            border: { color: gridColor },
            ticks: {
              color: textColor,
              callback(value) {
                return formatMoney(Number(value), displayCurrency.value, { maximumFractionDigits: 0 })
              },
            },
          },
        },
        plugins: {
          annotation: { annotations: buildChartAnnotations(isDark) },
          decimation: {
            enabled: true,
            algorithm: 'lttb',
            samples: 600,
          },
          legend: { display: false },
          tooltip: {
            enabled: true,
            backgroundColor: isDark ? 'rgba(17, 24, 39, 0.9)' : 'rgba(255, 255, 255, 0.9)',
            titleColor: isDark ? '#fff' : '#000',
            bodyColor: isDark ? '#fff' : '#000',
            borderColor: isDark ? '#374151' : '#E5E7EB',
            borderWidth: 1,
          },
        },
      },
    }
  }

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

    const config = buildChartConfig()
    if (!chartInstance) {
      chartInstance = new runtime.Chart(context, config)
      return
    }

    chartInstance.data = config.data
    chartInstance.options = config.options ?? {}
    chartInstance.update('none')
  }

  const refreshCurrentPrice = async () => {
    try {
      const response = await marketHistoryApi.getCurrentPrice({
        symbol: HALVING_PRICE_SYMBOL,
        timeframe: HALVING_PRICE_TIMEFRAME,
      })
      const livePrice = Number(response?.current_price)
      if (Number.isFinite(livePrice) && livePrice > 0) {
        currentPrice.value = livePrice
      }
    } catch (error) {
      console.error('Refresh halving current price failed', error)
    }
  }

  const fetchHistoryData = async () => {
    try {
      const response = await priceHistoryStore.getPriceHistory(
        HALVING_PRICE_SYMBOL,
        HALVING_PRICE_TIMEFRAME,
        HALVING_HISTORY_START_DATE,
      )
      const history = (response?.items || []).filter((row) => row.close > 0)
      if (currentPrice.value <= 0 && history.length > 0) {
        currentPrice.value = Number(history[history.length - 1]?.close || 0)
      }
    } catch (error) {
      console.error('Fetch halving history failed', error)
    } finally {
      void syncChart()
    }
  }

  const stopPriceRefresh = () => {
    if (priceRefreshTimer !== null) {
      window.clearInterval(priceRefreshTimer)
      priceRefreshTimer = null
    }
  }

  const startPriceRefresh = () => {
    stopPriceRefresh()
    priceRefreshTimer = window.setInterval(() => {
      if (priceRefreshPending) return
      priceRefreshPending = true
      refreshCurrentPrice().finally(() => {
        priceRefreshPending = false
      })
    }, CURRENT_PRICE_REFRESH_INTERVAL_MS)
  }

  watch([showPhases, scaleType], () => {
    void syncChart()
  })

  watch(theme, () => {
    void syncChart()
  })

  watch(displayCurrency, () => {
    void syncChart()
  })

  onMounted(() => {
    void Promise.all([
      loadHalvingChartRuntime(),
      fetchHistoryData(),
      refreshCurrentPrice(),
    ])
    startPriceRefresh()
  })

  pageSnapshot.bind(
    [showPhases, scaleType],
    () => buildHalvingSnapshot({
      showPhases: showPhases.value,
      scaleType: scaleType.value,
    }),
  )

  onBeforeUnmount(() => {
    renderToken += 1
    stopPriceRefresh()
    chartInstance?.destroy()
    chartInstance = null
  })

  return {
    loading,
    chartCanvas,
    currentPrice,
    showPhases,
    scaleType,
    nextHalvingDate,
    daysToHalving,
    cycleProgress,
    formatPrice: (price: number) => formatDisplayMoney(price, 'USDT', { maximumFractionDigits: 2 }),
  }
}

