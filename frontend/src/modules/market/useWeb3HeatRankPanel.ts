import { computed, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  BinanceWeb3HeatRankBoardsResponse,
  BinanceWeb3HeatRankItemResponse,
  BinanceWeb3HeatRankResponse,
  BinanceWeb3TokenAuditResponse,
  BinanceWeb3TokenDynamicResponse,
  BinanceWeb3TokenKlineItemResponse,
} from './contracts'
import { binanceWeb3Api } from './api'
import type { CandlestickData, VolumeData } from './contracts'
import { web3HeatRankWarmSnapshot } from './web3MarketWarmSnapshot'
import {
  web3ApiChainId,
  type Web3HeatRankSortField,
  type Web3HeatRankSortState,
  type Web3TokenDialogState,
} from './web3MarketShared'

const WEB3_HEAT_RANK_SIZE = 30

export function useWeb3HeatRankPanel(chainId: Ref<string>) {
  const { t } = useI18n()
  const web3HeatRankBoards = ref<Record<string, BinanceWeb3HeatRankResponse>>({})
  const web3Sort = ref<Web3HeatRankSortState>({ field: 'heat_score', direction: 'desc' })
  const web3Loading = ref(false)
  const web3ErrorKey = ref('')
  const web3Error = computed(() => (web3ErrorKey.value ? t(web3ErrorKey.value) : ''))
  const web3UpdatedAt = ref<string | null>(null)
  const web3Dialog = ref<Web3TokenDialogState>({ open: false, token: null })
  const web3DetailLoading = ref(false)
  const web3DetailErrorKey = ref('')
  const web3DetailError = computed(() => (web3DetailErrorKey.value ? t(web3DetailErrorKey.value) : ''))
  const web3Dynamic = ref<BinanceWeb3TokenDynamicResponse | null>(null)
  const web3Audit = ref<BinanceWeb3TokenAuditResponse | null>(null)
  const web3Kline = ref<BinanceWeb3TokenKlineItemResponse[]>([])
  const web3KlineInterval = ref('15min')
  let heatRankFetchState: { key: string; task: Promise<void> } | null = null

  const web3ChartData = computed<CandlestickData[]>(() => (
    web3Kline.value
      .filter((item) => item.open_time && item.open != null && item.high != null && item.low != null && item.close != null)
      .map((item) => ({
        time: Math.floor(Number(item.open_time) / 1000),
        open: Number(item.open),
        high: Number(item.high),
        low: Number(item.low),
        close: Number(item.close),
      }))
  ))

  const web3VolumeData = computed<VolumeData[]>(() => (
    web3Kline.value
      .filter((item) => item.open_time && item.volume != null)
      .map((item) => ({
        time: Math.floor(Number(item.open_time) / 1000),
        value: Number(item.volume),
        color: Number(item.close ?? 0) >= Number(item.open ?? 0) ? '#10b98188' : '#ef444488',
      }))
  ))

  const web3HeatRank = computed(() => (
    web3HeatRankBoards.value[web3HeatRankBoardKey(web3Sort.value.field, web3Sort.value.direction)]?.items || []
  ))

  const applyHeatRankPayload = (payload: Awaited<ReturnType<typeof binanceWeb3Api.getBinanceWeb3HeatRankBoards>>) => {
    web3HeatRankBoards.value = payload.boards || {}
  }

  const restoreHeatRankWarmSnapshot = () => {
    const payload = web3HeatRankWarmSnapshot.read(chainId.value, WEB3_HEAT_RANK_SIZE)
    if (payload) {
      applyHeatRankPayload(payload)
      web3ErrorKey.value = ''
      return true
    }
    return false
  }

  const heatRankRequestKey = () => `${chainId.value}:${WEB3_HEAT_RANK_SIZE}`

  const fetchWeb3HeatRank = async () => {
    const requestChainId = chainId.value
    const requestKey = heatRankRequestKey()
    if (heatRankFetchState?.key === requestKey) return heatRankFetchState.task
    let task!: Promise<void>
    task = (async () => {
      web3Loading.value = true
      web3ErrorKey.value = ''
      try {
        const response = await binanceWeb3Api.getBinanceWeb3HeatRankBoards({
          chain_id: web3ApiChainId(requestChainId),
          size: WEB3_HEAT_RANK_SIZE,
        })
        if (requestKey !== heatRankRequestKey()) return
        applyHeatRankPayload(response)
        web3UpdatedAt.value = new Date().toISOString()
        web3HeatRankWarmSnapshot.write(response, requestChainId, WEB3_HEAT_RANK_SIZE)
      } catch (requestError) {
        if (requestKey !== heatRankRequestKey()) return
        web3ErrorKey.value = web3HeatRank.value.length
          ? 'web3Rank.heatRankRefreshFailedWithCache'
          : 'web3Rank.heatRankLoadFailed'
        console.error('Failed to load Binance Web3 heat rank', requestError)
      } finally {
        if (heatRankFetchState?.key === requestKey && heatRankFetchState.task === task) {
          web3Loading.value = false
        }
      }
    })()
    heatRankFetchState = { key: requestKey, task }
    try {
      await task
    } finally {
      if (heatRankFetchState?.key === requestKey && heatRankFetchState.task === task) {
        heatRankFetchState = null
      }
    }
  }

  const loadWeb3TokenDetail = async () => {
    const token = web3Dialog.value.token
    if (!web3Dialog.value.open || !token?.chain_id || !token?.contract_address || !token?.platform) return
    web3DetailLoading.value = true
    web3DetailErrorKey.value = ''
    try {
      const [dynamicRes, auditRes, klineRes] = await Promise.all([
        binanceWeb3Api.getBinanceWeb3TokenDynamic({
          chain_id: token.chain_id,
          contract_address: token.contract_address,
        }),
        binanceWeb3Api.getBinanceWeb3TokenAudit({
          binance_chain_id: token.chain_id,
          contract_address: token.contract_address,
        }),
        binanceWeb3Api.getBinanceWeb3TokenKline({
          address: token.contract_address,
          platform: token.platform,
          interval: web3KlineInterval.value,
          limit: 240,
        }),
      ])
      web3Dynamic.value = dynamicRes
      web3Audit.value = auditRes
      web3Kline.value = klineRes?.items || []
    } catch (requestError) {
      web3DetailErrorKey.value = 'web3Rank.tokenDetailLoadFailed'
      web3Dynamic.value = null
      web3Audit.value = null
      web3Kline.value = []
      console.error('Failed to load Web3 token detail', requestError)
    } finally {
      web3DetailLoading.value = false
    }
  }

  const openWeb3Token = (token: BinanceWeb3HeatRankItemResponse) => {
    if (!token.chain_id || !token.contract_address) return
    web3Dialog.value = { open: true, token }
    void loadWeb3TokenDetail()
  }

  const closeWeb3Token = () => {
    web3Dialog.value = { open: false, token: null }
    web3Dynamic.value = null
    web3Audit.value = null
    web3Kline.value = []
    web3DetailErrorKey.value = ''
  }

  const toggleWeb3Sort = (field: Web3HeatRankSortField) => {
    if (web3Sort.value.field === field) {
      web3Sort.value = {
        ...web3Sort.value,
        direction: web3Sort.value.direction === 'desc' ? 'asc' : 'desc',
      }
      return
    }
    web3Sort.value = { field, direction: 'desc' }
  }

  watch(chainId, () => {
    if (!restoreHeatRankWarmSnapshot()) web3HeatRankBoards.value = {}
    void fetchWeb3HeatRank()
  })

  watch(web3KlineInterval, () => {
    void loadWeb3TokenDetail()
  })

  restoreHeatRankWarmSnapshot()

  return {
    web3HeatRank,
    web3Sort,
    web3Loading,
    web3Error,
    web3UpdatedAt,
    web3Dialog,
    web3Dynamic,
    web3Audit,
    web3DetailLoading,
    web3DetailError,
    web3KlineInterval,
    web3ChartData,
    web3VolumeData,
    fetchWeb3HeatRank,
    toggleWeb3Sort,
    openWeb3Token,
    closeWeb3Token,
  }
}

const web3HeatRankBoardKey = (field: Web3HeatRankSortField, direction: Web3HeatRankSortState['direction']) => `${field}_${direction}`

