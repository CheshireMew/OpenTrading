import assert from 'node:assert/strict'
import test from 'node:test'
import { analyzeObservation, normalizeObservationBars, returnSince, observationRangeStart, DAY_MS } from '../src/modules/market/assetObservation.ts'

const bar = (date, close, high = close, low = close) => ({ timestamp: Date.parse(`${date}T00:00:00Z`), open: close, high, low, close, volume: 10 })
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`)

test('a 50% drawdown requires a 100% gain, with intraday and closing peaks kept distinct', () => {
  const rows = [bar('2024-01-01', 80, 100), bar('2024-01-02', 50)]
  const high = analyzeObservation(rows)
  near(high.drawdown, -50)
  near(high.recovery, 100)
  near(high.maxDrawdown, -37.5)
  assert.equal(high.daysSincePeak, 1)
  const close = analyzeObservation(rows, 'close')
  near(close.drawdown, -37.5)
  near(close.recovery, 60)
})

test('drawdown uses each day’s running peak rather than a future record high', () => {
  const rows = [bar('2024-01-01', 100), bar('2024-01-02', 80), bar('2024-01-03', 120), bar('2024-01-04', 90)]
  const stats = analyzeObservation(rows)
  stats.drawdowns.forEach((row, i) => near(row.value, [0, -20, 0, -25][i]))
  near(stats.maxDrawdown, -25)
  assert.equal(stats.peak.timestamp, rows[2].timestamp)
  const cutoff = observationRangeStart(rows[3].timestamp, '3m')
  assert.equal(cutoff, rows[3].timestamp - 90 * DAY_MS)
})

test('calendar returns use the previous trading session and require sufficient history', () => {
  const rows = [bar('2023-12-29', 100), bar('2024-01-05', 120), bar('2024-01-08', 150)]
  const stats = analyzeObservation(rows)
  near(stats.returns.day, 25)
  near(stats.returns.week, 50)
  near(stats.returns.ytd, 50)
  assert.equal(stats.returns.year, null)
  assert.equal(stats.returns.month, null)
  near(returnSince(rows, Date.parse('2024-01-07T00:00:00Z')), 25)
  assert.equal(stats.yearComplete, false)
})

test('52-week extremes exclude older peaks while overall drawdown preserves them', () => {
  const stats = analyzeObservation([bar('2023-01-01', 200), bar('2024-01-10', 100, 110, 90), bar('2024-12-31', 120, 125, 115)])
  assert.equal(stats.yearHigh, 125)
  assert.equal(stats.yearLow, 90)
  assert.equal(stats.peakPrice, 200)
  assert.equal(stats.yearComplete, true)
  near(stats.drawdown, -40)
})

test('invalid, future and duplicate bars cannot introduce false highs', () => {
  const valid = bar('2024-01-02', 10)
  const refreshed = { ...valid, close: 12, high: 12 }
  const rows = normalizeObservationBars([
    valid, bar('2024-01-01', 8), refreshed,
    bar('2024-01-03', NaN), bar('2024-01-04', 0),
    bar('2024-01-05', 20, 19), bar('2099-01-01', 1000),
  ], Date.parse('2024-01-10T00:00:00Z'))
  assert.deepEqual(rows.map(row => row.close), [8, 12])
  assert.equal(analyzeObservation(rows).peakPrice, 12)
})

test('empty and flat histories have no invented returns or non-finite range positions', () => {
  assert.equal(analyzeObservation([]), null)
  const stats = analyzeObservation([bar('2024-01-01', 10)])
  assert.equal(stats.returns.day, null)
  assert.equal(stats.drawdown, 0)
  assert.equal(stats.recovery, 0)
  assert.equal(stats.yearPosition, 100)
  assert.equal(stats.drawdownLow, null)
  assert.equal(stats.rebound, null)
})

test('rebound uses the lowest price after the peak on the selected price basis', () => {
  const rows = [
    bar('2025-01-01', 25),
    bar('2025-01-02', 104, 130, 40),
    bar('2025-01-03', 80, 100, 55),
    bar('2025-01-04', 112, 115, 92),
    bar('2025-01-05', 90, 95, 85),
    bar('2025-01-06', 103, 108, 97),
  ]

  const intraday = analyzeObservation(rows)
  assert.equal(intraday.peak.timestamp, rows[1].timestamp)
  assert.deepEqual(intraday.drawdownLow, { timestamp: rows[2].timestamp, price: 55 })
  near(intraday.rebound, (103 / 55 - 1) * 100)

  const closing = analyzeObservation(rows, 'close')
  assert.equal(closing.peak.timestamp, rows[3].timestamp)
  assert.deepEqual(closing.drawdownLow, { timestamp: rows[4].timestamp, price: 90 })
  near(closing.rebound, (103 / 90 - 1) * 100)
})

test('the latest daily bar can set the drawdown low before any later bars exist', () => {
  const rows = [
    bar('2025-10-06', 124658.54, 126199.63, 123084),
    bar('2026-10-15', 80400, 83000, 79800),
    bar('2026-11-20', 58951.51, 62639.5, 57778.35),
    bar('2026-11-21', 60453.78, 60996, 55130),
  ]
  const stats = analyzeObservation(rows)
  assert.deepEqual(stats.drawdownLow, { timestamp: rows[3].timestamp, price: 55130 })
  assert.equal(stats.rebound.toFixed(2), '9.66')
  assert.equal(analyzeObservation(rows, 'close').rebound.toFixed(2), '2.55')

  const newPeak = analyzeObservation([...rows, bar('2026-11-22', 125000, 127000, 55000)])
  assert.equal(newPeak.drawdownLow, null)
  assert.equal(newPeak.rebound, null)
})
