import { computed, ref } from 'vue'
import { getLocalStorage, readStorageValue } from '@/utils/storage'

export interface TimezoneOption {
  value: string
  label: string
}

export const TIMEZONE_OPTIONS: TimezoneOption[] = [
  { value: 'UTC', label: 'UTC' },
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (北京)' },
  { value: 'America/New_York', label: 'America/New_York' },
  { value: 'Europe/London', label: 'Europe/London' },
  { value: 'Asia/Tokyo', label: 'Asia/Tokyo' },
]

const STORAGE_KEY = 'opentrading_user_preferences'
const PREFERENCES_VERSION = 2
const DEFAULT_TIMEZONE = 'Asia/Shanghai'
const DEFAULT_DISPLAY_CURRENCY = 'USD'

interface StoredPreferences {
  version?: number
  timezone?: string
  displayCurrency?: string
}

const readStoredPreferences = (): StoredPreferences => {
  const storage = getLocalStorage()
  if (storage === null) return {}
  try {
    const raw = readStorageValue(storage, STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch (error) {
    console.warn('Failed to read user preferences:', error)
    return {}
  }
}

const detectTimezone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || DEFAULT_TIMEZONE
  } catch {
    return DEFAULT_TIMEZONE
  }
}

const persistPreferences = () => {
  getLocalStorage()?.setItem(STORAGE_KEY, JSON.stringify({
    version: PREFERENCES_VERSION,
    timezone: timezone.value,
    displayCurrency: displayCurrency.value,
  }))
}

const resolveStoredCurrency = (preferences: StoredPreferences) => {
  if (
    (preferences.version || 1) < PREFERENCES_VERSION
    && preferences.timezone === DEFAULT_TIMEZONE
    && preferences.displayCurrency?.toUpperCase() === 'CNY'
  ) {
    return DEFAULT_DISPLAY_CURRENCY
  }
  return (preferences.displayCurrency || DEFAULT_DISPLAY_CURRENCY).toUpperCase()
}

const storedPreferences = readStoredPreferences()
const timezone = ref(storedPreferences.timezone || detectTimezone())
const displayCurrency = ref(resolveStoredCurrency(storedPreferences))

export function useUserPreferences() {
  const timezoneOptions = computed(() => {
    const knownValues = new Set(TIMEZONE_OPTIONS.map((item) => item.value))
    if (knownValues.has(timezone.value)) return TIMEZONE_OPTIONS
    return [{ value: timezone.value, label: timezone.value }, ...TIMEZONE_OPTIONS]
  })

  const setTimezone = (value: string) => {
    timezone.value = value || DEFAULT_TIMEZONE
    persistPreferences()
  }

  const setDisplayCurrency = (value: string) => {
    displayCurrency.value = (value || DEFAULT_DISPLAY_CURRENCY).toUpperCase()
    persistPreferences()
  }

  return {
    timezone,
    displayCurrency,
    timezoneOptions,
    setTimezone,
    setDisplayCurrency,
  }
}
