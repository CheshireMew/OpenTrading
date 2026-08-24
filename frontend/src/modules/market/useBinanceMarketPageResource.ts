import { computed, ref, watch, type Ref } from 'vue'

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
}

type Translate = (key: string, params?: Record<string, string | number>) => string

export const useBinanceMarketPageResource = (
  minRisePct: Ref<number>,
  autoRefresh: Ref<boolean>,
  locale: Ref<string>,
  translate: Translate,
) => {
  const loading = ref(false)
  const errorState = ref<{ key: string; params?: Record<string, string | number> } | null>(null)
  const error = computed(() => errorState.value ? translate(errorState.value.key, errorState.value.params) : '')
  const monitor = ref<BinanceBreakoutMonitorResponse>({ ...EMPTY_RESPONSE })
  const spotBoards = ref<Record<string, BinanceTickerStatsResponse>>({})
  const contractBoards = ref<Record<string, BinanceContractBoardResponse>>({})
  let refreshTimer: ReturnType<typeof setInterval> | null = null
  let pendingRefreshTimer: ReturnType<typeof setTimeout> | null = null
  let thresholdTimer: ReturnType<typeof setTimeout> | null = null
  let fetchState: { key: string; task: Promise<void> } | null = null

  const setLoadFailures = (labels: string[]) => {
    if (!labels.length) {
      errorState.value = null
      return
    }
    const separator = locale.value === 'zh-CN' ? '、' : ', '
    const localized = labels
      .map((label) => LOAD_ERROR_LABEL_KEYS[label] ? translate(LOAD_ERROR_LABEL_KEYS[label]) : label)
      .join(separator)
    errorState.value = { key: 'binanceMarket.loadFailure', params: { labels: localized } }
  }

  const hasDisplayedData = () => (
    Boolean(monitor.value.items?.length)
    || Object.values(spotBoards.value).some((board) => Boolean(board.items?.length))
    || Object.values(contractBoards.value).some((board) => Boolean(board.items?.length))
  )

  const applyPayload = (payload: BinanceMarketPageResponse, warmStart = false) => {
    monitor.value = payload.monitor || { ...EMPTY_RESPONSE }
    spotBoards.value = payload.spot_boards || {}
    contractBoards.value = payload.contract_boards || {}
    if (warmStart) errorState.value = null
    else setLoadFailures([...(payload.load_errors || [])])
  }

  const requestKey = () => `${minRisePct.value}:${MARKET_PAGE_LIMIT}:${MARKET_PAGE_QUOTE_ASSET}`

  const schedulePendingRefresh = (payload: BinanceMarketPageResponse) => {
    if (pendingRefreshTimer) clearTimeout(pendingRefreshTimer)
    pendingRefreshTimer = null
    const status = payload.refresh_status
    if (!status || status.monitor_ready) return
    pendingRefreshTimer = setTimeout(() => {
      pendingRefreshTimer = null
      void fetchData()
    }, status.refreshing ? 2500 : 5000)
  }

  const restoreWarmSnapshot = () => {
    const payload = binanceMarketWarmSnapshot.read(minRisePct.value, MARKET_PAGE_QUOTE_ASSET)
    if (payload) applyPayload(payload, true)
  }

  const fetchData = async () => {
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
        if (key !== requestKey()) return
        applyPayload(response)
        schedulePendingRefresh(response)
        binanceMarketWarmSnapshot.write(response, requestedRise, MARKET_PAGE_QUOTE_ASSET)
      } catch (requestError) {
        if (key !== requestKey()) return
        errorState.value = {
          key: hasDisplayedData() ? 'binanceMarket.refreshFailedWithCache' : 'binanceMarket.monitorLoadFailed',
        }
        console.error('Failed to load Binance market page', requestError)
      } finally {
        if (fetchState?.key === key && fetchState.task === task) loading.value = false
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
    if (refreshTimer) clearInterval(refreshTimer)
    refreshTimer = null
    if (!autoRefresh.value) return
    refreshTimer = setInterval(() => { void fetchData() }, 60_000)
  }

  const stopAutoRefresh = () => {
    if (refreshTimer) clearInterval(refreshTimer)
    if (thresholdTimer) clearTimeout(thresholdTimer)
    if (pendingRefreshTimer) clearTimeout(pendingRefreshTimer)
    refreshTimer = null
    thresholdTimer = null
    pendingRefreshTimer = null
  }

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
    error,
    monitor,
    spotBoards,
    contractBoards,
    fetchData,
    startAutoRefresh,
    stopAutoRefresh,
  }
}
