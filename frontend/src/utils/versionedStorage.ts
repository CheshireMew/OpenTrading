import { getLocalStorage } from '@/utils/storage'
import { isRecord } from '@/utils/typeGuards'

interface VersionedStorageEnvelope<TPayload> {
  version: number
  savedAt: number
  data: TPayload
}

interface VersionedStorageOptions<TPayload> {
  key: string
  label: string
  version: number
  ttlMs: number
  validate?: (payload: unknown) => payload is TPayload
}

export const readVersionedStorage = <TPayload>(
  options: VersionedStorageOptions<TPayload>,
): TPayload | null => {
  const storage = getLocalStorage()
  if (storage === null) return null
  try {
    const stored = storage.getItem(options.key)
    if (!stored) return null
    const parsed: unknown = JSON.parse(stored)
    if (!isRecord(parsed)) return null
    if (parsed.version !== options.version) return null
    if (typeof parsed.savedAt !== 'number' || Date.now() - parsed.savedAt > options.ttlMs) return null
    if (!('data' in parsed)) return null
    if (options.validate && !options.validate(parsed.data)) return null
    return parsed.data as TPayload
  } catch (error) {
    console.warn(`Failed to restore ${options.label}: ${options.key}`, error)
    return null
  }
}

export const writeVersionedStorage = <TPayload>(
  options: VersionedStorageOptions<TPayload>,
  payload: TPayload,
) => {
  const storage = getLocalStorage()
  if (storage === null) return
  try {
    const envelope: VersionedStorageEnvelope<TPayload> = {
      version: options.version,
      savedAt: Date.now(),
      data: payload,
    }
    storage.setItem(options.key, JSON.stringify(envelope))
  } catch (error) {
    console.warn(`Failed to save ${options.label}: ${options.key}`, error)
  }
}
