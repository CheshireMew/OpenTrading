import { computed, onActivated, onDeactivated, onUnmounted, ref, watch, type Ref } from 'vue'
import { marketHistoryApi, marketIndexApi } from './api'
import { useKlineStore } from './klineStore'
import { isIndexSymbol } from './symbolCatalog'
import { toLocalIsoDate } from '@/utils/localDate'
import type { OhlcvPointResponse } from './contracts'

const REFRESH_INTERVAL_MS = 5000
const LIVE_TAIL_LIMIT = 16

type UseKlineSeriesOptions = {
  enabled?: Ref<boolean>
  source?: {
    key: Ref<string>
    latest: (limit: number) => Promise<OhlcvPointResponse[]>
    tail: (limit: number) => Promise<OhlcvPointResponse[]>
    before: (endTimestamp: number, limit: number) => Promise<OhlcvPointResponse[]>
  }
}

export function useKlineSeries(symbol: Ref<string>, timeframe: Ref<string>, options: UseKlineSeriesOptions = {}) {
  const klineStore = useKlineStore()
  const indexKlineData = ref<OhlcvPointResponse[]>([])
  const sourceKlineData = ref<OhlcvPointResponse[]>([])
  const loadingMore = ref(false)
  const noMoreHistory = ref(false)
  const loadError = ref(false)
  const enabled = computed(() => options.enabled?.value ?? true)
  let tailRefreshPending = false
  let refreshTimer: number | null = null
  let isRouteActive = true
  let shouldRefreshOnActivate = false

  const cacheKey = computed(() => options.source?.key.value || `${symbol.value}:${timeframe.value}`)
  const klineData = computed(() => (
    options.source
      ? sourceKlineData.value
      : isIndexSymbol(symbol.value)
      ? indexKlineData.value
      : klineStore.readKlineCache(cacheKey.value)
  ))

  const chartData = computed(() =>
    klineData.value.map(k => ({
      time: k.timestamp / 1000,
      open: k.open,
      high: k.high,
      low: k.low,
      close: k.close,
    }))
  )

  const volumeData = computed(() =>
    klineData.value.map(k => ({
      time: k.timestamp / 1000,
      value: k.volume,
      color: k.close >= k.open ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.5)',
    }))
  )

  const fetchLatest = async (fetchOptions: { force?: boolean } = {}) => {
    const requestSymbol = symbol.value
    const requestTimeframe = timeframe.value
    if (!isRouteActive || !enabled.value || !requestSymbol || !requestTimeframe) {
      indexKlineData.value = []
      return
    }
    noMoreHistory.value = false
    if (options.source) {
      const items = await options.source.latest(1000)
      if (!isRouteActive || cacheKey.value !== options.source.key.value) return
      sourceKlineData.value = mergeKlines(items).slice(-1000)
      return
    }
    if (isIndexSymbol(requestSymbol)) {
      const end = new Date()
      const start = new Date()
      start.setFullYear(end.getFullYear() - 1)
      const res = await marketIndexApi.getIndexHistory({
        symbol: requestSymbol,
        timeframe: '1d',
        start_date: toLocalIsoDate(start),
        end_date: toLocalIsoDate(end),
      })
      if (!isRouteActive || requestSymbol !== symbol.value || requestTimeframe !== timeframe.value) return
      indexKlineData.value = res.data || []
      return
    }
    const data = await klineStore.getKlineData(requestSymbol, requestTimeframe, 1000, fetchOptions)
    if (!isRouteActive || requestSymbol !== symbol.value || requestTimeframe !== timeframe.value) return
    if (data) {
      klineStore.setKlineHistory(requestSymbol, requestTimeframe, data, 1000)
    }
    if (!isIndexSymbol(requestSymbol)) await refreshTail()
  }

  const refreshTail = async () => {
    const requestSymbol = symbol.value
    const requestTimeframe = timeframe.value
    if (!isRouteActive || !enabled.value || !requestSymbol || !requestTimeframe || (!options.source && isIndexSymbol(requestSymbol))) return
    const tail = options.source
      ? await options.source.tail(LIVE_TAIL_LIMIT)
      : (await marketHistoryApi.getPriceSeriesTail({
          symbol: requestSymbol,
          timeframe: requestTimeframe,
          limit: LIVE_TAIL_LIMIT,
        })).kline_data || []
    if (!isRouteActive || requestSymbol !== symbol.value || requestTimeframe !== timeframe.value) return
    if (tail.length === 0) return
    if (options.source) sourceKlineData.value = mergeKlines(sourceKlineData.value, tail).slice(-1000)
    else klineStore.applyKlineTail(requestSymbol, requestTimeframe, tail, 1000)
  }

  const stopAutoRefresh = () => {
    if (refreshTimer !== null) {
      window.clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  const startAutoRefresh = () => {
    stopAutoRefresh()
    if (!isRouteActive || !enabled.value || !symbol.value || !timeframe.value || (!options.source && isIndexSymbol(symbol.value))) return
    refreshTimer = window.setInterval(() => {
      if (!isRouteActive || isIndexSymbol(symbol.value) || tailRefreshPending) return
      tailRefreshPending = true
      refreshTail().catch(error => {
        console.error('Realtime refresh failed', error)
        loadError.value = true
        stopAutoRefresh()
      }).finally(() => {
        tailRefreshPending = false
      })
    }, REFRESH_INTERVAL_MS)
  }

  const loadLatest = async (fetchOptions: { force?: boolean } = {}) => {
    try {
      await fetchLatest(fetchOptions)
      loadError.value = false
    } catch (error) {
      loadError.value = true
      console.error('Market history load failed', error)
    } finally {
      if (!loadError.value) startAutoRefresh()
    }
  }

  const loadMore = async () => {
    if (loadingMore.value || noMoreHistory.value || klineData.value.length === 0) return

    loadingMore.value = true
    try {
      const requestSymbol = symbol.value
      const requestTimeframe = timeframe.value
      const oldest = klineData.value[0]
      if (isIndexSymbol(requestSymbol)) {
        const end = new Date(oldest.timestamp - 24 * 60 * 60 * 1000)
        const start = new Date(end)
        start.setFullYear(end.getFullYear() - 1)
        const res = await marketIndexApi.getIndexHistory({
          symbol: requestSymbol,
          timeframe: '1d',
          start_date: toLocalIsoDate(start),
          end_date: toLocalIsoDate(end),
        })
        if (requestSymbol !== symbol.value || requestTimeframe !== timeframe.value) return
        const newKlines = res.data || []
        if (newKlines.length === 0) {
          noMoreHistory.value = true
          return
        }
        indexKlineData.value = [...newKlines, ...indexKlineData.value]
        return
      }

      const newKlines = options.source
        ? await options.source.before(oldest.timestamp - 1, 500)
        : (await marketHistoryApi.getPriceSeriesWindow({
        symbol: requestSymbol,
        timeframe: requestTimeframe,
        end_ts: oldest.timestamp - 1,
        limit: 500,
      })).items || []
      if (requestSymbol !== symbol.value || requestTimeframe !== timeframe.value) return

      if (newKlines.length === 0) {
        noMoreHistory.value = true
        return
      }

      if (options.source) sourceKlineData.value = mergeKlines(newKlines, sourceKlineData.value).slice(-5000)
      else klineStore.prependKlineHistory(requestSymbol, requestTimeframe, newKlines)
    } catch (e) {
      console.error('Load history failed', e)
    } finally {
      loadingMore.value = false
    }
  }

  const mergeKlines = (...batches: OhlcvPointResponse[][]) => Array.from(
    new Map(batches.flat().map((item) => [item.timestamp, item])).values(),
  ).sort((left, right) => left.timestamp - right.timestamp)

  watch([symbol, timeframe, enabled, cacheKey], async () => {
    stopAutoRefresh()
    tailRefreshPending = false
    if (!isRouteActive || !enabled.value || !symbol.value || !timeframe.value) {
      indexKlineData.value = []
      sourceKlineData.value = []
      noMoreHistory.value = false
      return
    }
    if (isIndexSymbol(symbol.value)) {
      indexKlineData.value = []
    }
    if (options.source) sourceKlineData.value = []
    await loadLatest()
  }, { immediate: true })

  onActivated(() => {
    isRouteActive = true
    if (!enabled.value || !symbol.value || !timeframe.value) return
    if (shouldRefreshOnActivate) {
      shouldRefreshOnActivate = false
      void loadLatest()
      return
    }
    startAutoRefresh()
  })

  onDeactivated(() => {
    isRouteActive = false
    shouldRefreshOnActivate = true
    tailRefreshPending = false
    stopAutoRefresh()
  })

  onUnmounted(() => {
    isRouteActive = false
    stopAutoRefresh()
  })

  return {
    chartData,
    volumeData,
    loadingMore,
    noMoreHistory,
    loadError,
    fetchLatest,
    retry: () => loadLatest({ force: true }),
    loadMore,
  }
}

