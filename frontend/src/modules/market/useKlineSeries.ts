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
  const loading = ref(false)
  const enabled = computed(() => options.enabled?.value ?? true)
  let tailRefreshPending = false
  let refreshTimer: number | null = null
  let isRouteActive = true
  let shouldRefreshOnActivate = false
  let requestVersion = 0

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

  const fetchLatest = async (fetchOptions: { force?: boolean } = {}, version = requestVersion) => {
    const requestSymbol = symbol.value
    const requestTimeframe = timeframe.value
    const requestKey = cacheKey.value
    if (!isRouteActive || !enabled.value || !requestSymbol || !requestTimeframe) {
      indexKlineData.value = []
      return
    }
    noMoreHistory.value = false
    if (options.source) {
      const items = await options.source.latest(1000)
      if (!isRouteActive || !enabled.value || version !== requestVersion || requestKey !== cacheKey.value) return
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
      if (!isRouteActive || !enabled.value || version !== requestVersion || requestKey !== cacheKey.value) return
      indexKlineData.value = res.data || []
      return
    }
    const data = await klineStore.getKlineData(requestSymbol, requestTimeframe, 1000, fetchOptions)
    if (!isRouteActive || !enabled.value || version !== requestVersion || requestKey !== cacheKey.value) return
    if (data) {
      klineStore.setKlineHistory(requestSymbol, requestTimeframe, data, 1000)
    }
    if (!isIndexSymbol(requestSymbol)) await refreshTail()
  }

  const refreshTail = async () => {
    const requestSymbol = symbol.value
    const requestTimeframe = timeframe.value
    const requestKey = cacheKey.value
    const version = requestVersion
    if (!isRouteActive || !enabled.value || !requestSymbol || !requestTimeframe || (!options.source && isIndexSymbol(requestSymbol))) return
    const tail = options.source
      ? await options.source.tail(LIVE_TAIL_LIMIT)
      : (await marketHistoryApi.getPriceSeriesTail({
          symbol: requestSymbol,
          timeframe: requestTimeframe,
          limit: LIVE_TAIL_LIMIT,
        })).kline_data || []
    if (!isRouteActive || !enabled.value || version !== requestVersion || requestKey !== cacheKey.value) return
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
      const version = requestVersion
      refreshTail().catch(error => {
        if (version !== requestVersion || !enabled.value) return
        console.error('Realtime refresh failed', error)
        loadError.value = true
        stopAutoRefresh()
      }).finally(() => {
        if (version === requestVersion) tailRefreshPending = false
      })
    }, REFRESH_INTERVAL_MS)
  }

  const loadLatest = async (fetchOptions: { force?: boolean } = {}) => {
    const version = ++requestVersion
    loading.value = true
    loadError.value = false
    try {
      await fetchLatest(fetchOptions, version)
      if (version === requestVersion) loadError.value = false
    } catch (error) {
      if (version !== requestVersion) return
      loadError.value = true
      console.error('Market history load failed', error)
    } finally {
      if (version === requestVersion) {
        loading.value = false
        if (!loadError.value) startAutoRefresh()
      }
    }
  }

  const loadMore = async () => {
    if (loadingMore.value || noMoreHistory.value || klineData.value.length === 0) return

    loadingMore.value = true
    const version = requestVersion
    const requestKey = cacheKey.value
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
        if (!isRouteActive || !enabled.value || version !== requestVersion || requestKey !== cacheKey.value) return
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
      if (!isRouteActive || !enabled.value || version !== requestVersion || requestKey !== cacheKey.value) return

      if (newKlines.length === 0) {
        noMoreHistory.value = true
        return
      }

      if (options.source) sourceKlineData.value = mergeKlines(newKlines, sourceKlineData.value).slice(-5000)
      else klineStore.prependKlineHistory(requestSymbol, requestTimeframe, newKlines)
    } catch (e) {
      if (version === requestVersion) console.error('Load history failed', e)
    } finally {
      if (version === requestVersion) loadingMore.value = false
    }
  }

  const mergeKlines = (...batches: OhlcvPointResponse[][]) => Array.from(
    new Map(batches.flat().map((item) => [item.timestamp, item])).values(),
  ).sort((left, right) => left.timestamp - right.timestamp)

  watch([symbol, timeframe, enabled, cacheKey], async () => {
    requestVersion += 1
    loading.value = false
    loadingMore.value = false
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
    requestVersion += 1
    loading.value = false
    loadingMore.value = false
    isRouteActive = false
    shouldRefreshOnActivate = true
    tailRefreshPending = false
    stopAutoRefresh()
  })

  onUnmounted(() => {
    requestVersion += 1
    isRouteActive = false
    stopAutoRefresh()
  })

  return {
    chartData,
    volumeData,
    loadingMore,
    loading,
    noMoreHistory,
    loadError,
    fetchLatest,
    retry: () => loadLatest({ force: true }),
    loadMore,
  }
}

