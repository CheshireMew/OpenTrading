import type { MarketIndicatorResponse } from './contracts'
import { percentChange } from '@/utils/number'
import { parseUtcDate } from '@/utils/utcDate'


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
  if (!Number.isFinite(lookback) || lookback <= 0) return null
  const points = (indicator?.history ?? []).map(point => ({ time: parseUtcDate(point.date)?.getTime(), value: point.value }))
    .filter((point): point is { time: number; value: number } => point.time !== undefined && Number.isFinite(point.value))
    .sort((a, b) => a.time - b.time)
  const latest = points[points.length - 1]
  if (!latest) return null
  const cutoff = latest.time - lookback * 86_400_000
  let previous: { time: number; value: number } | undefined
  for (const point of points) { if (point.time > cutoff) break; previous = point }
  if (!previous || previous.value === 0) return null
  return percentChange(latest.value, previous.value, true)
}

export const parseIndicatorTimestamp = (value: string | null | undefined): number | null => {
  if (!value) return null
  return parseUtcDate(value)?.getTime() ?? null
}
