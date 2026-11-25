import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

function load(file, modules = {}) {
  const exports = {}
  const compiled = ts.transpileModule(readFileSync(new URL(file, import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  new Function('require', 'exports', compiled)(name => { if (!(name in modules)) throw new Error('Unexpected import: ' + name); return modules[name] }, exports)
  return exports
}
const dates = load('../src/utils/utcDate.ts')
const numbers = load('../src/utils/number.ts')
const indicators = load('../src/modules/market/indicatorSeries.ts', { '@/utils/number': numbers, '@/utils/utcDate': dates })

test('indicator changes use calendar days rather than the number of samples', () => {
  const start = Date.UTC(2026, 0, 1)
  const history = Array.from({ length: 181 }, (_, i) => ({ date: new Date(start + i * 4 * 3600000).toISOString(), value: 100 + i / 6 }))
  assert.ok(Math.abs(indicators.indicatorChangePercent({ history }, 30) - 30) < 1e-9)
  assert.equal(indicators.indicatorChangePercent({ history: history.slice(-40) }, 30), null)
})
test('sparse indicator history uses the observation preceding the comparison date', () => {
  const history = [{ date: '2026-01-01T00:00:00Z', value: 100 }, { date: '2026-01-03T00:00:00Z', value: 200 }, { date: '2026-02-01T00:00:00Z', value: 300 }]
  assert.equal(indicators.indicatorChangePercent({ history }, 30), 200)
  assert.equal(indicators.indicatorChangePercent({ history: history.slice().reverse() }, 30), 200)
})
test('legacy UTC and explicit offsets describe the same indicator instant', () => {
  const expected = Date.UTC(2026, 0, 1, 12)
  for (const value of ['2026-01-01T12:00:00', '2026-01-01T12:00:00Z', '2026-01-01T20:00:00+08:00']) assert.equal(indicators.parseIndicatorTimestamp(value), expected)
  assert.equal(indicators.parseIndicatorTimestamp('invalid'), null)
})
