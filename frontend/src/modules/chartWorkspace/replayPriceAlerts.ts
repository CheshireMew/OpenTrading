import type { ChartBar } from './api'
import type { ResearchAlertResponse } from '@/modules/research/contracts'

/** Use only the newly revealed source candle, never the accumulated chart wick. */
export function replayPriceAlertMatches(rule: ResearchAlertResponse, bar: ChartBar): boolean {
  const level = rule.threshold, previous = rule.lastValue, second = rule.secondaryThreshold
  // Directional crosses require a crossing demonstrated by the candle's
  // endpoints and extremes; OHLC cannot tell us the order of high and low.
  const above = (previous != null && previous < level && bar.open >= level) ||
    (bar.open < level && bar.high >= level) || (bar.low < level && bar.close >= level)
  const below = (previous != null && previous > level && bar.open <= level) ||
    (bar.open > level && bar.low <= level) || (bar.high > level && bar.close <= level)
  return {
    gt: bar.high > level, gte: bar.high >= level, lt: bar.low < level, lte: bar.low <= level,
    crosses: above || below, crosses_above: above, crosses_below: below,
    between: second != null && bar.high >= level && bar.low <= second,
    outside: second != null && (bar.low < level || bar.high > second),
  }[rule.operator]
}
