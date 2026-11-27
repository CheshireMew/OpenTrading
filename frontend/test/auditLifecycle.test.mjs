import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import ts from 'typescript'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as vue from 'vue'

const require = createRequire(import.meta.url)
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
const settle = async () => { for (let i = 0; i < 8; i++) await vue.nextTick() }
const { render } = vue.createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  insert() {}, remove() {}, patchProp() {}, setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null })

// Compile the real component/composable. Only external API, charts and storage are replaced.
function loadSource(url, modules, sfc = false) {
  const source = fs.readFileSync(url, 'utf8')
  const content = sfc ? compileScript(parse(source).descriptor, { id: 'audit-lifecycle' }).content : source
  const code = ts.transpileModule(content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(id => id in modules ? modules[id] : id === 'vue' ? vue : require(id), exports)
  return exports
}

function mountTester(api, overrides = {}) {
  const component = loadSource(new URL('../src/components/chartWorkspace/StrategyTester.vue', import.meta.url), {
    '@/theme/palette.mjs': { DARK_PALETTE: {} },
    '@/api/request': { apiErrorMessage: (cause, fallback) => cause?.message || fallback },
    '@/modules/chartWorkspace/api': { chartApi: api },
    '@/modules/chartWorkspace/pineEngine': { readPineMetadata: () => ({ result: Promise.resolve({ kind: 'strategy', props: {}, inputs: [] }), cancel() {} }) },
    '@/modules/chartWorkspace/locale': { cw: key => key, formatNumber: String, formatDate: String },
    '@/modules/chartWorkspace/metrics.mjs': { payoffRatio: () => null },
    '@/modules/chartWorkspace/pineCompatibility.mjs': { checkPine() {} },
    'lightweight-charts': {},
  }, true).default
  let state
  const host = {}
  render(vue.h({ setup() {
    state = component.setup({ timeframe: '1m', dark: false, ...overrides }, { expose() {}, emit() {} })
    return () => null
  } }), host)
  return { state, unmount: () => render(null, host) }
}

test('tester cannot recreate its polling timer after unmount with getRun pending', async t => {
  const waiting = deferred()
  let timers = 0
  t.mock.method(globalThis, 'setTimeout', () => { timers++; return 1 })
  const mounted = mountTester({ runs: async () => [{ id: 'one' }], getRun: () => waiting.promise })
  await settle()
  mounted.unmount()
  waiting.resolve({ id: 'one', status: 'running' })
  await settle()
  assert.equal(timers, 0)
  assert.equal(mounted.state.selected.value, undefined)
})

test('tester rejects an older selection response after the new selection has completed', async () => {
  const first = deferred(), second = deferred()
  const mounted = mountTester({ runs: async () => [], getRun: id => id === 'a' ? first.promise : second.promise })
  await settle()
  mounted.state.selectedId.value = 'a'
  const a = mounted.state.loadSelected()
  mounted.state.selectedId.value = 'b'
  const b = mounted.state.loadSelected()
  second.resolve({ id: 'b', status: 'failed' }); await b
  first.resolve({ id: 'a', status: 'running' }); await a
  assert.equal(mounted.state.selected.value.id, 'b')
  mounted.unmount()
})

test('a late run submission cannot replace a selection made while submission was pending', async () => {
  const waiting = deferred()
  const mounted = mountTester({ runs: async () => [], run: () => waiting.promise,
    getRun: async id => ({ id, status: 'failed' }) }, { script: { id: 'script', version: 1, data: { source: 'strategy("S")' } }, symbol: { id: 'BTC' } })
  await settle()
  const submission = mounted.state.run()
  mounted.state.selectedId.value = 'chosen'
  await mounted.state.loadSelected()
  waiting.resolve({ id: 'late-created', status: 'queued' })
  await submission
  assert.equal(mounted.state.selectedId.value, 'chosen')
  assert.equal(mounted.state.selected.value.id, 'chosen')
  mounted.unmount()
})

test('tester retries a transient status failure and recovers the completed report', async t => {
  const timers = []
  t.mock.method(globalThis, 'setTimeout', (run, delay) => { const timer = { run, delay }; timers.push(timer); return timer })
  t.mock.method(globalThis, 'clearTimeout', () => {})
  let calls = 0
  const mounted = mountTester({ runs: async () => [{ id: 'one' }],
    getRun: async () => { calls++; if (calls === 2) throw Object.assign(new Error('offline'), { status: 503 }); return { id: 'one', status: calls < 3 ? 'running' : 'completed' } },
    records: async () => ({ items: [], total: 0 }),
  })
  await settle()
  assert.equal(timers[0].delay, 1500)
  await timers.shift().run()
  assert.equal(mounted.state.requestError.value, 'offline')
  assert.equal(timers[0].delay, 3000)
  await timers.shift().run()
  assert.equal(calls, 3)
  assert.equal(mounted.state.selected.value.status, 'completed')
  assert.equal(mounted.state.requestError.value, '')
  assert.equal(timers.length, 0)
  mounted.unmount()
})

test('tester exposes manual recovery for an initial missing record without retrying a permanent failure', async t => {
  let timers = 0, calls = 0
  t.mock.method(globalThis, 'setTimeout', () => { timers++; return 1 })
  const mounted = mountTester({ runs: async () => [{ id: 'one' }],
    getRun: async () => { if (++calls === 1) throw Object.assign(new Error('missing'), { status: 404 }); return { id: 'one', status: 'failed' } },
  })
  await settle()
  assert.equal(mounted.state.requestError.value, 'missing')
  assert.equal(timers, 0)
  await mounted.state.retrySelected()
  assert.equal(mounted.state.selected.value.status, 'failed')
  assert.equal(mounted.state.requestError.value, '')
  mounted.unmount()
})

test('chart HTTP requests bound stalled responses and preserve caller cancellation', async t => {
  const { request } = loadSource(new URL('../src/modules/chartWorkspace/api.ts', import.meta.url), {
    '@/api/request': { ApiRequestError: Error }, '@/app/publicSite': { PUBLIC_SITE: false },
    './browserDocuments': { createBrowserDocuments: () => ({}) }, './browserPineRuns': {},
    './barRequests': loadSource(new URL('../src/modules/chartWorkspace/barRequests.ts', import.meta.url)),
  })
  let signal
  t.mock.method(globalThis, 'fetch', (_url, options) => new Promise((_resolve, reject) => {
    signal = options.signal
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  }))
  await assert.rejects(request('/stalled', {}, 20), /timeout of 20ms exceeded/)
  assert.equal(signal.aborted, true)
  const controller = new AbortController(), reason = new Error('caller stopped')
  const pending = request('/canceled', { signal: controller.signal })
  controller.abort(reason)
  await assert.rejects(pending, error => error === reason)
  assert.equal(signal.aborted, true)
})

test('chart HTTP errors retain status for localized recovery and preserve useful backend details', async t => {
  class RequestError extends Error {
    constructor(message, options) { super(message); Object.assign(this, options) }
  }
  const { request } = loadSource(new URL('../src/modules/chartWorkspace/api.ts', import.meta.url), {
    '@/api/request': { ApiRequestError: RequestError }, '@/app/publicSite': { PUBLIC_SITE: false },
    './browserDocuments': { createBrowserDocuments: () => ({}) }, './browserPineRuns': {},
    './barRequests': loadSource(new URL('../src/modules/chartWorkspace/barRequests.ts', import.meta.url)),
  })
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>gateway timeout</html>', { status: 504 }))
  await assert.rejects(request('/bars'), error => error.status === 504)
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: '历史行情暂时加载失败，请重试' }), { status: 502 }))
  await assert.rejects(request('/bars'), error => error.status === 502 && error.message === '历史行情暂时加载失败，请重试')
})

