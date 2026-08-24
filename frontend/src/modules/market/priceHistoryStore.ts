import { defineStore } from 'pinia'
import { marketHistoryApi } from './api'
import { useKlineStore } from './klineStore'
import type { MarketHistoryResponse } from './contracts'
import { MARKET_CACHE_TTL_MS } from './cacheTypes'
import { createResourceLoader, createResourceState, isResourceLoading, readResource, readResourceError, type ResourceState } from './resourceCache'

interface PriceHistoryState {
  resources: ResourceState<MarketHistoryResponse>
}

const priceHistoryResource = createResourceLoader<MarketHistoryResponse>()
const priceHistoryKey = (symbol: string, timeframe: string, startDate: string) => (
  `symbol:${symbol}:timeframe:${timeframe}:start_date:${startDate}`
)

export const usePriceHistoryStore = defineStore('priceHistory', {
  state: (): PriceHistoryState => ({
    resources: createResourceState<MarketHistoryResponse>(12),
  }),

  actions: {
    getPriceHistoryCacheKey(symbol: string, timeframe: string, startDate: string): string {
      return priceHistoryKey(symbol, timeframe, startDate)
    },

    readPriceHistory(symbol: string, timeframe: string, startDate: string): MarketHistoryResponse | null {
      return readResource(this.resources, this.getPriceHistoryCacheKey(symbol, timeframe, startDate))
    },

    isPriceHistoryLoading(symbol: string, timeframe: string, startDate: string): boolean {
      return isResourceLoading(this.resources, this.getPriceHistoryCacheKey(symbol, timeframe, startDate))
    },

    getPriceHistoryError(symbol: string, timeframe: string, startDate: string): string {
      return readResourceError(this.resources, this.getPriceHistoryCacheKey(symbol, timeframe, startDate))
    },

    async getPriceHistory(
      symbol: string,
      timeframe: string,
      startDate: string,
      options: { force?: boolean } = {},
    ): Promise<MarketHistoryResponse | null> {
      const key = this.getPriceHistoryCacheKey(symbol, timeframe, startDate)
      return priceHistoryResource.load(this.resources, {
        key,
        ttlMs: MARKET_CACHE_TTL_MS.priceHistory,
        force: options.force,
        load: () => marketHistoryApi.getPriceHistory({ symbol, timeframe, start_date: startDate }),
        errorKey: 'common.priceHistoryLoadFailed',
        onError: (error) => {
          console.error('Price history fetch failed', error)
        },
        onWrite: (response) => {
          if (response.items?.length) {
            useKlineStore().setKlineHistory(symbol, timeframe, response.items, response.items.length)
          }
        }
      })
    },
  },
})
