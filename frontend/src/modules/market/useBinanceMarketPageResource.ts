import { computed, ref, watch, onScopeDispose, type Ref } from 'vue'

import { binanceMarketApi } from './api'
import { binanceMarketWarmSnapshot } from './binanceMarketWarmSnapshot'
import { EMPTY_RESPONSE } from './binanceMarketShared'
import type {
  BinanceBreakoutMonitorResponse,
  BinanceContractBoardResponse,
  BinanceMarketPageResponse,
  BinanceTickerStatsResponse,
} from './contracts'


const MARKET_PAGE_LIMIT = 24
const MARKET_PAGE_QUOTE_ASSET = 'USDT'
const LOAD_ERROR_LABEL_KEYS: Record<string, string> = {
  '现货榜单': 'binanceMarket.loadErrorLabels.spotRank',
  'U本位24H': 'binanceMarket.loadErrorLabels.contractTicker',
  'U本位Funding': 'binanceMarket.loadErrorLabels.contractFunding',
}

type Translate = (key: string, params?: Record<string, string | number>) => string

export const useBinanceMarketPageResource = (
  minRisePct: Ref<number>,
  autoRefresh: Ref<boolean>,
  locale: Ref<string>,
  translate: Translate,
) => {
  const loading = ref(false)
  const errorState = ref<{ key: string; labels?: string[] } | null>(null)
  const error = computed(() => {
    const failure = errorState.value
    if (!failure) return ''
    const labels = failure.labels?.map(label => LOAD_ERROR_LABEL_KEYS[label]
      ? translate(LOAD_ERROR_LABEL_KEYS[label]) : label).join(locale.value === 'zh-CN' ? '、' : ', ')
    return translate(failure.key, labels ? { labels } : undefined)
  })
  const monitor = ref<BinanceBreakoutMonitorResponse>({ ...EMPTY_RESPONSE })
  const spotBoards = ref<Record<string, BinanceTickerStatsResponse>>({})
  const contractBoards = ref<Record<string, BinanceContractBoardResponse>>({})
  const monitorAvailable = ref(false), spotAvailable = ref(false), contractAvailable = ref(false)
  let refreshTimer: ReturnType<typeof setInterval> | null = null
  let pendingRefreshTimer: ReturnType<typeof setTimeout> | null = null
  let thresholdTimer: ReturnType<typeof setTimeout> | null = null
  let fetchState: { key: string; task: Promise<void> } | null = null
  let disposed = false
  let stopped = false
  let generation = 0

  const setLoadFailures = (labels: string[]) => {
    if (!labels.length) {
      errorState.value = null
      return
    }
    errorState.value = { key: 'binanceMarket.loadFailure', labels }
  }

  const hasDisplayedData = () => (
    Boolean(monitor.value.items?.length)
    || Object.values(spotBoards.value).some((board) => Boolean(board.items?.length))
    || Object.values(contractBoards.value).some((board) => Boolean(board.items?.length))
  )

  const applyPayload = (payload: BinanceMarketPageResponse) => {
    const failures = payload.load_errors || []
    const hasRows = (boards: typeof payload.spot_boards | typeof payload.contract_boards) => Object.values(boards || {}).some(board => board.items?.length)
    const boardsReady = payload.refresh_status?.boards_ready ?? true
    spotAvailable.value = hasRows(payload.spot_boards) || (boardsReady && !failures.includes('现货榜单') && Object.keys(payload.spot_boards || {}).length > 0)
    contractAvailable.value = hasRows(payload.contract_boards) || (boardsReady && !failures.some(label => label.startsWith('U本位')) && Object.keys(payload.contract_boards || {}).length > 0)
    monitorAvailable.value = Boolean(payload.monitor?.items?.length) || (Boolean(payload.monitor?.updated_at)
      && (payload.refresh_status?.monitor_ready ?? true) && (payload.refresh_status?.snapshot_ready ?? !failures.length))
    monitor.value = payload.monitor || { ...EMPTY_RESPONSE }
    spotBoards.value = payload.spot_boards || {}
    contractBoards.value = payload.contract_boards || {}
    setLoadFailures([...(payload.load_errors || [])])
  }

  const requestKey = () => `${minRisePct.value}:${MARKET_PAGE_LIMIT}:${MARKET_PAGE_QUOTE_ASSET}`

  const schedulePendingRefresh = (payload: BinanceMarketPageResponse) => {
    if (pendingRefreshTimer) clearTimeout(pendingRefreshTimer)
    pendingRefreshTimer = null
    const status = payload.refresh_status
    if (disposed || stopped || !status || status.monitor_ready) return
    pendingRefreshTimer = setTimeout(() => {
      pendingRefreshTimer = null
      void fetchData()
    }, status.refreshing ? 2500 : 5000)
  }

  const restoreWarmSnapshot = () => {
    const payload = binanceMarketWarmSnapshot.read(minRisePct.value, MARKET_PAGE_QUOTE_ASSET)
    if (payload) applyPayload(payload)
  }

  const fetchData = async () => {
    if (disposed) return
    const current = generation
    const requestedRise = minRisePct.value
    const key = requestKey()
    if (fetchState?.key === key) return fetchState.task
    let task!: Promise<void>
    task = (async () => {
      loading.value = true
      errorState.value = null
      try {
        const response = await binanceMarketApi.getBinanceMarketPage({
          min_rise_pct: requestedRise,
          limit: MARKET_PAGE_LIMIT,
          quote_asset: MARKET_PAGE_QUOTE_ASSET,
        })
        if (disposed || current !== generation || key !== requestKey()) return
        applyPayload(response)
        schedulePendingRefresh(response)
        binanceMarketWarmSnapshot.write(response, requestedRise, MARKET_PAGE_QUOTE_ASSET)
      } catch (requestError) {
        if (disposed || current !== generation || key !== requestKey()) return
        errorState.value = {
          key: hasDisplayedData() ? 'binanceMarket.refreshFailedWithCache' : 'binanceMarket.monitorLoadFailed',
        }
        console.error('Failed to load Binance market page', requestError)
      } finally {
        if (!disposed && current === generation && fetchState?.key === key && fetchState.task === task) loading.value = false
      }
    })()
    fetchState = { key, task }
    try {
      await task
    } finally {
      if (fetchState?.key === key && fetchState.task === task) fetchState = null
    }
  }

  const startAutoRefresh = () => {
    if (disposed) return
    stopped = false
    if (refreshTimer) clearInterval(refreshTimer)
    refreshTimer = null
    if (!autoRefresh.value) return
    refreshTimer = setInterval(() => { void fetchData() }, 60_000)
  }

  const stopAutoRefresh = () => {
    stopped = true
    generation += 1
    fetchState = null
    loading.value = false
    if (refreshTimer) clearInterval(refreshTimer)
    if (thresholdTimer) clearTimeout(thresholdTimer)
    if (pendingRefreshTimer) clearTimeout(pendingRefreshTimer)
    refreshTimer = null
    thresholdTimer = null
    pendingRefreshTimer = null
  }
  onScopeDispose(() => { disposed = true; stopAutoRefresh() })

  watch(autoRefresh, startAutoRefresh)
  watch(minRisePct, () => {
    if (thresholdTimer) clearTimeout(thresholdTimer)
    thresholdTimer = setTimeout(() => {
      restoreWarmSnapshot()
      void fetchData()
    }, 350)
  })
  restoreWarmSnapshot()

  return {
    loading,
    monitorAvailable, spotAvailable, contractAvailable,
    error,
    monitor,
    spotBoards,
    contractBoards,
    fetchData,
    startAutoRefresh,
    stopAutoRefresh,
  }
}
