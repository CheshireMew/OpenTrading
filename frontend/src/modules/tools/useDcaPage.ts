import { computed, onBeforeUnmount, onMounted, reactive, ref, watch, type WatchStopHandle } from 'vue'
import { useI18n } from 'vue-i18n'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import { ensureSymbolCatalogLoaded, isIndexSymbol } from '@/modules/market'
import { useTheme } from '@/composables/useTheme'
import { useMoney } from '@/composables/useMoney'
import { useUserPreferences } from '@/composables/useUserPreferences'
import { apiErrorMessage } from '@/api/request'
import type { DCAResponse, SimulateDcaCommand } from './contracts'
import { toolsApi } from './api'
import { buildDcaSnapshot, createDefaultDcaConfig, createEmptyDcaConfig, createEmptyDcaSnapshot, normalizeDcaConfig, normalizeDcaSnapshot } from './pageSnapshots'
import { createEmptyMarketData, useDcaMarketContext } from './useDcaMarketContext'
import { useDcaCharts } from './useDcaCharts'
import { localIsoDateDaysAgo, todayLocalIsoDate } from '@/utils/localDate'

export function useDcaPage() {
  const { theme } = useTheme()
  const { t } = useI18n()
  const { timezone, setTimezone } = useUserPreferences()
  const { displayCurrency, fromDisplayAmount, formatDisplayNumber, formatMoney } = useMoney()
  const pageSnapshot = createPersistentPageSnapshot(
    PAGE_SNAPSHOT_KEYS.dca,
    normalizeDcaSnapshot,
    createEmptyDcaSnapshot(),
  )
  const restoredSnapshot = pageSnapshot.initial
  const config = reactive(createEmptyDcaConfig())
  let snapshotStop: WatchStopHandle | null = null
  let disposed = false
  const strategyKeys = ref<string[]>([])
  const multiplierDefault = ref(0)
  const dcaMaxDays = ref(3650)

  const loading = ref(false)
  const errorMessage = ref('')
  const result = ref<DCAResponse | null>(null)
  const { marketData, fetchMarketIndicators } = useDcaMarketContext({
    symbol: () => config.symbol,
    t,
    initialValue: createEmptyMarketData(),
  })
  const {
    roiChartCanvas,
    priceChartCanvas,
    investmentChartCanvas,
    renderCharts,
  } = useDcaCharts({
    theme,
    t,
    result,
  })

  const runSimulation = async () => {
    if (!canRunSimulation.value) {
      errorMessage.value = t('dca.invalidConfig')
      return
    }
    loading.value = true
    errorMessage.value = ''
    try {
      await ensureSymbolCatalogLoaded()
      const payload: SimulateDcaCommand = {
        symbol: config.symbol,
        amount: config.amount,
        start_date: config.start_date || undefined,
        investment_time: config.investment_time,
        timezone: config.timezone,
        strategy: config.strategy || undefined,
        strategy_params: config.strategy_params,
      }
      const response = await toolsApi.runSimulation(payload)
      result.value = {
        ...response,
        current_price: typeof response.current_price !== 'undefined'
          ? response.current_price
          : response.history?.[response.history.length - 1]?.price,
        total_days: response.history?.length ?? response.total_days,
      }
      await fetchMarketIndicators()
      renderCharts()
    } catch (error: unknown) {
      console.error('DCA Error:', error)
      errorMessage.value = apiErrorMessage(error, t('dca.simFailed'))
    } finally {
      loading.value = false
    }
  }

  watch(() => config.strategy, (nextStrategy) => {
    if (nextStrategy === 'ema_deviation') {
      if (!config.strategy_params.multiplier) config.strategy_params.multiplier = multiplierDefault.value
    } else if (['rsi_dynamic', 'fear_greed', 'ahr999'].includes(nextStrategy)) {
      config.strategy_params.multiplier = 1
    }
  })

  watch(timezone, (nextTimezone) => {
    config.timezone = nextTimezone
  })

  watch(() => config.timezone, (nextTimezone) => {
    if (nextTimezone && nextTimezone !== timezone.value) {
      setTimezone(nextTimezone)
    }
  })

  const displayAmount = computed({
    get: () => formatDisplayNumber(config.amount, 'USDT', 2),
    set: (value: number | string) => {
      const converted = fromDisplayAmount(value, 'USDT')
      config.amount = converted ?? config.amount
    },
  })

  watch(() => config.symbol, () => {
    if (isIndexSymbol(config.symbol) && ['ahr999', 'fear_greed'].includes(config.strategy)) {
      config.strategy = 'standard'
    }
  })

  watch(theme, () => {
    if (result.value) {
      renderCharts()
    }
  })

  watch(displayCurrency, () => {
    if (result.value) {
      renderCharts()
    }
  })

  onMounted(async () => {
    const [contractResponse] = await Promise.all([
      toolsApi.getContract(),
      ensureSymbolCatalogLoaded(),
    ])
    if (disposed) return
    strategyKeys.value = [...contractResponse.dca_strategies]
    multiplierDefault.value = contractResponse.dca_multiplier_default
    dcaMaxDays.value = contractResponse.dca_max_days
    const defaultConfig = createDefaultDcaConfig(contractResponse)
    const restoredConfig = pageSnapshot.hasStoredData
      ? normalizeDcaSnapshot(restoredSnapshot, { config: defaultConfig }, strategyKeys.value).config
      : defaultConfig
    Object.assign(config, restoredConfig)
    config.timezone = timezone.value
    if (!snapshotStop) {
      snapshotStop = pageSnapshot.bind(
        config,
        () => buildDcaSnapshot(config, defaultConfig, strategyKeys.value),
      )
    }
    await fetchMarketIndicators()
    if (result.value) {
      renderCharts()
    }
  })

  onBeforeUnmount(() => {
    disposed = true
    snapshotStop?.()
    snapshotStop = null
  })

  const isPositiveRoi = computed(() => (result.value?.roi || 0) >= 0)
  const isIndexSelected = computed(() => isIndexSymbol(config.symbol))
  const dcaStartMin = computed(() => localIsoDateDaysAgo(dcaMaxDays.value))
  const dcaStartMax = todayLocalIsoDate()
  const canRunSimulation = computed(() => (
    Boolean(config.symbol)
    && Number.isFinite(config.amount)
    && config.amount > 0
    && Boolean(config.investment_time)
    && Boolean(config.timezone)
    && Boolean(config.strategy)
    && (!config.start_date || (config.start_date >= dcaStartMin.value && config.start_date <= dcaStartMax))
    && (config.strategy === 'standard' || config.strategy === 'value_averaging' || config.strategy_params.multiplier > 0)
  ))
  const sentimentClass = computed(() => ((marketData.sentiment || 0) >= 50
    ? 'text-green-600 dark:text-green-400'
    : 'text-red-500 dark:text-red-400'))

  return {
    config,
    displayAmount,
    loading,
    errorMessage,
    result,
    marketData,
    roiChartCanvas,
    priceChartCanvas,
    investmentChartCanvas,
    runSimulation,
    isPositiveRoi,
    isIndexSelected,
    dcaStartMin,
    dcaStartMax,
    canRunSimulation,
    sentimentClass,
    displayCurrency,
    formatMoney,
  }
}

