import { readVersionedStorage, writeVersionedStorage } from '@/utils/versionedStorage'

const STORAGE_SCHEMA_VERSION = 3
const STORAGE_TTL_MS = 1000 * 60 * 60 * 12

const readMarketWarmSnapshot = <TPayload>(storageKey: string, label: string): TPayload | null => {
  return readVersionedStorage<TPayload>({
    key: storageKey,
    label,
    version: STORAGE_SCHEMA_VERSION,
    ttlMs: STORAGE_TTL_MS,
  })
}

const writeMarketWarmSnapshot = <TPayload>(storageKey: string, label: string, payload: TPayload) => {
  writeVersionedStorage({
    key: storageKey,
    label,
    version: STORAGE_SCHEMA_VERSION,
    ttlMs: STORAGE_TTL_MS,
  }, payload)
}

export const createWarmSnapshotStore = <TPayload, TArgs extends readonly unknown[]>(options: {
  label: string
  key: (...args: TArgs) => string
  validate: (payload: TPayload, ...args: TArgs) => boolean
  hasContent: (payload: TPayload) => boolean
}) => ({
  read(...args: TArgs): TPayload | null {
    const payload = readMarketWarmSnapshot<TPayload>(options.key(...args), options.label)
    if (!payload || !options.validate(payload, ...args)) return null
    return payload
  },
  write(payload: TPayload, ...args: TArgs) {
    if (!options.hasContent(payload)) return
    writeMarketWarmSnapshot(options.key(...args), options.label, payload)
  },
})

