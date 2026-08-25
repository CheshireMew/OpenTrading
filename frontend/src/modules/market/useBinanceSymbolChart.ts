import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useTheme } from '@/composables/useTheme'
import { binanceMarketApi } from './api'
import type {
  BinanceContractResearchDetailResponse,
} from './contracts'
import { displaySymbol, type ChartDialogState } from './binanceMarketShared'
import { useKlineSeries } from './useKlineSeries'

export function useBinanceSymbolChart() {
  const { t } = useI18n()
  const { theme } = useTheme()
  const chartDialog = ref<ChartDialogState>({
    open: false,
    rawSymbol: '',
    market: '',
  })
  const chartTimeframe = ref('15m')
  const chartTimeframes = ['5m', '15m', '1h', '4h', '1d']
  const contractDetail = ref<BinanceContractResearchDetailResponse | null>(null)
  const contractDetailLoading = ref(false)
  const contractDetailError = ref('')
  let contractDetailRequestId = 0

  const chartSymbol = computed(() => chartDialog.value.rawSymbol)
  const chartTitle = computed(() => displaySymbol(chartDialog.value.rawSymbol))
  const chartMarketLabel = computed(() => {
    if (chartDialog.value.market === 'spot') return t('binanceMarket.market.spot')
    if (chartDialog.value.market === 'usdm') return t('binanceMarket.market.usdm')
    return t('binanceMarket.marketFallback')
  })
  const chartEnabled = computed(() => chartDialog.value.open && Boolean(chartSymbol.value))
  const contractDetailEnabled = computed(() => chartDialog.value.open && chartDialog.value.market === 'usdm' && Boolean(chartDialog.value.rawSymbol))
  const chartColors = computed(() => {
    const isDark = theme.value === 'dark'
    return {
      bg: isDark ? '#020617' : '#ffffff',
      grid: isDark ? '#1e293b' : '#e2e8f0',
      text: isDark ? '#94a3b8' : '#475569',
      upColor: '#10b981',
      downColor: '#ef4444',
    }
  })
  const {
    chartData,
    volumeData,
    loadingMore: chartLoadingMore,
    loadError: chartLoadError,
    loadMore: loadMoreChartHistory,
    retry: retryChart,
  } = useKlineSeries(chartSymbol, chartTimeframe, {
    enabled: chartEnabled,
    source: {
      key: computed(() => `binance:${chartDialog.value.market}:${chartSymbol.value}:${chartTimeframe.value}`),
      latest: async (limit) => (await binanceMarketApi.getBinanceMarketKlines({
        symbol: chartSymbol.value,
        market: chartDialog.value.market || 'spot',
        interval: chartTimeframe.value,
        limit,
      })).items || [],
      tail: async (limit) => (await binanceMarketApi.getBinanceMarketKlines({
        symbol: chartSymbol.value,
        market: chartDialog.value.market || 'spot',
        interval: chartTimeframe.value,
        limit,
      })).items || [],
      before: async (endTime, limit) => (await binanceMarketApi.getBinanceMarketKlines({
        symbol: chartSymbol.value,
        market: chartDialog.value.market || 'spot',
        interval: chartTimeframe.value,
        limit,
        end_time: endTime,
      })).items || [],
    },
  })

  const openChart = (
    item: { symbol?: string | null; market?: string | null; market_label?: string | null },
  ) => {
    const rawSymbol = String(item.symbol || '').trim().toUpperCase()
    if (!rawSymbol) return
    chartDialog.value = {
      open: true,
      rawSymbol,
      market: item.market || 'spot',
    }
  }

  const closeChart = () => {
    chartDialog.value = {
      ...chartDialog.value,
      open: false,
    }
  }

  watch([contractDetailEnabled, () => chartDialog.value.rawSymbol], async ([enabled]) => {
    const requestId = ++contractDetailRequestId
    contractDetail.value = null
    contractDetailError.value = ''
    if (!enabled) {
      contractDetailLoading.value = false
      return
    }
    contractDetailLoading.value = true
    try {
      const response = await binanceMarketApi.getBinanceMarketContractDetail({
        symbol: chartDialog.value.rawSymbol,
        period: '1h',
        limit: 72,
      })
      if (requestId !== contractDetailRequestId) return
      contractDetail.value = response
    } catch (error) {
      if (requestId !== contractDetailRequestId) return
      contractDetailError.value = t('binanceMarket.contractDetail.loadFailed')
      console.error('Failed to load Binance contract detail', error)
    } finally {
      if (requestId === contractDetailRequestId) {
        contractDetailLoading.value = false
      }
    }
  }, { immediate: true })

  return {
    chartDialog,
    chartSymbol,
    chartTitle,
    chartMarketLabel,
    chartTimeframe,
    chartTimeframes,
    chartColors,
    chartData,
    volumeData,
    chartLoadingMore,
    chartError: computed(() => chartLoadError.value ? t('binanceMarket.chartLoadFailed') : ''),
    contractDetail,
    contractDetailLoading,
    contractDetailError,
    openChart,
    closeChart,
    loadMoreChartHistory,
    retryChart,
  }
}

