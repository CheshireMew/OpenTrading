import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import type { OhlcvPointResponse } from './contracts'
import { marketHistoryApi } from './api'
import { usePriceHistoryStore } from './priceHistoryStore'


export const HALVING_PRICE_SYMBOL = 'BTC/USDT'
export const HALVING_PRICE_TIMEFRAME = '1d'
export const HALVING_HISTORY_START_DATE = '2010-07-01'
const CURRENT_PRICE_REFRESH_INTERVAL_MS = 15_000

export const useHalvingMarketData = (translate: (key: string) => string) => {
  const store = usePriceHistoryStore()
  const currentPrice = ref(0)
  const currentPriceError = ref('')
  const currentPriceUpdatedAt = ref<string | null>(null)
  let refreshTimer: number | null = null
  let refreshPending = false

  const historyResponse = computed(() => store.readPriceHistory(
    HALVING_PRICE_SYMBOL,
    HALVING_PRICE_TIMEFRAME,
    HALVING_HISTORY_START_DATE,
  ))
  const historyData = computed<OhlcvPointResponse[]>(() => (
    (historyResponse.value?.items || []).filter((row) => row.close > 0)
  ))
  const historyError = computed(() => {
    const key = store.getPriceHistoryError(
      HALVING_PRICE_SYMBOL,
      HALVING_PRICE_TIMEFRAME,
      HALVING_HISTORY_START_DATE,
    )
    return key ? translate(key) : ''
  })
  const error = computed(() => historyError.value || currentPriceError.value)
  const loading = computed(() => (
    store.isPriceHistoryLoading(HALVING_PRICE_SYMBOL, HALVING_PRICE_TIMEFRAME, HALVING_HISTORY_START_DATE)
    || (!historyResponse.value && !error.value)
  ))

  const refreshCurrentPrice = async () => {
    try {
      const response = await marketHistoryApi.getCurrentPrice({
        symbol: HALVING_PRICE_SYMBOL,
        timeframe: HALVING_PRICE_TIMEFRAME,
      })
      const price = Number(response?.current_price)
      if (Number.isFinite(price) && price > 0) {
        currentPrice.value = price
        currentPriceError.value = ''
        currentPriceUpdatedAt.value = response.timestamp || new Date().toISOString()
      }
    } catch (requestError) {
      console.error('Refresh halving current price failed', requestError)
      currentPriceError.value = translate('halving.currentPriceLoadFailed')
    }
  }

  const fetchHistory = async (force = false) => {
    try {
      const response = await store.getPriceHistory(
        HALVING_PRICE_SYMBOL,
        HALVING_PRICE_TIMEFRAME,
        HALVING_HISTORY_START_DATE,
        { force },
      )
      const history = (response?.items || []).filter((row) => row.close > 0)
      if (currentPrice.value <= 0 && history.length) {
        currentPrice.value = Number(history[history.length - 1]?.close || 0)
        currentPriceUpdatedAt.value = new Date(history[history.length - 1].timestamp).toISOString()
      }
    } catch (requestError) {
      console.error('Fetch halving history failed', requestError)
    }
  }

  const stopRefresh = () => {
    if (refreshTimer !== null) window.clearInterval(refreshTimer)
    refreshTimer = null
  }

  onMounted(() => {
    void Promise.all([fetchHistory(), refreshCurrentPrice()])
    refreshTimer = window.setInterval(() => {
      if (refreshPending) return
      refreshPending = true
      refreshCurrentPrice().finally(() => { refreshPending = false })
    }, CURRENT_PRICE_REFRESH_INTERVAL_MS)
  })
  onBeforeUnmount(stopRefresh)

  const retry = () => Promise.all([fetchHistory(true), refreshCurrentPrice()])

  return { currentPrice, currentPriceUpdatedAt, historyData, loading, error, retry }
}
