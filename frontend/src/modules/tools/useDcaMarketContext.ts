import { reactive } from 'vue'

import { isRecord } from '@/composables/pageSnapshot'
import { ensureSymbolCatalogLoaded, isIndexSymbol, marketIndexApi, marketInsightApi, marketLiveApi, toBaseSymbol } from '@/modules/market'
import { resolveSentimentBucket } from '@/modules/market/sentiment'
import { localIsoDateDaysAgo } from '@/utils/localDate'
import type { MarketIndexHistoryResponse, RealtimeResponse } from '@/modules/market/contracts'

export interface DcaMarketState {
  rsi: string | null
  sentiment: number | null
  sentimentLabel: string
  currentPrice: number | null
  pricingCurrency: string
  pricingSymbol: string
  loading: boolean
  error: string
  updatedAt: string | null
}

export const createEmptyMarketData = (): DcaMarketState => ({
  rsi: null,
  sentiment: null,
  sentimentLabel: '',
  currentPrice: null,
  pricingCurrency: 'USDT',
  pricingSymbol: '',
  loading: false,
  error: '',
  updatedAt: null,
})

export const normalizeMarketData = (value: unknown): DcaMarketState => {
  if (!isRecord(value)) return createEmptyMarketData()
  return {
    rsi: typeof value.rsi === 'string' ? value.rsi : null,
    sentiment: typeof value.sentiment === 'number' ? value.sentiment : null,
    sentimentLabel: typeof value.sentimentLabel === 'string' ? value.sentimentLabel : '',
    currentPrice: typeof value.currentPrice === 'number' ? value.currentPrice : null,
    pricingCurrency: typeof value.pricingCurrency === 'string' ? value.pricingCurrency : 'USDT',
    pricingSymbol: typeof value.pricingSymbol === 'string' ? value.pricingSymbol : '',
    loading: false,
    error: '',
    updatedAt: typeof value.updatedAt === 'string' ? value.updatedAt : null,
  }
}

interface UseDcaMarketContextOptions {
  symbol: () => string
  t: (key: string) => string
  initialValue?: DcaMarketState
}

export const useDcaMarketContext = ({
  symbol,
  t,
  initialValue,
}: UseDcaMarketContextOptions) => {
  const marketData = reactive(normalizeMarketData(initialValue))
  let requestGeneration = 0

  const sentimentLabel = (value: number) => {
    const key = resolveSentimentBucket(value)
    return t(`dca.fgLabels.${key}`)
  }

  const fetchMarketIndicators = async () => {
    const generation = ++requestGeneration
    marketData.loading = true
    marketData.error = ''
    try {
      await ensureSymbolCatalogLoaded()
      const currentSymbol = symbol()
      const [marketResult, indicatorsResult] = await Promise.allSettled([
        isIndexSymbol(currentSymbol)
          ? marketIndexApi.getIndexPricingHistory({
              symbol: currentSymbol,
              timeframe: '1d',
              start_date: localIsoDateDaysAgo(180),
            })
          : marketLiveApi.getRealtime({ symbol: currentSymbol, timeframe: '1d', limit: 100 }),
        marketInsightApi.getIndicators({ days: 7 }),
      ])

      if (generation !== requestGeneration || currentSymbol !== symbol()) return

      const failures: string[] = []
      if (marketResult.status === 'fulfilled') {
        const marketRes = marketResult.value
        if (isIndexSymbol(currentSymbol)) {
          const indexResponse = marketRes as MarketIndexHistoryResponse
          const latest = indexResponse.data?.[indexResponse.data.length - 1]
          marketData.rsi = '--'
          marketData.currentPrice = latest?.close ?? null
          marketData.pricingCurrency = indexResponse.pricing_currency || indexResponse.currency || 'USD'
          marketData.pricingSymbol = indexResponse.pricing_symbol || indexResponse.symbol
        } else {
          const realtimeResponse = marketRes as RealtimeResponse
          marketData.rsi = realtimeResponse.indicators?.rsi?.toFixed(2) || '--'
          marketData.currentPrice = realtimeResponse.current_price
          marketData.pricingCurrency = 'USDT'
          marketData.pricingSymbol = `${toBaseSymbol(currentSymbol)}/USDT`
        }
      } else {
        marketData.rsi = null
        marketData.currentPrice = null
        failures.push(t('dca.marketPriceLoadFailed'))
      }

      if (indicatorsResult.status === 'fulfilled') {
        const fearGreed = (indicatorsResult.value || []).find((item) => item.indicator_id === 'FEAR_GREED')
        marketData.sentiment = fearGreed?.current_value ?? null
        marketData.sentimentLabel = fearGreed?.current_value == null ? '' : sentimentLabel(fearGreed.current_value)
      } else {
        marketData.sentiment = null
        marketData.sentimentLabel = ''
        failures.push(t('dca.sentimentLoadFailed'))
      }
      marketData.error = failures.join(' ')
      marketData.updatedAt = new Date().toISOString()
    } catch (error) {
      console.warn('Failed to fetch market indicators:', error)
      if (generation === requestGeneration) marketData.error = t('dca.marketLoadFailed')
    } finally {
      if (generation === requestGeneration) marketData.loading = false
    }
  }

  return {
    marketData,
    fetchMarketIndicators,
  }
}

