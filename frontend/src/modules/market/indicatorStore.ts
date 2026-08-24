import { defineStore } from 'pinia'
import { marketInsightApi } from './api'
import { resolveSentimentBucket } from './sentiment'
import type { MarketIndicatorResponse, SentimentCache, SentimentData } from './contracts'
import { isCacheFresh, MARKET_CACHE_TTL_MS } from './cacheTypes'
import { createResourceLoader, createResourceState, isResourceLoading, readResource, readResourceError, type ResourceState } from './resourceCache'

interface MarketIndicatorState {
  sentimentCache: SentimentCache
  resources: ResourceState<MarketIndicatorResponse[]>
}

const indicatorResource = createResourceLoader<MarketIndicatorResponse[]>()
const indicatorKey = (category: string | null | undefined, days: number) => `category:${category || 'all'}:days:${days}`

export const useMarketIndicatorStore = defineStore('marketIndicators', {
  state: (): MarketIndicatorState => ({
    sentimentCache: {
      value: null,
      timestamp: 0,
    },
    resources: createResourceState<MarketIndicatorResponse[]>(16),
  }),

  actions: {
    getMarketIndicatorsCacheKey(category: string | null | undefined, days: number): string {
      return indicatorKey(category, days)
    },

    readMarketIndicators(category: string | null | undefined, days: number): MarketIndicatorResponse[] | null {
      return readResource(this.resources, this.getMarketIndicatorsCacheKey(category, days))
    },

    isMarketIndicatorsLoading(category: string | null | undefined, days: number): boolean {
      return isResourceLoading(this.resources, this.getMarketIndicatorsCacheKey(category, days))
    },

    getMarketIndicatorsError(category: string | null | undefined, days: number): string {
      return readResourceError(this.resources, this.getMarketIndicatorsCacheKey(category, days))
    },

    async getMarketIndicators(
      category: string | null | undefined,
      days: number,
      options: { force?: boolean } = {},
    ): Promise<MarketIndicatorResponse[] | null> {
      const key = this.getMarketIndicatorsCacheKey(category, days)
      return indicatorResource.load(this.resources, {
        key,
        ttlMs: MARKET_CACHE_TTL_MS.marketIndicators,
        force: options.force,
        load: async () => {
          const response = await marketInsightApi.getIndicators({ category: category || undefined, days })
          return Array.isArray(response) ? response : []
        },
        errorKey: 'common.marketIndicatorsLoadFailed',
        onError: (error) => {
          console.error('Market indicators fetch failed', error)
        },
      })
    },

    async getSentiment(): Promise<SentimentData | null> {
      const now = Date.now()
      if (this.sentimentCache.value && isCacheFresh(this.sentimentCache, MARKET_CACHE_TTL_MS.sentimentFresh, now)) {
        if (!isCacheFresh(this.sentimentCache, MARKET_CACHE_TTL_MS.sentimentRefresh, now)) {
          this.fetchSentiment()
        }
        return this.sentimentCache.value
      }
      return await this.fetchSentiment()
    },

    async fetchSentiment(): Promise<SentimentData | null> {
      try {
        const res = await this.getMarketIndicators(null, 7)
        if (res && Array.isArray(res)) {
          const fearGreed = res.find((ind) => ind.indicator_id === 'FEAR_GREED')
          if (fearGreed && fearGreed.current_value !== null) {
            const sentimentData: SentimentData = {
              value: fearGreed.current_value,
              label: this.getSentimentLabel(fearGreed.current_value),
              last_updated: fearGreed.last_updated,
            }
            this.sentimentCache = {
              value: sentimentData,
              timestamp: Date.now(),
            }
            return sentimentData
          }
        }
      } catch (e) {
        console.error('Sentiment fetch error', e)
      }
      return null
    },

    getSentimentLabel(value: number): string {
      const labels = {
        extremeFear: 'Extreme Fear',
        fear: 'Fear',
        neutral: 'Neutral',
        greed: 'Greed',
        extremeGreed: 'Extreme Greed',
      }
      return labels[resolveSentimentBucket(value)]
    },
  },
})
