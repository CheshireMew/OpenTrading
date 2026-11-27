import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import * as Vue from 'vue'

// Run the production composable with real Vue lifecycle/watchers and deferred sources.
const source = fs.readFileSync(new URL('../src/modules/market/useKlineSeries.ts', import.meta.url), 'utf8')
const compiled = ts.transpile(source, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 })
const module = { exports: {} }
new Function('require', 'module', 'exports', compiled)(name => {
  if (name === 'vue') return Vue
  if (name === './api') return {}
  if (name === './klineStore') return { useKlineStore: () => ({}) }
  if (name === './symbolCatalog') return { isIndexSymbol: () => false }
  if (name === '@/utils/localDate') return { toLocalIsoDate: () => '' }
  throw Error(`Unexpected import: ${name}`)
}, module, module.exports)
const { useKlineSeries } = module.exports
const { render } = Vue.createRenderer({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  insert() {}, remove() {}, patchProp() {}, setText() {}, setElementText() {},
  parentNode: () => null, nextSibling: () => null,
})
const settle = async () => { for (let i = 0; i < 5; i += 1) await Vue.nextTick() }
const bar = (close, timestamp = 1000) => ({ timestamp, open: close, high: close + 1, low: close - 1, close, volume: 100 })

function mount() {
  const calls = []
  const timers = new Map()
  const previousWindow = globalThis.window
  let timer = 0
  globalThis.window = { setInterval(fn) { timers.set(++timer, fn); return timer }, clearInterval(id) { timers.delete(id) } }
  const key = Vue.ref('spot:TOKEN:15m'), enabled = Vue.ref(true)
  const request = kind => new Promise((resolve, reject) => calls.push({ kind, key: key.value, resolve, reject }))
  let series
  const host = {}
  render(Vue.h({ setup() {
    series = useKlineSeries(Vue.ref('TOKEN'), Vue.ref('15m'), {
      enabled, source: { key, latest: () => request('latest'), tail: () => request('tail'), before: () => request('before') },
    })
    return () => null
  } }), host)
  return { series, key, enabled, calls, timers, close() { render(null, host); globalThis.window = previousWindow } }
}

test('same ticker on spot and perpetual cannot exchange chart data or loading states', async () => {
  const view = mount()
  try {
    const oldSpot = view.calls[0]
    view.key.value = 'usdm:TOKEN:15m'; await settle()
    const perpetual = view.calls[1]
    perpetual.resolve([bar(20)]); await settle()
    assert.equal(view.series.chartData.value[0].close, 20)
    assert.equal(view.series.loading.value, false)
    oldSpot.resolve([bar(10)]); await settle()
    assert.equal(view.series.chartData.value[0].close, 20)
    assert.equal(view.series.loadError.value, false)
  } finally { view.close() }
})

test('returning to a ticker ignores its older pending request and a closed panel ignores failures', async () => {
  const view = mount()
  try {
    view.key.value = 'usdm:TOKEN:15m'; await settle()
    view.key.value = 'spot:TOKEN:15m'; await settle()
    view.calls[2].resolve([bar(30)]); await settle()
    view.calls[0].resolve([bar(10)]); view.calls[1].reject(Error('obsolete request')); await settle()
    assert.equal(view.series.chartData.value[0].close, 30)
    assert.equal(view.series.loadError.value, false)
    const retry = view.series.retry()
    view.enabled.value = false; await settle()
    view.calls[3].reject(Error('panel closed')); await retry; await settle()
    assert.deepEqual(view.series.chartData.value, [])
    assert.equal(view.series.loading.value, false)
    assert.equal(view.series.loadError.value, false)
    assert.equal(view.timers.size, 0)
  } finally { view.close() }
})

test('tail refresh and older history cannot append rows after the selected market changes', async () => {
  const view = mount()
  try {
    view.calls[0].resolve([bar(10, 2000)]); await settle()
    const timer = [...view.timers.values()][0]
    timer()
    const tail = view.calls[1]
    const older = view.series.loadMore()
    const before = view.calls[2]
    view.key.value = 'usdm:TOKEN:15m'; await settle()
    view.calls[3].resolve([bar(20, 3000)]); await settle()
    tail.resolve([bar(99, 4000)]); before.resolve([bar(99, 1000)])
    await older; await settle()
    assert.deepEqual(view.series.chartData.value.map(row => row.close), [20])
    assert.equal(view.series.loadingMore.value, false)
  } finally { view.close() }
})

