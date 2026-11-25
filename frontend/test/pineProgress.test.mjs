import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import test from 'node:test'
import { runPineComputation } from '../src/modules/chartWorkspace/pineComputation.mjs'

test('the real Pine producer reports counted candles separately from saving the report', async () => {
  const start = Date.UTC(2026, 0, 1), count = 4001, interval = 60000
  const request = { symbol: 'binance:spot:BTCUSDT', timeframe: '1m', start, end: start + count * interval, inputs: {}, props: {} }
  const bars = Array.from({ length: count }, (_, index) => ({ time: start + index * interval, closeTime: start + (index + 1) * interval,
    open: 100, high: 101, low: 99, close: 100, volume: 1, closed: true }))
  const progress = []
  const result = await runPineComputation({ runId: 'progress-attempt', source: '//@version=6\nstrategy("Progress")\nplot(close)', request, bars,
    symbol: { id: request.symbol, symbol: 'BTCUSDT', exchange: 'binance', market: 'spot', currency: 'USDT', timezone: 'Etc/UTC', session: '24x7', metadata: {} }, frozen: true },
  { hash: async value => createHash('sha256').update(JSON.stringify(value)).digest('hex'), write: (name, value) => { if (name === 'progress.json') progress.push(value) } })
  const measured = progress.filter(value => value.progress?.mode === 'measured')
  assert.ok(measured.some(value => value.progress.completed > 0 && value.progress.completed < count))
  assert.ok(measured.every(value => value.runId === 'progress-attempt' && value.progress.total === count && value.progress.unit === 'candles'))
  assert.deepEqual(progress.at(-1), { runId: 'progress-attempt', progress: { phase: 'saving', mode: 'indeterminate', completed: null, total: null, unit: null } })
  assert.equal(result.equity.length, count)
})
