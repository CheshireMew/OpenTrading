import { isCacheFresh, touchCacheEntry, writeCacheEntry, type CacheEntry } from './cacheTypes'

export type ResourceState<TData> = {
  cache: Record<string, CacheEntry<TData>>
  loading: Record<string, boolean>
  errors: Record<string, string>
  maxEntries: number
}

type ResourceLoadOptions<TData> = {
  key: string
  pendingKey?: string
  ttlMs: number
  force?: boolean
  load: () => Promise<TData | null>
  errorKey?: string
  onError?: (error: unknown) => void
  onWrite?: (data: TData) => void
}

export const createResourceState = <TData>(maxEntries: number = 16): ResourceState<TData> => ({
  cache: {},
  loading: {},
  errors: {},
  maxEntries,
})

export const readResource = <TData>(state: ResourceState<TData>, key: string): TData | null => (
  touchCacheEntry(state.cache, key)?.data ?? null
)

export const isResourceLoading = <TData>(state: ResourceState<TData>, key: string) => Boolean(state.loading[key])

export const readResourceError = <TData>(state: ResourceState<TData>, key: string) => state.errors[key] || ''

export const createResourceLoader = <TData>() => {
  const pending = new Map<string, Promise<unknown>>()

  const pruneErrors = (state: ResourceState<TData>) => {
    const keys = Object.keys(state.errors)
    keys.slice(0, Math.max(keys.length - state.maxEntries, 0)).forEach((key) => {
      delete state.errors[key]
    })
  }

  const load = async (state: ResourceState<TData>, options: ResourceLoadOptions<TData>): Promise<TData | null> => {
    const entry = state.cache[options.key]
    if (!options.force && isCacheFresh(entry, options.ttlMs)) {
      touchCacheEntry(state.cache, options.key)
      return entry.data
    }

    const pendingKey = options.pendingKey ?? options.key
    const active = pending.get(pendingKey) as Promise<TData | null> | undefined
    if (active) return active

    state.loading[options.key] = true
    delete state.errors[options.key]
    const request = (async () => {
      try {
        const data = await options.load()
        if (data !== null) {
          writeCacheEntry(state.cache, options.key, data, state.maxEntries)
          delete state.errors[options.key]
          options.onWrite?.(data)
          return data
        }
      } catch (error) {
        state.errors[options.key] = options.errorKey || ''
        pruneErrors(state)
        options.onError?.(error)
      } finally {
        pending.delete(pendingKey)
        delete state.loading[options.key]
      }
      return state.cache[options.key]?.data ?? null
    })()

    pending.set(pendingKey, request)
    return request
  }

  return { load }
}
