import { computed, ref } from 'vue'

import type { CurrencyRatesResponse, DisplayCurrencyResponse } from './contracts'

import { systemApi } from './api'

export const currencyRates = ref<Record<string, number>>({})
export const supportedCurrencies = ref<DisplayCurrencyResponse[]>([])
export const currencyAliases = ref<Record<string, string>>({})
export const ratesSource = ref('')
export const ratesUpdatedAt = ref('')
export const ratesAreFallback = ref(false)
export const loadingRates = ref(false)

let ratesPromise: Promise<boolean> | null = null

export const currencyMetaByCode = computed(() => {
  const map = new Map<string, DisplayCurrencyResponse>()
  supportedCurrencies.value.forEach((item) => map.set(item.code, item))
  return map
})

export const loadCurrencyRates = async () => {
  if (ratesPromise) return ratesPromise
  loadingRates.value = true
  ratesPromise = systemApi.getCurrencyRates()
    .then((response) => {
      applyCurrencyRates(response)
      return true
    })
    .catch((error) => {
      console.warn('Failed to load currency rates:', error)
      return false
    })
    .finally(() => {
      loadingRates.value = false
      ratesPromise = null
    })
  return ratesPromise
}

export const resolveCurrencyAlias = (code: string) => {
  const normalized = String(code || 'USD').trim().toUpperCase()
  if (!normalized) return 'USD'
  return currencyAliases.value[normalized] || normalized
}

const applyCurrencyRates = (payload: CurrencyRatesResponse) => {
  currencyRates.value = { ...(payload?.rates || {}) }
  supportedCurrencies.value = payload?.supported || []
  currencyAliases.value = payload?.aliases || {}
  ratesSource.value = payload?.source || ''
  ratesUpdatedAt.value = payload?.updated_at || ''
  ratesAreFallback.value = !!payload?.is_fallback
}

export const readCurrencyMeta = (code: string) => {
  const resolvedCode = resolveCurrencyAlias(code)
  return (
    currencyMetaByCode.value.get(resolvedCode)
    || supportedCurrencies.value[0]
    || {
      code: 'USD',
      name: 'US Dollar',
      symbol: '$',
      locale: 'en-US',
      fraction_digits: 2,
    }
  )
}

