import { useUserPreferences } from './useUserPreferences'
import i18n from '@/i18n'
import { parseUtcDate } from '@/utils/utcDate'

type DateInput = string | number | Date | null | undefined

const isDateOnly = (value: DateInput) => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)

const parseDateInput = (value: DateInput) => {
  return parseUtcDate(value)
}

export function useDateTime() {
  const { timezone } = useUserPreferences()

  const formatDateTime = (
    value: DateInput,
    options: Intl.DateTimeFormatOptions = {},
  ) => {
    const date = parseDateInput(value)
    if (!date) return '--'
    return date.toLocaleString(i18n.global.locale.value, {
      timeZone: timezone.value,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      ...options,
    })
  }

  const formatDate = (
    value: DateInput,
    options: Intl.DateTimeFormatOptions = {},
  ) => {
    if (isDateOnly(value)) return String(value)
    const date = parseDateInput(value)
    if (!date) return '--'
    return date.toLocaleDateString(i18n.global.locale.value, {
      timeZone: timezone.value,
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      ...options,
    })
  }

  const formatDateRange = (
    value: { start?: string; end?: string } | null | undefined,
  ) => {
    if (!value?.start || !value?.end) return '--'
    return `${formatDate(value.start)} ~ ${formatDate(value.end)}`
  }

  return {
    timezone,
    formatDate,
    formatDateTime,
    formatDateRange,
  }
}
