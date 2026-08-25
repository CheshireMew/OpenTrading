import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import { formatAdaptivePrice, formatCompactCurrency, formatSignedMetric } from '@/modules/format'
import type { BinanceBreakoutMonitorItemResponse } from './contracts'
import {
  normalizeSnapshot,
  toItemKey,
  displaySymbol,
  formatScore,
  formatTime,
  sortDirectionIcon,
  valueTone,
  verdictTone,
  createDefaultSnapshot,
  buildBinanceMarketSnapshot,
} from './binanceMarketShared'
import { useBinanceMarketMonitor } from './useBinanceMarketMonitor'
import { useBinanceSymbolChart } from './useBinanceSymbolChart'

export function useBinanceMarketPage() {
  const { t, locale } = useI18n()
  const pageSnapshot = createPersistentPageSnapshot(PAGE_SNAPSHOT_KEYS.binanceMarket, normalizeSnapshot, createDefaultSnapshot())
  const restoredSnapshot = pageSnapshot.initial
  const market = useBinanceMarketMonitor(restoredSnapshot)
  const chart = useBinanceSymbolChart()

  const openChart = (
    item: { symbol?: string | null; market?: string | null; market_label?: string | null },
  ) => {
    market.clearMonitorDetail()
    chart.openChart(item)
  }

  const formatMarketLabel = (item: Pick<BinanceBreakoutMonitorItemResponse, 'market'> | null | undefined) => {
    if (item?.market === 'spot') return t('binanceMarket.market.spot')
    if (item?.market === 'usdm') return t('binanceMarket.market.usdm')
    return t('binanceMarket.marketFallback')
  }

  const statusKeys: Record<string, string> = {
    '优先关注': 'binanceMarket.status.focus',
    '继续跟踪': 'binanceMarket.status.tracking',
    '只做观察': 'binanceMarket.status.watch',
    '数据不足': 'binanceMarket.status.insufficient',
    '继续上行': 'binanceMarket.status.advancing',
    '高位蓄势': 'binanceMarket.status.consolidating',
    '冲高回撤': 'binanceMarket.status.pullback',
  }

  const reasonKeys: Record<string, string> = {
    '离高点不远，回撤不深': 'binanceMarket.reasons.nearHigh',
    '价格仍压在强势区间上沿': 'binanceMarket.reasons.strongRange',
    '短线节奏均匀，不是单根硬拉': 'binanceMarket.reasons.evenPace',
    '15 分钟仍站在均线之上': 'binanceMarket.reasons.aboveEma15m',
    '1 小时趋势还没掉头': 'binanceMarket.reasons.hourTrend',
    '最近 1 小时还在续涨': 'binanceMarket.reasons.hourRising',
    '短周期数据暂时不足': 'binanceMarket.reasons.insufficientShortCycle',
  }

  const translateKnownValue = (value: string | null | undefined, keys: Record<string, string>) => {
    if (!value) return '--'
    const key = keys[value]
    return key ? t(key) : value
  }

  const openMonitorDetail = (item: BinanceBreakoutMonitorItemResponse) => {
    market.openMonitorDetail(item)
    chart.openChart(item)
  }

  const closeChart = () => {
    market.clearMonitorDetail()
    chart.closeChart()
  }

  onMounted(async () => {
    await market.fetchData()
    market.startAutoRefresh()
  })

  onUnmounted(() => {
    market.stopAutoRefresh()
  })

  pageSnapshot.bind(
    [
      market.minRisePct,
      market.mode,
      market.marketFilter,
      market.autoRefresh,
      market.spotSort,
      market.contractSort,
    ],
    () => buildBinanceMarketSnapshot({
      minRisePct: market.minRisePct.value,
      mode: market.mode.value,
      marketFilter: market.marketFilter.value,
      autoRefresh: market.autoRefresh.value,
      spotSortField: market.spotSort.value.field,
      spotSortDirection: market.spotSort.value.direction,
      contractSortField: market.contractSort.value.field,
      contractSortDirection: market.contractSort.value.direction,
    }),
  )

  return {
    loading: market.loading,
    error: market.error,
    minRisePct: market.minRisePct,
    mode: market.mode,
    marketFilter: market.marketFilter,
    autoRefresh: market.autoRefresh,
    monitor: market.monitor,
    items: market.items,
    filteredItems: market.filteredItems,
    spotRows: market.spotRows,
    spotSort: market.spotSort,
    contractRows: market.contractRows,
    contractSort: market.contractSort,
    detailKey: market.detailKey,
    detailItem: market.detailItem,
    summaryCards: market.summaryCards,
    fetchData: market.fetchData,
    toggleSpotSort: market.toggleSpotSort,
    toggleContractSort: market.toggleContractSort,
    openMonitorDetail,
    chartDialog: chart.chartDialog,
    chartSymbol: chart.chartSymbol,
    chartTitle: chart.chartTitle,
    chartMarketLabel: chart.chartMarketLabel,
    chartTimeframe: chart.chartTimeframe,
    chartTimeframes: chart.chartTimeframes,
    chartColors: chart.chartColors,
    chartData: chart.chartData,
    volumeData: chart.volumeData,
    chartLoadingMore: chart.chartLoadingMore,
    chartError: chart.chartError,
    contractDetail: chart.contractDetail,
    contractDetailLoading: chart.contractDetailLoading,
    contractDetailError: chart.contractDetailError,
    openChart,
    closeChart,
    loadMoreChartHistory: chart.loadMoreChartHistory,
    retryChart: chart.retryChart,
    formatSigned: formatSignedMetric,
    formatScore,
    formatTime: (value: number | null | undefined) => formatTime(value, locale.value),
    formatPrice: (value: number | null | undefined) => formatAdaptivePrice(value, 'USDT', '--'),
    formatCompact: (value: number | null | undefined) => formatCompactCurrency(value, 'USDT'),
    displaySymbol,
    formatMarketLabel,
    formatVerdict: (value: string | null | undefined) => translateKnownValue(value, statusKeys),
    formatFollowStatus: (value: string | null | undefined) => translateKnownValue(value, statusKeys),
    formatReason: (value: string | null | undefined) => translateKnownValue(value, reasonKeys),
    sortDirectionIcon,
    valueTone,
    verdictTone,
    toItemKey,
  }
}

