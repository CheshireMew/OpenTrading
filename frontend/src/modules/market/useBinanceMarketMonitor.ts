import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

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
import { EMPTY_RESPONSE, toItemKey } from './binanceMarketShared'
import type { BinanceBreakoutMonitorItemResponse, BinanceTickerStatsItemResponse } from './contracts'
import { useBinanceMarketPageResource } from './useBinanceMarketPageResource'


const boardKey = (field: string, direction: SortDirection) => `${field}_${direction}`

export function useBinanceMarketMonitor(snapshot: BinanceMarketSnapshot) {
  const { t, locale } = useI18n()
  const translate = (key: string, params?: Record<string, string | number>) => String(t(key, params ?? {}))
  const minRisePct = ref(snapshot.minRisePct)
  const mode = ref<MonitorMode>(snapshot.mode)
  const marketFilter = ref<MarketFilter>(snapshot.marketFilter)
  const autoRefresh = ref(snapshot.autoRefresh)
  const spotSort = ref<SpotSortState>({ field: snapshot.spotSortField, direction: snapshot.spotSortDirection })
  const contractSort = ref<ContractSortState>({ field: snapshot.contractSortField, direction: snapshot.contractSortDirection })
  const detailKey = ref('')
  const resource = useBinanceMarketPageResource(minRisePct, autoRefresh, locale, translate)
  const { loading, error, monitor, spotBoards, contractBoards, fetchData, startAutoRefresh, stopAutoRefresh } = resource

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
  const clearMonitorDetail = () => { detailKey.value = '' }
  watch(items, () => {
    if (detailKey.value && !detailItem.value) clearMonitorDetail()
  })

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
