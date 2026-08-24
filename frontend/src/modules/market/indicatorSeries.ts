import type { MarketIndicatorResponse } from './contracts'
import { percentChange } from '@/utils/number'


export const indicatorHistoryValues = (indicator: MarketIndicatorResponse | null | undefined): number[] => (
  indicator?.history
    ?.map((item) => item.value)
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  || []
)

export const indicatorLatestValue = (indicator: MarketIndicatorResponse | null | undefined): number | null => {
  if (!indicator) return null
  if (typeof indicator.current_value === 'number') return indicator.current_value
  const values = indicatorHistoryValues(indicator)
  return values.length ? values[values.length - 1] : null
}

export const indicatorChangePercent = (
  indicator: MarketIndicatorResponse | null | undefined,
  lookback: number,
): number | null => {
  const values = indicatorHistoryValues(indicator)
  if (values.length < 2) return null
  const current = values[values.length - 1]
  const previous = values[Math.max(0, values.length - lookback - 1)]
  if (previous === 0) return null
  return percentChange(current, previous, true)
}

export const parseIndicatorTimestamp = (value: string | null | undefined): number | null => {
  if (!value) return null
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) ? timestamp : null
}
