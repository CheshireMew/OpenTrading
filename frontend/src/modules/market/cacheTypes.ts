export interface CacheEntry<TData> {
  data: TData
  timestamp: number
  lastAccessed: number
}

export const MARKET_CACHE_TTL_MS = {
  klineLive: 10_000,
  marketIndicators: 300_000,
  sentimentFresh: 300_000,
  sentimentRefresh: 60_000,
  priceHistory: 1_800_000,
} as const

export const MARKET_CACHE_LIMITS = {
  keyedResource: 64,
} as const

export const isCacheFresh = (
  entry: Pick<CacheEntry<unknown>, 'timestamp'> | null | undefined,
  ttlMs: number,
  now: number = Date.now(),
): boolean => Boolean(entry && now - entry.timestamp < ttlMs)

export const writeCacheEntry = <TData>(
  cache: Record<string, CacheEntry<TData>>,
  key: string,
  data: TData,
  maxEntries: number = MARKET_CACHE_LIMITS.keyedResource,
) => {
  const now = Date.now()
  cache[key] = { data, timestamp: now, lastAccessed: now }
  pruneCacheEntries(cache, maxEntries)
}

export const touchCacheEntry = <TData>(
  cache: Record<string, CacheEntry<TData>>,
  key: string,
): CacheEntry<TData> | undefined => {
  const entry = cache[key]
  if (entry) entry.lastAccessed = Date.now()
  return entry
}

export const pruneCacheEntries = <TData>(
  cache: Record<string, CacheEntry<TData>>,
  maxEntries: number,
) => {
  const keys = Object.keys(cache)
  if (keys.length <= maxEntries) return
  keys
    .sort((left, right) => cache[left].lastAccessed - cache[right].lastAccessed)
    .slice(0, keys.length - maxEntries)
    .forEach((key) => {
      delete cache[key]
    })
}
