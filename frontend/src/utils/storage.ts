let legacyKeysCopied = false

export const getLocalStorage = (): Storage | null => {
  if (typeof window === 'undefined') return null
  try {
    // Some browser modes expose window but throw while reading localStorage.
    const storage = window.localStorage
    if (!legacyKeysCopied) {
      try {
        const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index))
        for (const key of keys) {
          if (!key?.startsWith('heimdall')) continue
          const nextKey = 'opentrading' + key.slice('heimdall'.length)
          const value = storage.getItem(key)
          if (value !== null && storage.getItem(nextKey) === null) storage.setItem(nextKey, value)
        }
        legacyKeysCopied = true
      } catch {
        // Reads below can still fall back when storage is full or read-only.
      }
    }
    return storage
  } catch {
    return null
  }
}

export const readStorageValue = (storage: Storage, key: string): string | null => (
  storage.getItem(key) ?? (key.startsWith('opentrading')
    ? storage.getItem('heimdall' + key.slice('opentrading'.length)) : null)
)
