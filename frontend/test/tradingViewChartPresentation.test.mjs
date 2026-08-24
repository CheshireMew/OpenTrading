import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildMainPriceFormat,
  buildStrategyMarkers,
} from '../src/components/tradingViewChartPresentation.ts'

test('adaptive price formatting preserves precision for low-priced assets', () => {
  const format = buildMainPriceFormat([
    { time: 1, open: 0.000123, high: 0.000125, low: 0.00012, close: 0.000124 },
  ])

  assert.ok(format.precision >= 6)
  assert.equal(format.minMove, 10 ** -format.precision)
})

test('strategy markers are normalized and sorted chronologically', () => {
  const markers = buildStrategyMarkers([
    { time: 2000, kind: 'long_exit' },
    { time: 1000, kind: 'long_entry', label: 'Buy' },
  ])

  assert.deepEqual(markers.map((item) => Number(item.time)), [1, 2])
  assert.equal(markers[0].shape, 'arrowUp')
  assert.equal(markers[0].text, 'Buy')
})