test('older history continues past 5000 candles and a refresh retains the expanded history', async () => {
  const view = mount()
  try {
    view.calls[0].resolve(Array.from({ length: 1000 }, (_, i) => bar(10, 5000 + i))); await settle()
    for (let page = 0; page < 9; page++) {
      const older = view.series.loadMore()
      view.calls.at(-1).resolve(Array.from({ length: 500 }, (_, i) => bar(10, 4500 - page * 500 + i)))
      await older; await settle()
    }
    assert.equal(view.series.chartData.value.length, 5500)
    assert.equal(view.series.chartData.value[0].time, 0.5)
    const timer = [...view.timers.values()][0]; timer()
    view.calls.at(-1).resolve([bar(20, 5999), bar(30, 6000)]); await settle()
    assert.equal(view.series.chartData.value.length, 5501)
    assert.equal(view.series.chartData.value[0].time, 0.5)
    assert.equal(view.series.chartData.value.at(-1).close, 30)
  } finally { view.close() }
})

test('a tail beyond the last loaded candle fills the missing interval before publishing it', async () => {
  const view = mount()
  try {
    view.calls[0].resolve([bar(10, 1000)]); await settle()
    const timer = [...view.timers.values()][0]; timer()
    view.calls[1].resolve([bar(40, 4000), bar(50, 5000)]); await settle()
    assert.equal(view.calls[2]?.kind, 'before')
    assert.deepEqual(view.series.chartData.value.map(row => row.time), [1])
    timer(); await settle()
    assert.equal(view.calls.length, 3, 'tail repair must not launch overlapping refreshes')
    view.calls[2].resolve([bar(11, 1000), bar(20, 2000), bar(30, 3000)]); await settle()
    assert.deepEqual(view.series.chartData.value.map(row => row.time), [1, 2, 3, 4, 5])
    assert.equal(view.series.chartData.value[0].close, 11, 'the old forming candle must be corrected too')
  } finally { view.close() }
})

test('a history page containing no older candles ends pagination instead of requesting the same page again', async () => {
  const view = mount()
  try {
    view.calls[0].resolve([bar(10, 1000)]); await settle()
    const older = view.series.loadMore()
    view.calls[1].resolve([bar(10, 1000)]); await older; await settle()
    assert.equal(view.series.noMoreHistory.value, true)
    await view.series.loadMore()
    assert.equal(view.calls.length, 2)
  } finally { view.close() }
})

test('retrying the latest snapshot repairs its gap before replacing the visible tail', async () => {
  const view = mount()
  try {
    view.calls[0].resolve([bar(10, 1000)]); await settle()
    const retry = view.series.retry()
    view.calls[1].resolve([bar(50, 5000)]); await settle()
    assert.equal(view.calls[2]?.kind, 'before')
    assert.deepEqual(view.series.chartData.value.map(row => row.time), [1])
    view.calls[2].resolve([bar(11, 1000), bar(20, 2000), bar(30, 3000), bar(40, 4000)])
    await retry; await settle()
    assert.deepEqual(view.series.chartData.value.map(row => row.time), [1, 2, 3, 4, 5])
  } finally { view.close() }
})

test('switching market during a multi-page gap repair discards every old-market repair page', async () => {
  const view = mount()
  try {
    view.calls[0].resolve([bar(10, 1000)]); await settle()
    const timer = [...view.timers.values()][0]; timer()
    view.calls[1].resolve([bar(60, 6000)]); await settle()
    view.calls[2].resolve([bar(40, 4000), bar(50, 5000)]); await settle()
    assert.equal(view.calls[3]?.kind, 'before')
    assert.deepEqual(view.series.chartData.value.map(row => row.time), [1])
    view.key.value = 'usdm:TOKEN:15m'; await settle()
    view.calls[4].resolve([bar(80, 8000)]); await settle()
    view.calls[3].resolve([bar(11, 1000), bar(20, 2000), bar(30, 3000)]); await settle()
    assert.deepEqual(view.series.chartData.value.map(row => row.close), [80])
  } finally { view.close() }
})
