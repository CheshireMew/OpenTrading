type PromiseCacheEntry<T> = {
  promise: Promise<T>
  expiresAt: number
}

type PromiseCacheOptions<T> = {
  maxEntries: number
  ttlMs: number
  clone: (value: T) => T
  now?: () => number
}

export const createPromiseLruCache = <T>({
  maxEntries,
  ttlMs,
  clone,
  now = Date.now,
}: PromiseCacheOptions<T>) => {
  const entries = new Map<string, PromiseCacheEntry<T>>()

  const load = (key: string, loader: () => Promise<T>): Promise<T> => {
    const cached = entries.get(key)
    if (cached && cached.expiresAt > now()) {
      entries.delete(key)
      entries.set(key, cached)
      return cached.promise.then(clone)
    }
    if (cached) entries.delete(key)

    const promise = loader()
    entries.set(key, { promise, expiresAt: now() + ttlMs })
    void promise.catch(() => {
      if (entries.get(key)?.promise === promise) entries.delete(key)
    })

    while (entries.size > maxEntries) {
      const oldestKey = entries.keys().next().value
      if (oldestKey === undefined) break
      entries.delete(oldestKey)
    }
    return promise.then(clone)
  }

  return { load }
}
