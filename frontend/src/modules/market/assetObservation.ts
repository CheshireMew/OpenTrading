import type { OhlcvPointResponse } from './contracts'

export const DAY_MS = 86_400_000
export type PeakBasis = 'high' | 'close'
export type ObservationRange = '3m' | '1y' | '3y' | 'all'

export function normalizeObservationBars(input: OhlcvPointResponse[], now = Date.now()) {
  const rows = new Map<number, OhlcvPointResponse>()
  for (const row of input) {
    if (!Number.isFinite(row.timestamp) || row.timestamp <= 0 || row.timestamp > now) continue
    if (![row.open, row.high, row.low, row.close].every(value => Number.isFinite(value) && value > 0)) continue
    if (row.high < Math.max(row.open, row.close, row.low) || row.low > Math.min(row.open, row.close)) continue
    rows.set(row.timestamp, { ...row, volume: Number.isFinite(row.volume) && row.volume >= 0 ? row.volume : 0 })
  }
  return [...rows.values()].sort((a, b) => a.timestamp - b.timestamp)
}

export const percentageChange = (value: number, base: number) => (value / base - 1) * 100

// Returns are calendar-based; the reference is the last session on/before
// the requested date. A new listing never becomes a fictional one-year return.
export function returnSince(bars: OhlcvPointResponse[], cutoff: number): number | null {
  const last = bars[bars.length - 1]
  const base = [...bars].reverse().find(row => row.timestamp <= cutoff)
  if (!last || !base || base === last) return null
  return percentageChange(last.close, base.close)
}

export function analyzeObservation(bars: OhlcvPointResponse[], basis: PeakBasis = 'high') {
  const latest = bars[bars.length - 1]
  if (!latest) return null
  let peak = bars[0]
  let runningPeak = 0
  let closePeak = 0
  let maxDrawdown = 0
  const drawdowns = bars.map(row => {
    if (row[basis] >= peak[basis]) peak = row
    runningPeak = Math.max(runningPeak, row[basis])
    closePeak = Math.max(closePeak, row.close)
    maxDrawdown = Math.min(maxDrawdown, percentageChange(row.close, closePeak))
    return { timestamp: row.timestamp, value: Math.min(0, percentageChange(row.close, runningPeak)) }
  })
  const yearCutoff = latest.timestamp - 364 * DAY_MS
  const yearBars = bars.filter(row => row.timestamp >= yearCutoff)
  const yearHigh = Math.max(...yearBars.map(row => row[basis]))
  const lowBasis = basis === 'high' ? 'low' : 'close'
  const yearLow = Math.min(...yearBars.map(row => row[lowBasis]))
  // Daily OHLC does not tell us whether the peak day's low came after its high.
  let lowest: OhlcvPointResponse | null = null
  for (let index = bars.length - 1; index >= 0 && bars[index].timestamp > peak.timestamp; index -= 1) {
    const row = bars[index]
    if (!lowest || row[lowBasis] < lowest[lowBasis]) lowest = row
  }
  const drawdownLow = lowest ? { timestamp: lowest.timestamp, price: lowest[lowBasis] } : null
  const previous = bars[bars.length - 2]
  const yearStart = Date.UTC(new Date(latest.timestamp).getUTCFullYear(), 0, 1)
  return {
    latest, peak, peakPrice: peak[basis],
    drawdownLow,
    rebound: drawdownLow ? percentageChange(latest.close, drawdownLow.price) : null,
    drawdown: Math.min(0, percentageChange(latest.close, peak[basis])),
    recovery: Math.max(0, percentageChange(peak[basis], latest.close)),
    daysSincePeak: Math.floor((latest.timestamp - peak.timestamp) / DAY_MS),
    maxDrawdown, drawdowns, yearHigh, yearLow,
    yearComplete: bars[0].timestamp <= yearCutoff,
    yearPosition: yearHigh === yearLow ? 100 : Math.max(0, Math.min(100, (latest.close - yearLow) / (yearHigh - yearLow) * 100)),
    returns: {
      day: previous ? percentageChange(latest.close, previous.close) : null,
      week: returnSince(bars, latest.timestamp - 7 * DAY_MS),
      month: returnSince(bars, latest.timestamp - 30 * DAY_MS),
      quarter: returnSince(bars, latest.timestamp - 90 * DAY_MS),
      ytd: returnSince(bars, yearStart - 1),
      year: returnSince(bars, latest.timestamp - 365 * DAY_MS),
    },
  }
}

export function observationRangeStart(latest: number, range: ObservationRange) {
  return range === 'all' ? 0 : latest - ({ '3m': 90, '1y': 365, '3y': 1095 }[range] * DAY_MS)
}
