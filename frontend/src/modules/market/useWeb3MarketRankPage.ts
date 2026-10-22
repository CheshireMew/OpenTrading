import { DARK_PALETTE } from '@/theme/palette.mjs'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useTheme } from '@/composables/useTheme'
import { formatAdaptivePrice, formatCompactNumber, formatSignedPercent } from '@/modules/format'
import { binanceWeb3Api } from './api'
import type {
  BinanceWeb3AddressPnlItemResponse,
} from './contracts'
import { formatScore, sortDirectionIcon } from './binanceMarketShared'
import { useWeb3HeatRankPanel } from './useWeb3HeatRankPanel'
import {
  WEB3_ALL_CHAIN_ID,
  WEB3_SUPPORTED_CHAIN_OPTIONS,
  web3ApiChainId,
  WEB3_KLINE_INTERVALS,
} from './web3MarketShared'

const changeClass = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'text-slate-500 dark:text-slate-400'
  return value >= 0 ? 'text-emerald-500' : 'text-rose-500'
}

export function useWeb3MarketRankPage() {
  const { t } = useI18n()
  const { theme } = useTheme()
  const loading = ref(false)
  const errorKey = ref('')
  const error = computed(() => (errorKey.value ? t(errorKey.value) : ''))
  const chainId = ref(WEB3_ALL_CHAIN_ID)
  const heatRank = useWeb3HeatRankPanel(chainId)
  const addressPnl = ref<BinanceWeb3AddressPnlItemResponse[]>([])
  const addressPnlUpdatedAt = ref<string | null>(null)
  let addressPnlFetchState: { key: string; task: Promise<void> } | null = null

  const chainOptions = computed(() => (
    [
      { label: t('web3Rank.allChains'), value: WEB3_ALL_CHAIN_ID },
      ...WEB3_SUPPORTED_CHAIN_OPTIONS,
    ]
  ))

  const web3ChartColors = computed(() => {
    const isDark = theme.value === 'dark'
    return {
      bg: isDark ? DARK_PALETTE.canvas : '#ffffff',
      grid: isDark ? DARK_PALETTE.grid : '#e2e8f0',
      text: isDark ? DARK_PALETTE.muted : '#475569',
      upColor: isDark ? DARK_PALETTE.positive : '#10b981',
      downColor: isDark ? DARK_PALETTE.negative : '#ef4444',
    }
  })

  const addressPnlRequestKey = () => chainId.value

  const fetchData = async () => {
    const requestChainId = chainId.value
    const requestKey = addressPnlRequestKey()
    if (addressPnlFetchState?.key === requestKey) return addressPnlFetchState.task
    let task!: Promise<void>
    task = (async () => {
      loading.value = true
      errorKey.value = ''
      try {
        const selectedChainId = web3ApiChainId(requestChainId)
        const pnlRes = await binanceWeb3Api.getBinanceWeb3AddressPnlRank({ chain_id: selectedChainId || '56', page_size: 10 })
        if (requestKey !== addressPnlRequestKey()) return
        addressPnl.value = pnlRes?.items || []
        addressPnlUpdatedAt.value = new Date().toISOString()
      } catch (err) {
        if (requestKey !== addressPnlRequestKey()) return
        console.error('Failed to load Binance Web3 rank page', err)
        errorKey.value = 'web3Rank.loadFailed'
      } finally {
        if (addressPnlFetchState?.key === requestKey && addressPnlFetchState.task === task) {
          loading.value = false
        }
      }
    })()
    addressPnlFetchState = { key: requestKey, task }
    try {
      await task
    } finally {
      if (addressPnlFetchState?.key === requestKey && addressPnlFetchState.task === task) {
        addressPnlFetchState = null
      }
    }
  }

  watch(chainId, fetchData)

  onMounted(() => {
    void fetchData()
    void heatRank.fetchWeb3HeatRank()
  })

  const updatedAt = computed(() => {
    const timestamps = [addressPnlUpdatedAt.value, heatRank.web3UpdatedAt.value]
      .filter((value): value is string => Boolean(value))
      .sort()
    return timestamps.length ? timestamps[timestamps.length - 1] : null
  })

  return {
    loading,
    error,
    chainId,
    chainOptions,
    addressPnl,
    updatedAt,
    web3HeatRank: heatRank.web3HeatRank,
    web3Loading: heatRank.web3Loading,
    web3Error: heatRank.web3Error,
    web3Dialog: heatRank.web3Dialog,
    web3Dynamic: heatRank.web3Dynamic,
    web3Audit: heatRank.web3Audit,
    web3DetailLoading: heatRank.web3DetailLoading,
    web3DetailError: heatRank.web3DetailError,
    web3KlineInterval: heatRank.web3KlineInterval,
    web3KlineIntervals: WEB3_KLINE_INTERVALS,
    web3ChartData: heatRank.web3ChartData,
    web3VolumeData: heatRank.web3VolumeData,
    web3ChartColors,
    web3Sort: heatRank.web3Sort,
    fetchWeb3HeatRank: heatRank.fetchWeb3HeatRank,
    toggleWeb3Sort: heatRank.toggleWeb3Sort,
    openWeb3Token: heatRank.openWeb3Token,
    closeWeb3Token: heatRank.closeWeb3Token,
    fetchData,
    formatScore,
    formatPercent: formatSignedPercent,
    formatPrice: (value: number | null | undefined) => formatAdaptivePrice(value, 'USDT', '--'),
    formatCompact: formatCompactNumber,
    sortDirectionIcon,
    changeClass,
  }
}