test('market resource drops pending data and cannot restart timers after its scope is disposed', async t => {
  const waiting = deferred()
  let timers = 0, writes = 0
  t.mock.method(globalThis, 'setTimeout', () => { timers++; return 1 })
  t.mock.method(globalThis, 'setInterval', () => { timers++; return 2 })
  const { useBinanceMarketPageResource } = loadSource(new URL('../src/modules/market/useBinanceMarketPageResource.ts', import.meta.url), {
    './api': { binanceMarketApi: { getBinanceMarketPage: () => waiting.promise } },
    './binanceMarketWarmSnapshot': { binanceMarketWarmSnapshot: { read() {}, write() { writes++ } } },
    './binanceMarketShared': { EMPTY_RESPONSE: { items: [] } },
  })
  const scope = vue.effectScope()
  const resource = scope.run(() => useBinanceMarketPageResource(vue.ref(3), vue.ref(true), vue.ref('en'), key => key))
  const request = resource.fetchData()
  scope.stop()
  waiting.resolve({ monitor: { items: [{ symbol: 'late' }] }, refresh_status: { monitor_ready: false, refreshing: true } })
  await request
  resource.startAutoRefresh()
  assert.equal(timers, 0)
  assert.equal(writes, 0)
  assert.deepEqual(resource.monitor.value.items, [])
})
