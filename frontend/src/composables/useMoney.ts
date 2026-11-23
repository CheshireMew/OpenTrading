import { computed } from 'vue'
import { useUserPreferences } from './useUserPreferences'
import {
  currencyAliases,
  currencyRates as rates,
  loadCurrencyRates,
  loadingRates,
  ratesAreFallback,
  ratesSource,
  ratesUpdatedAt,
  readCurrencyMeta,
  resolveCurrencyAlias,
  supportedCurrencies,
} from '@/modules/system'
import { asNumber } from '@/utils/number'

const normalizeCurrency = (value: string | null | undefined) => {
  return resolveCurrencyAlias(value || 'USD')
}

export function useMoney() {
  const { displayCurrency, setDisplayCurrency } = useUserPreferences()

  const currencyOptions = computed(() => supportedCurrencies.value.map((item) => ({
    value: item.code,
    label: `${item.code} · ${item.name}`,
  })))

  const selectedCurrencyMeta = computed(() => readCurrencyMeta(displayCurrency.value))

  const convertMoney = (
    value: unknown,
    sourceCurrency = 'USD',
    targetCurrency = displayCurrency.value,
  ) => {
    const numeric = value == null || value === '' ? null : asNumber(value)
    if (numeric === null) return null
    const source = normalizeCurrency(sourceCurrency)
    const target = normalizeCurrency(targetCurrency)
    const sourceRate = rates.value[source] || 1
    const targetRate = rates.value[target] || 1
    return (numeric / sourceRate) * targetRate
  }

  const fromDisplayAmount = (value: unknown, targetSourceCurrency = 'USD') => (
    convertMoney(value, displayCurrency.value, targetSourceCurrency)
  )

  const toDisplayAmount = (value: unknown, sourceCurrency = 'USD') => (
    convertMoney(value, sourceCurrency, displayCurrency.value)
  )

  const formatMoney = (
    value: unknown,
    sourceCurrency = 'USD',
    options: Intl.NumberFormatOptions = {},
  ) => {
    const converted = toDisplayAmount(value, sourceCurrency)
    if (converted === null) return '--'
    const meta = selectedCurrencyMeta.value
    const absolute = Math.abs(converted)
    const usesSignificantDigits = options.maximumSignificantDigits !== undefined || options.minimumSignificantDigits !== undefined
    const maximumFractionDigits: number | undefined = usesSignificantDigits
      ? undefined
      : options.maximumFractionDigits ?? (absolute >= 1000 ? meta.fraction_digits : Math.max(meta.fraction_digits, 4))
    const minimumFractionDigits: number | undefined = usesSignificantDigits
      ? undefined
      : Math.min(options.minimumFractionDigits ?? meta.fraction_digits, maximumFractionDigits ?? meta.fraction_digits)
    return new Intl.NumberFormat(meta.locale, {
      ...options,
      style: 'currency',
      currency: meta.code,
      minimumFractionDigits,
      maximumFractionDigits,
    }).format(converted)
  }

  const formatCompactMoney = (value: unknown, sourceCurrency = 'USD') => (
    formatMoney(value, sourceCurrency, { notation: 'compact', maximumFractionDigits: 2 })
  )

  const formatSignedMoney = (value: unknown, sourceCurrency = 'USD') => {
    const numeric = value == null || value === '' ? null : asNumber(value)
    if (numeric === null) return '--'
    return `${numeric >= 0 ? '+' : '-'}${formatMoney(Math.abs(numeric), sourceCurrency)}`
  }

  const formatDisplayNumber = (value: unknown, sourceCurrency = 'USD', maximumFractionDigits = 2) => {
    const converted = toDisplayAmount(value, sourceCurrency)
    if (converted === null) return ''
    return Number(converted.toFixed(maximumFractionDigits))
  }

  return {
    displayCurrency,
    currencyOptions,
    selectedCurrencyMeta,
    currencyAliases,
    rates,
    ratesSource,
    ratesUpdatedAt,
    ratesAreFallback,
    loadingRates,
    setDisplayCurrency,
    loadCurrencyRates,
    normalizeCurrency,
    convertMoney,
    fromDisplayAmount,
    toDisplayAmount,
    formatMoney,
    formatCompactMoney,
    formatSignedMoney,
    formatDisplayNumber,
  }
}
