import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useMoney } from '@/composables/useMoney'
import { useTheme } from '@/composables/useTheme'
import type { MarketSymbolSearchResponse, TradeSetupResponse } from './contracts'

import { ensureSymbolCatalogLoaded, findSymbolCatalogItem, isIndexSymbol } from './symbolCatalog'
import { marketInsightApi } from './api'
import { useKlineSeries } from './useKlineSeries'

export function useDashboardPage() {
  const { t } = useI18n()
  const { theme } = useTheme()
  const { displayCurrency, formatMoney, formatDisplayNumber, fromDisplayAmount } = useMoney()

  const timeframes = ['5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M']
  const currentSymbol = ref('BTC/USDT')
  const currentTimeframe = ref('1h')
  const accountSize = ref(1000)
  const tradeStyle = ref('Scalping')
  const tradeStrategy = ref('最大收益')
  const decisionMode = ref('rules')
  const tradeSetupLoading = ref(false)
  const tradeSetupResult = ref<TradeSetupResponse | null>(null)
  const tradeSetupError = ref('')
  let tradeSetupAbortController: AbortController | null = null
  let tradeSetupAbortTimer: number | null = null

  const chartColors = computed(() => {
    const isDark = theme.value === 'dark'
    return {
      bg: isDark ? '#1f2937' : '#ffffff',
      grid: isDark ? '#374151' : '#e5e7eb',
      text: isDark ? '#9ca3af' : '#4b5563',
      upColor: '#10b981',
      downColor: '#ef4444',
    }
  })

  const currentAssetClass = computed(() => {
    const matched = findSymbolCatalogItem(currentSymbol.value)
    if (matched?.asset_class) return matched.asset_class
    return isIndexSymbol(currentSymbol.value) ? 'index' : 'crypto'
  })
  const visibleTimeframes = computed(() => currentAssetClass.value === 'index' ? ['1d'] : timeframes)
  const activeTradeSetup = computed(() => tradeSetupResult.value?.setup || null)
  const canAskTradeSetup = computed(() => currentAssetClass.value === 'crypto')
  const tradeSetupMessage = computed(() => {
    const result = tradeSetupResult.value
    if (!result || result.setup) return ''
    const code = result.error_code || 'model_output_unavailable'
    const key = `dashboard.tradeSetupErrors.${code}`
    const localized = t(key)
    return localized === key ? t('dashboard.tradeSetupUnavailable') : localized
  })
  const tradeSetupNeedsConfiguration = computed(() => tradeSetupResult.value?.error_code === 'model_not_configured')
  const displayAccountSize = computed({
    get: () => Number(formatDisplayNumber(accountSize.value, 'USDT', 2) || 0),
    set: (value) => {
      accountSize.value = fromDisplayAmount(value, 'USDT') ?? accountSize.value
    },
  })
  const {
    chartData,
    volumeData,
    loadingMore,
    loadError: klineLoadError,
    loadMore,
    retry: retryKline,
  } = useKlineSeries(currentSymbol, currentTimeframe)

  const handleSymbolSelect = (item: MarketSymbolSearchResponse) => {
    if (item.asset_class === 'index') currentTimeframe.value = '1d'
  }

  const formatTradePrice = (value: number) => {
    if (!Number.isFinite(value)) return '-'
    if (value >= 1000) return formatMoney(value, 'USDT', { maximumFractionDigits: 1 })
    if (value >= 1) return formatMoney(value, 'USDT', { maximumFractionDigits: 3 })
    return formatMoney(value, 'USDT', { maximumSignificantDigits: 4 })
  }

  const clearTradeSetupPendingState = () => {
    if (tradeSetupAbortTimer !== null) {
      window.clearTimeout(tradeSetupAbortTimer)
      tradeSetupAbortTimer = null
    }
    if (tradeSetupAbortController) {
      tradeSetupAbortController.abort()
      tradeSetupAbortController = null
    }
    tradeSetupLoading.value = false
  }

  const askTradeSetup = async () => {
    if (!canAskTradeSetup.value) return
    clearTradeSetupPendingState()
    const controller = new AbortController()
    tradeSetupAbortController = controller
    tradeSetupLoading.value = true
    tradeSetupError.value = ''
    tradeSetupAbortTimer = window.setTimeout(() => {
      if (tradeSetupAbortController !== controller) return
      controller.abort()
      tradeSetupAbortController = null
      tradeSetupAbortTimer = null
      tradeSetupLoading.value = false
      tradeSetupError.value = t(decisionMode.value === 'ai' ? 'dashboard.aiTimeout' : 'dashboard.rulesTimeout')
    }, decisionMode.value === 'ai' ? 180000 : 20000)
    try {
      const response = await marketInsightApi.getTradeSetup({
        symbol: currentSymbol.value,
        timeframe: currentTimeframe.value,
        limit: 120,
        account_size: accountSize.value,
        style: tradeStyle.value,
        strategy: tradeStrategy.value,
        mode: decisionMode.value,
        signal: controller.signal,
      })
      if (tradeSetupAbortController !== controller) return
      tradeSetupResult.value = response
    } catch (error) {
      if (controller.signal.aborted) return
      console.error('Trade setup failed', error)
      tradeSetupResult.value = null
      tradeSetupError.value = t('dashboard.setupFailed')
    } finally {
      if (tradeSetupAbortController !== controller) return
      if (tradeSetupAbortTimer !== null) {
        window.clearTimeout(tradeSetupAbortTimer)
        tradeSetupAbortTimer = null
      }
      tradeSetupAbortController = null
      tradeSetupLoading.value = false
    }
  }

  watch([currentSymbol, currentTimeframe, decisionMode], () => {
    clearTradeSetupPendingState()
    tradeSetupResult.value = null
    tradeSetupError.value = ''
  })

  onMounted(() => {
    void ensureSymbolCatalogLoaded()
  })

  onUnmounted(() => {
    clearTradeSetupPendingState()
  })

  return reactive({
    displayCurrency,
    chartColors,
    visibleTimeframes,
    currentSymbol,
    currentTimeframe,
    displayAccountSize,
    tradeStyle,
    tradeStrategy,
    decisionMode,
    tradeSetupLoading,
    tradeSetupResult,
    tradeSetupError,
    activeTradeSetup,
    canAskTradeSetup,
    tradeSetupMessage,
    tradeSetupNeedsConfiguration,
    chartData,
    volumeData,
    loadingMore,
    klineLoadError,
    loadMore,
    retryKline,
    handleSymbolSelect,
    formatTradePrice,
    askTradeSetup,
  })
}

