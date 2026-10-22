import { watch, type WatchSource, type WatchStopHandle } from 'vue'
import { getLocalStorage } from '@/utils/storage'
import { readVersionedStorage, writeVersionedStorage } from '@/utils/versionedStorage'
export { isRecord } from '@/utils/typeGuards'

const PAGE_SNAPSHOT_PREFIX = 'opentrading_page_snapshot:'
const PAGE_SNAPSHOT_VERSION = 2
const PAGE_SNAPSHOT_TTL_MS = 1000 * 60 * 60 * 24 * 30

export const PAGE_SNAPSHOT_KEYS = {
  dca: 'tools:dca',
  compare: 'tools:compare',
  portfolioBalance: 'tools:portfolio-balance',
  halving: 'tools:halving',
  binanceMarket: 'indicators:binance-market',
} as const

export const readString = (value: unknown, fallback: string) => (typeof value === 'string' && value ? value : fallback)

export const readNumber = (value: unknown, fallback: number) => (typeof value === 'number' && Number.isFinite(value) ? value : fallback)

export const readBoolean = (value: unknown, fallback: boolean) => (typeof value === 'boolean' ? value : fallback)

export const readStringArray = (value: unknown, fallback: string[] = []) => (
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.length > 0)
    : fallback
)

export const readEnum = <TValue extends string>(
  value: unknown,
  allowed: readonly TValue[],
  fallback: TValue,
): TValue => (
  typeof value === 'string' && (allowed as readonly string[]).includes(value) ? value as TValue : fallback
)

export const readPersistentPageSnapshotData = (key: string, ignoreExpiration = false): unknown | null => {
  return readVersionedStorage<unknown>({
    key: `${PAGE_SNAPSHOT_PREFIX}${key}`,
    label: 'page snapshot',
    version: PAGE_SNAPSHOT_VERSION,
    ttlMs: ignoreExpiration ? Number.POSITIVE_INFINITY : PAGE_SNAPSHOT_TTL_MS,
  })
}

export interface PersistentPageSnapshot<TSnapshot> {
  initial: TSnapshot
  hasStoredData: boolean
  bind: (sources: WatchSource | WatchSource[] | object, buildSnapshot: () => TSnapshot) => WatchStopHandle
  clear: () => void
}

export const createPersistentPageSnapshot = <TSnapshot>(
  key: string,
  normalize: (value: unknown, fallback: TSnapshot) => TSnapshot,
  fallback: TSnapshot,
): PersistentPageSnapshot<TSnapshot> => {
  const storageKey = `${PAGE_SNAPSHOT_PREFIX}${key}`
  const storedData = readPersistentPageSnapshotData(key)
  const load = (): TSnapshot => {
    const data = storedData
    return data === null ? fallback : normalize(data, fallback)
  }

  const save = (snapshot: TSnapshot) => {
    // 本地快照跟随页面结构变化；版本不匹配时直接丢弃，避免旧字段重新灌回新页面。
    writeVersionedStorage({
      key: storageKey,
      label: 'page snapshot',
      version: PAGE_SNAPSHOT_VERSION,
      ttlMs: PAGE_SNAPSHOT_TTL_MS,
    }, normalize(snapshot, fallback))
  }

  return {
    initial: load(),
    hasStoredData: storedData !== null,
    bind(sources: WatchSource | WatchSource[] | object, buildSnapshot: () => TSnapshot) {
      return watch(sources, () => save(buildSnapshot()), { deep: true, immediate: true })
    },
    clear() {
      const storage = getLocalStorage()
      if (storage === null) return
      try {
        storage.removeItem(storageKey)
      } catch (error) {
        console.warn(`Failed to clear page snapshot: ${storageKey}`, error)
      }
    },
  }
}
