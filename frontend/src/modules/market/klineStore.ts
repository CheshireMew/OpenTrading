import { defineStore } from 'pinia'
import { marketHistoryApi } from './api'
import type { OhlcvPointResponse } from './contracts'
import { isCacheFresh, MARKET_CACHE_TTL_MS, touchCacheEntry, writeCacheEntry } from './cacheTypes'
import { createResourceLoader, createResourceState, type ResourceState } from './resourceCache'

interface KlineState {
  resources: ResourceState<OhlcvPointResponse[]>
}

const klineResource = createResourceLoader<OhlcvPointResponse[]>()

export const useKlineStore = defineStore('marketKline', {
  state: (): KlineState => ({
    resources: createResourceState<OhlcvPointResponse[]>(24),
  }),

  actions: {
    readKlineCache(key: string): OhlcvPointResponse[] {
      return touchCacheEntry(this.resources.cache, key)?.data || []
    },

    readKlineSlice(data: OhlcvPointResponse[] | null | undefined, limit: number): OhlcvPointResponse[] | null {
      if (!Array.isArray(data) || data.length === 0) return null
      if (limit <= 0 || data.length <= limit) return data
      return data.slice(-limit)
    },

    setKlineCache(key: string, data: OhlcvPointResponse[]) {
      writeCacheEntry(this.resources.cache, key, data, this.resources.maxEntries)
    },

    mergeKlines(...batches: Array<OhlcvPointResponse[] | null | undefined>): OhlcvPointResponse[] {
      const merged = new Map<number, OhlcvPointResponse>()
      batches.forEach((batch) => {
        if (!batch) return
        batch.forEach((row) => {
          if (typeof row?.timestamp === 'number') merged.set(row.timestamp, row)
        })
      })
      return Array.from(merged.values()).sort((left, right) => left.timestamp - right.timestamp)
    },

    setKlineHistory(
      symbol: string,
      timeframe: string,
      data: OhlcvPointResponse[],
      maxLength: number = 1000,
    ): OhlcvPointResponse[] {
      const key = `${symbol}:${timeframe}`
      const trimmed = this.mergeKlines(data).slice(-maxLength)
      this.setKlineCache(key, trimmed)
      return trimmed
    },

    async getKlineData(
      symbol: string,
      timeframe: string,
      limit: number = 1000,
      options: { force?: boolean } = {},
    ): Promise<OhlcvPointResponse[] | null> {
      const key = `${symbol}:${timeframe}`
      const now = Date.now()
      const forceRefresh = Boolean(options.force)
      const cachedParams = this.resources.cache[key]
      let cachedData: OhlcvPointResponse[] | null = null

      if (cachedParams) {
        touchCacheEntry(this.resources.cache, key)
        cachedData = cachedParams.data
        if (!forceRefresh && isCacheFresh(cachedParams, MARKET_CACHE_TTL_MS.klineLive, now) && cachedData.length >= limit) {
          return this.readKlineSlice(cachedData, limit)
        }
      }

      let fetchError: unknown = null
      const fetchPromise = klineResource.load(this.resources, {
        key,
        pendingKey: `${key}:limit:${limit}`,
        ttlMs: MARKET_CACHE_TTL_MS.klineLive,
        force: true,
        load: async () => {
          const res = await marketHistoryApi.getLatestKlines({ symbol, timeframe, limit })
          const items = res.items || []
          return items.length ? items : null
        },
        onError: (error) => {
          fetchError = error
          console.error('Kline fetch failed', error)
        },
      }).then((data) => this.readKlineSlice(data, limit))

      if (cachedData && !forceRefresh) {
        fetchPromise.then(() => {})
        return this.readKlineSlice(cachedData, limit)
      }
      const freshData = await fetchPromise
      if (!freshData && !cachedData && fetchError) throw fetchError
      return freshData || this.readKlineSlice(cachedData, limit)
    },

    applyKlineTail(
      symbol: string,
      timeframe: string,
      tail: OhlcvPointResponse[],
      maxLength: number = 1000,
    ): OhlcvPointResponse[] {
      const key = `${symbol}:${timeframe}`
      const current = this.resources.cache[key]?.data || []
      if (tail.length === 0) return current

      const unchanged = tail.every((row) => {
        let low = 0
        let high = current.length - 1
        while (low <= high) {
          const middle = (low + high) >> 1
          const candidate = current[middle]
          if (candidate.timestamp === row.timestamp) {
            return this.sameKline(candidate, row)
          }
          if (candidate.timestamp < row.timestamp) low = middle + 1
          else high = middle - 1
        }
        return false
      })
      if (unchanged) return current

      const trimmed = this.mergeKlines(current, tail).slice(-maxLength)
      this.setKlineCache(key, trimmed)
      return trimmed
    },

    sameKline(left: OhlcvPointResponse, right: OhlcvPointResponse): boolean {
      return left.timestamp === right.timestamp
        && left.open === right.open
        && left.high === right.high
        && left.low === right.low
        && left.close === right.close
        && left.volume === right.volume
    },

    prependKlineHistory(
      symbol: string,
      timeframe: string,
      history: OhlcvPointResponse[],
      maxLength: number = 5000,
    ): OhlcvPointResponse[] {
      const key = `${symbol}:${timeframe}`
      const current = this.resources.cache[key]?.data || []
      const trimmed = this.mergeKlines(history, current).slice(-maxLength)
      this.setKlineCache(key, trimmed)
      return trimmed
    },
  },
})
