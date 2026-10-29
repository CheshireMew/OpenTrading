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
