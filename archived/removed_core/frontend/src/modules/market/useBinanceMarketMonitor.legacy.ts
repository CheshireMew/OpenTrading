import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  BinanceBreakoutMonitorItemResponse,
  BinanceBreakoutMonitorResponse,
  BinanceContractBoardResponse,
  BinanceMarketPageResponse,
  BinanceTickerStatsItemResponse,
  BinanceTickerStatsResponse,
} from './contracts'
import { binanceMarketApi } from './api'
import { binanceMarketWarmSnapshot } from './binanceMarketWarmSnapshot'
import type {
  BinanceMarketSnapshot,
  ContractBoardRow,
  ContractSortField,
  ContractSortState,
  MarketFilter,
  MonitorMode,
  SortDirection,
  SpotSortField,
  SpotSortState,
} from './binanceMarketShared'
import {
  EMPTY_RESPONSE,
  toItemKey,
} from './binanceMarketShared'

const MARKET_PAGE_LIMIT = 24
const MARKET_PAGE_QUOTE_ASSET = 'USDT'
const LOAD_ERROR_LABEL_KEYS: Record<string, string> = {
  '现货榜单': 'binanceMarket.loadErrorLabels.spotRank',
}

export function useBinanceMarketMonitor(snapshot: BinanceMarketSnapshot) {
  const { t, locale } = useI18n()
  const loading = ref(false)
  const errorState = ref<{ key: string; params?: Record<string, string | number> } | null>(null)
  const error = computed(() => (errorState.value ? t(errorState.value.key, errorState.value.params ?? {}) : ''))
  const minRisePct = ref(snapshot.minRisePct)
  const mode = ref<MonitorMode>(snapshot.mode)
  const marketFilter = ref<MarketFilter>(snapshot.marketFilter)
  const autoRefresh = ref(snapshot.autoRefresh)
  const spotSort = ref<SpotSortState>({
    field: snapshot.spotSortField,
    direction: snapshot.spotSortDirection,
  })
  const contractSort = ref<ContractSortState>({
    field: snapshot.contractSortField,
    direction: snapshot.contractSortDirection,
  })
  const monitor = ref<BinanceBreakoutMonitorResponse>({ ...EMPTY_RESPONSE })
  const spotBoards = ref<Record<string, BinanceTickerStatsResponse>>({})
  const contractBoards = ref<Record<string, BinanceContractBoardResponse>>({})
  const detailKey = ref('')
  let refreshTimer: ReturnType<typeof setInterval> | null = null
  let pendingRefreshTimer: ReturnType<typeof setTimeout> | null = null
  let thresholdTimer: ReturnType<typeof setTimeout> | null = null
  let fetchState: { key: string; task: Promise<void> } | null = null

  const items = computed(() => monitor.value.items || [])
  const spotRows = computed<BinanceTickerStatsItemResponse[]>(() => (
    spotBoards.value[boardKey(spotSort.value.field, spotSort.value.direction)]?.items || []
  ))
  const contractRows = computed<ContractBoardRow[]>(() => (
    contractBoards.value[boardKey(contractSort.value.field, contractSort.value.direction)]?.items || []
  ))
  const filteredItems = computed(() => items.value.filter((item) => {
    if (marketFilter.value !== 'all' && item.market !== marketFilter.value) return false
    if (mode.value === 'natural' && !item.structure_ok) return false
    if (mode.value === 'momentum' && !item.momentum_ok) return false
    if (mode.value === 'focus' && item.verdict !== '优先关注') return false
    return true
  }))
  const detailItem = computed(() => items.value.find((item) => toItemKey(item) === detailKey.value) || null)
  const summaryCards = computed(() => {
    const summary = monitor.value.summary ?? EMPTY_RESPONSE.summary!
    return [
      { label: t('binanceMarket.summary.monitored'), value: String(summary.monitored_count || 0), hint: `>${monitor.value.min_rise_pct || minRisePct.value}%` },
      { label: t('binanceMarket.summary.natural'), value: String(summary.natural_count || 0), hint: t('binanceMarket.summary.naturalHint') },
      { label: t('binanceMarket.summary.momentum'), value: String(summary.momentum_count || 0), hint: t('binanceMarket.summary.momentumHint') },
      { label: t('binanceMarket.summary.focus'), value: String(summary.focus_count || 0), hint: t('binanceMarket.summary.focusHint') },
    ]
  })

  const formatLoadFailureMessage = (labels: string[]) => {
    if (!labels.length) {
      errorState.value = null
      return
    }
    const separator = locale.value === 'zh-CN' ? '、' : ', '
    const localizedLabels = labels
      .map((label) => (LOAD_ERROR_LABEL_KEYS[label] ? t(LOAD_ERROR_LABEL_KEYS[label]) : label))
      .join(separator)
    errorState.value = {
      key: 'binanceMarket.loadFailure',
      params: { labels: localizedLabels },
    }
  }

  const hasDisplayedData = () => (
    Boolean(monitor.value.items?.length)
    || Object.values(spotBoards.value).some((board) => Boolean(board.items?.length))
    || Object.values(contractBoards.value).some((board) => Boolean(board.items?.length))
  )

  const applyMonitorPayload = (payload: BinanceBreakoutMonitorResponse) => {
    monitor.value = payload || { ...EMPTY_RESPONSE }
  }

  const applyBoardsPayload = (
    payload: Pick<BinanceMarketPageResponse, 'spot_boards' | 'contract_boards' | 'load_errors'>,
    options: { warmStart?: boolean } = {},
  ) => {
    spotBoards.value = payload.spot_boards || {}
    contractBoards.value = payload.contract_boards || {}
    if (options.warmStart) {
      errorState.value = null
    } else {
      formatLoadFailureMessage([...(payload.load_errors || [])])
    }
  }

  const applyPayload = (
    payload: BinanceMarketPageResponse,
    options: { warmStart?: boolean } = {},
  ) => {
    applyMonitorPayload(payload.monitor)
    applyBoardsPayload(payload, options)
  }

  const schedulePendingRefresh = (payload: BinanceMarketPageResponse) => {
    if (pendingRefreshTimer) {
      clearTimeout(pendingRefreshTimer)
      pendingRefreshTimer = null
    }
    const status = payload.refresh_status
    if (!status || status.monitor_ready) return
    pendingRefreshTimer = setTimeout(() => {
      pendingRefreshTimer = null
      void fetchData()
    }, status.refreshing ? 2500 : 5000)
  }

  const restoreWarmSnapshot = () => {
    const payload = binanceMarketWarmSnapshot.read(minRisePct.value, MARKET_PAGE_QUOTE_ASSET)
    if (payload) applyPayload(payload, { warmStart: true })
  }

  const marketPageRequestKey = () => `${minRisePct.value}:${MARKET_PAGE_LIMIT}:${MARKET_PAGE_QUOTE_ASSET}`

  const fetchData = async () => {
    const requestMinRisePct = minRisePct.value
    const requestQuoteAsset = MARKET_PAGE_QUOTE_ASSET
    const requestKey = marketPageRequestKey()
    if (fetchState?.key === requestKey) return fetchState.task
    let task!: Promise<void>
    task = (async () => {
      loading.value = true
      errorState.value = null
      try {
        const response = await binanceMarketApi.getBinanceMarketPage({
          min_rise_pct: requestMinRisePct,
          limit: MARKET_PAGE_LIMIT,
          quote_asset: requestQuoteAsset,
        })
        if (requestKey !== marketPageRequestKey()) return
        applyPayload(response)
        schedulePendingRefresh(response)
        binanceMarketWarmSnapshot.write(response, requestMinRisePct, requestQuoteAsset)
      } catch (requestError) {
        if (requestKey !== marketPageRequestKey()) return
        errorState.value = {
          key: hasDisplayedData()
            ? 'binanceMarket.refreshFailedWithCache'
            : 'binanceMarket.monitorLoadFailed',
        }
        console.error('Failed to load Binance market page', requestError)
      } finally {
        if (fetchState?.key === requestKey && fetchState.task === task) {
          loading.value = false
        }
      }
    })()
    fetchState = { key: requestKey, task }
    try {
      await task
    } finally {
      if (fetchState?.key === requestKey && fetchState.task === task) {
        fetchState = null
      }
    }
  }

  const startAutoRefresh = () => {
    if (refreshTimer) clearInterval(refreshTimer)
    if (!autoRefresh.value) return
    refreshTimer = setInterval(() => {
      void fetchData()
    }, 60000)
  }

  const stopAutoRefresh = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
    if (thresholdTimer) {
      clearTimeout(thresholdTimer)
      thresholdTimer = null
    }
    if (pendingRefreshTimer) {
      clearTimeout(pendingRefreshTimer)
      pendingRefreshTimer = null
    }
  }

  watch(autoRefresh, startAutoRefresh)
  watch(minRisePct, () => {
    if (thresholdTimer) clearTimeout(thresholdTimer)
    thresholdTimer = setTimeout(() => {
      restoreWarmSnapshot()
      void fetchData()
    }, 350)
  })

  const toggleContractSort = (field: ContractSortField) => {
    if (contractSort.value.field === field) {
      contractSort.value = {
        ...contractSort.value,
        direction: contractSort.value.direction === 'desc' ? 'asc' : 'desc',
      }
      return
    }
    contractSort.value = { field, direction: 'desc' }
  }

  const toggleSpotSort = (field: SpotSortField) => {
    if (spotSort.value.field === field) {
      spotSort.value = {
        ...spotSort.value,
        direction: spotSort.value.direction === 'desc' ? 'asc' : 'desc',
      }
      return
    }
    spotSort.value = { field, direction: 'desc' }
  }

  const openMonitorDetail = (item: BinanceBreakoutMonitorItemResponse) => {
    detailKey.value = toItemKey(item)
  }

  const clearMonitorDetail = () => {
    detailKey.value = ''
  }

  watch(items, () => {
    if (detailKey.value && !detailItem.value) {
      clearMonitorDetail()
    }
  })

  restoreWarmSnapshot()

  return {
    loading,
    error,
    minRisePct,
    mode,
    marketFilter,
    autoRefresh,
    monitor,
    items,
    filteredItems,
    spotRows,
    spotSort,
    contractRows,
    contractSort,
    detailKey,
    detailItem,
    summaryCards,
    fetchData,
    startAutoRefresh,
    stopAutoRefresh,
    toggleSpotSort,
    toggleContractSort,
    openMonitorDetail,
    clearMonitorDetail,
  }
}

const boardKey = (field: string, direction: SortDirection) => `${field}_${direction}`

