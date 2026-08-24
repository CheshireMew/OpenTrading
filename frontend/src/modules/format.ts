import { useDateTime } from '@/composables/useDateTime'
import { useMoney } from '@/composables/useMoney'
import { asNumber } from '@/utils/number'

let moneyFormatter: ReturnType<typeof useMoney> | null = null
let dateTimeFormatter: ReturnType<typeof useDateTime> | null = null

const money = () => {
  moneyFormatter ??= useMoney()
  return moneyFormatter
}

const dateTime = () => {
  dateTimeFormatter ??= useDateTime()
  return dateTimeFormatter
}

type PercentOptions = {
  empty?: string
  signed?: boolean
}

export const formatMetric = (value: unknown, digits = 2, empty = '-') => {
  const numeric = asNumber(value)
  return numeric === null ? empty : numeric.toFixed(digits)
}

export const formatPercent = (value: unknown, digits = 2, options: PercentOptions = {}) => {
  const numeric = asNumber(value)
  if (numeric === null) return options.empty ?? '-'
  const sign = options.signed && numeric > 0 ? '+' : ''
  return `${sign}${numeric.toFixed(digits)}%`
}

export const formatSignedPercent = (value: unknown, digits = 2, empty = '--') => (
  formatPercent(value, digits, { empty, signed: true })
)

export const formatRatioPercent = (value: unknown, digits = 2, options: PercentOptions = {}) => {
  const numeric = asNumber(value)
  return numeric === null ? options.empty ?? '--' : formatPercent(numeric * 100, digits, options)
}

export const formatMoney = (
  value: unknown,
  sourceCurrency = 'USDT',
  options: Intl.NumberFormatOptions = { maximumFractionDigits: 2 },
  empty = '-',
) => {
  const numeric = asNumber(value)
  return numeric === null ? empty : money().formatMoney(numeric, sourceCurrency, options)
}

export const formatPrice = (
  value: unknown,
  sourceCurrency = 'USDT',
  options: Intl.NumberFormatOptions = { maximumFractionDigits: 4 },
  empty = '-',
) => formatMoney(value, sourceCurrency, options, empty)

export const formatAdaptivePrice = (value: unknown, sourceCurrency = 'USDT', empty = '-') => {
  const numeric = asNumber(value)
  if (numeric === null) return empty
  if (numeric >= 1000) return formatMoney(numeric, sourceCurrency, { maximumFractionDigits: 1 }, empty)
  if (numeric >= 100) return formatMoney(numeric, sourceCurrency, { maximumFractionDigits: 2 }, empty)
  if (numeric >= 1) return formatMoney(numeric, sourceCurrency, { maximumFractionDigits: 3 }, empty)
  return formatMoney(numeric, sourceCurrency, { maximumSignificantDigits: 4 }, empty)
}

export const formatCompactCurrency = (value: unknown, sourceCurrency = 'USDT', empty = '--') => {
  const numeric = asNumber(value)
  return numeric === null ? empty : money().formatCompactMoney(numeric, sourceCurrency)
}

export const formatNumber = (value: unknown, empty = '-') => {
  const numeric = asNumber(value)
  return numeric === null ? empty : numeric.toLocaleString()
}

export const formatSignedNumber = (value: unknown, digits = 2, empty = '--') => {
  const numeric = asNumber(value)
  if (numeric === null) return empty
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(digits)}`
}

export const formatSignedMetric = (value: unknown, digits = 2, suffix = '%', withSign = true, empty = '--') => {
  const numeric = asNumber(value)
  if (numeric === null) return empty
  const sign = withSign && numeric > 0 ? '+' : ''
  return `${sign}${numeric.toFixed(digits)}${suffix}`
}

export const formatPercentile = (value: unknown, empty = '--') => {
  const numeric = asNumber(value)
  return numeric === null ? empty : `P${Math.round(numeric)}`
}

export const formatLocalizedNumber = (value: unknown, maximumFractionDigits = 3, empty = '--') => {
  const numeric = asNumber(value)
  if (numeric === null) return empty
  return numeric.toLocaleString(undefined, { maximumFractionDigits, minimumFractionDigits: 0 })
}

export const formatCompactNumber = (value: unknown, empty = '--') => {
  const numeric = asNumber(value)
  if (numeric === null) return empty
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(numeric)
}

export const formatDate = (value: string | number | Date | null | undefined, empty = '-') => {
  if (!value) return empty
  const formatted = dateTime().formatDate(value)
  return formatted === '--' ? empty : formatted
}

export const formatDateTime = (value: string | number | Date | null | undefined, empty = '-') => {
  if (!value) return empty
  const formatted = dateTime().formatDateTime(value, { hour12: false })
  return formatted === '--' ? empty : formatted
}

export const formatDuration = (minutes: unknown) => {
  const numeric = asNumber(minutes)
  if (numeric === null) return '-'
  const hours = Math.floor(numeric / 60)
  const rest = Math.round(numeric % 60)
  return hours > 0 ? `${hours}h ${rest}m` : `${rest}m`
}

export const formatRange = (value: { start?: string; end?: string } | null | undefined) => {
  if (!value?.start || !value?.end) return '-'
  const formatted = dateTime().formatDateRange(value)
  return formatted === '--' ? '-' : formatted
}

