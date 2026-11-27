import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

function load(name, modules = {}) {
  const exports = {}
  const code = ts.transpileModule(fs.readFileSync(new URL('../src/modules/chartWorkspace/' + name + '.ts', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  new Function('require', 'exports', code)(id => modules[id], exports)
  return exports
}
const { createBarRequests } = load('barRequests')
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const info = { id: 'binance:spot:BTCUSDT', symbol: 'BTCUSDT', timeframes: ['1h'] }
const bar = i => ({ time: i * 3600000, closeTime: (i + 1) * 3600000, closed: true, open: 100, high: 102, low: 99, close: 101, volume: 1 })
const query = { symbol: info.id, timeframe: '1h', end: 1000 * 3600000, limit: 200 }
const response = { symbol: info, bars: [bar(1)] }

test('reconnecting the live feed repairs missing candles before releasing buffered chart updates', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  t.mock.method(Date, 'now', () => 4 * 3600000)
  const originalSocket = globalThis.WebSocket, originalLocation = globalThis.location
  const sockets = [], plots = [], quotes = [], calls = [], pending = deferred()
  class Socket {
    static OPEN = 1
    readyState = 0
    sent = []
    constructor() { sockets.push(this) }
    send(value) { this.sent.push(JSON.parse(value)) }
    close() { this.readyState = 3 }
  }
  globalThis.WebSocket = Socket
  globalThis.location = { protocol: 'http:', host: 'localhost' }
  t.after(() => { globalThis.WebSocket = originalSocket; globalThis.location = originalLocation })
  const { OpenTradingProvider } = load('provider', {
    './api': { chartApi: { bars: async query => {
      calls.push(query)
      return query.start === undefined ? { symbol: info, bars: [bar(1)] }
        : query.start >= bar(4).time ? { symbol: info, bars: [] } : pending.promise
    } } }, './locale': { cw: key => key }, './symbolIcons': {}, './symbolSearch': {},
  })
  const provider = new OpenTradingProvider(() => {}); provider.catalog = [info]
  t.after(() => provider.destroy())
  await provider.getBars(info.id, '60', { limit: 1 })
  provider.subscribe(info.id, '60', value => plots.push(value.time))
  provider.subscribeQuotes(info.id, '60', value => quotes.push(value.price))
  const open = socket => { socket.readyState = 1; socket.onopen() }
  const emit = (socket, index) => socket.onmessage({ data: JSON.stringify({ type: 'bar', symbol: info.id,
    timeframe: '1h', generation: socket.sent.at(-1).generation, sequence: index,
    bar: { ...bar(index), close: 100 + index }, live: true, observed_at: Date.now() }) })
  open(sockets[0]); emit(sockets[0], 1)
  sockets[0].readyState = 3; sockets[0].onclose()
  t.mock.timers.tick(2000); open(sockets[1])
  for (let i = 0; i < 10; i++) await Promise.resolve()
  emit(sockets[1], 4)
  assert.deepEqual(plots, [bar(1).time], 'the chart must wait for its missing historical candles')
  assert.deepEqual(quotes, [101, 104], 'live quotes remain independent from chart history recovery')
  assert.equal(calls.at(-1).start, bar(1).time)
  pending.resolve({ symbol: info, bars: [bar(1), bar(2), bar(3)] })
  for (let i = 0; i < 20; i++) await Promise.resolve()
  assert.deepEqual([...new Set(plots)], [1, 2, 3, 4].map(index => bar(index).time))
})

test('identical requests share one transport and cancelling one consumer does not cancel the other', async () => {
  const waiting = deferred(), signals = []
  const cache = createBarRequests((_query, signal) => { signals.push(signal); return waiting.promise })
  const firstAbort = new AbortController(), secondAbort = new AbortController()
  const first = cache.load(query, firstAbort.signal), second = cache.load({ ...query }, secondAbort.signal)
  const cancelled = assert.rejects(first, { name: 'AbortError' })
  firstAbort.abort(); await cancelled
  assert.equal(signals.length, 1)
  assert.equal(signals[0].aborted, false)
  waiting.resolve(response)
  assert.equal(await second, response)
  assert.equal(await cache.load(query), response)
  assert.equal(signals.length, 1)
})

test('superseded requests abort their transport, and an abandoned answer cannot replace the new request', async () => {
  const requests = []
  const cache = createBarRequests((_query, signal) => { const request = { ...deferred(), signal }; requests.push(request); return request.promise })
  const controller = new AbortController(), stale = cache.load(query, controller.signal)
  const cancelled = assert.rejects(stale, { name: 'AbortError' })
  controller.abort(); await cancelled
  assert.equal(requests[0].signal.aborted, true)
  const current = cache.load(query)
  requests[1].resolve(response); await current
  requests[0].resolve({ ...response, bars: [] }); await Promise.resolve()
  assert.equal(await cache.load(query), response)
  const preAborted = new AbortController(); preAborted.abort()
  await assert.rejects(cache.load(query, preAborted.signal), { name: 'AbortError' })
  assert.equal(requests.length, 2)
})

test('historical cutoffs, venues and periods are isolated and the response cache is bounded by total bars', async () => {
  const calls = []
  const cache = createBarRequests(async item => { calls.push(item); return { symbol: info, bars: [bar(1), bar(2)] } }, { maxBars: 4 })
  await cache.load(query)
  await cache.load({ ...query, end: query.end - 1 })
  assert.equal(calls.length, 2, 'a replay cutoff must never reuse a response with later candles')
  await cache.load({ ...query, symbol: 'binance:usdm:BTCUSDT' })
  assert.equal(cache.peek(query), undefined, 'the oldest result must be evicted when the bar budget is exceeded')
  await cache.load({ ...query, timeframe: '4h' })
  assert.equal(calls.length, 4)
})

test('expired live data remains available as a preview while the fresh request replaces it', async t => {
  let clock = Date.UTC(2026, 10, 26, 12), count = 0
  t.mock.method(Date, 'now', () => clock)
  const cache = createBarRequests(async () => { count++; return response })
  const live = { ...query, end: clock }
  await cache.load(live)
  clock += 100
  await cache.load({ ...live, end: clock })
  assert.equal(count, 1)
  clock += 60000
  assert.equal(cache.peek({ ...live, end: clock }), response)
  await cache.load({ ...live, end: clock })
  assert.equal(count, 2)
})

test('empty historical responses can recover on retry instead of being cached as a long-lived end of history', async t => {
  let clock = Date.UTC(2026, 10, 26, 12), count = 0
  t.mock.method(Date, 'now', () => clock)
  const cache = createBarRequests(async () => { count++; return count === 1 ? { ...response, bars: [] } : response }, { historical: true })
  assert.equal((await cache.load(query)).bars.length, 0)
  clock += 2001
  assert.equal((await cache.load(query)).bars.length, 1)
  assert.equal(count, 2)
})

test('a prefetched market paints immediately and fills older history without downloading the preview again', async () => {
  const calls = [], older = deferred()
  const cache = createBarRequests(async query => {
    calls.push(query)
    if (query.limit === 200) return { symbol: info, bars: Array.from({ length: 200 }, (_, i) => bar(800 + i)) }
    return older.promise
  })
  const { OpenTradingProvider } = load('provider', {
    './api': { chartApi: { bars: cache.load, cachedBars: cache.peek } }, './locale': { cw: key => key },
    './symbolIcons': {}, './symbolSearch': {},
  })
  const provider = new OpenTradingProvider(() => {}); provider.catalog = [info]
  try {
    await provider.preload(info.id, '60', new AbortController().signal)
    const batches = []
    const loading = provider.getBarsProgressive(info.id, '60', { limit: 1000 }, batch => batches.push(batch))
    for (let i = 0; i < 8; i++) await Promise.resolve()
    assert.equal(batches[0].length, 200)
    assert.equal(calls.length, 2)
    assert.equal(calls[1].end, 800 * 3600000 - 1)
    assert.equal(calls[1].limit, 800)
    older.resolve({ symbol: info, bars: Array.from({ length: 800 }, (_, i) => bar(i)) })
    const full = await loading
    assert.equal(full.length, 1000)
    assert.equal(new Set(full.map(bar => bar.time)).size, 1000)
  } finally { provider.destroy() }
})

test('a failed background history page rejects while retaining the already delivered preview', async () => {
  const batches = [], failure = new Error('upstream unavailable')
  const { OpenTradingProvider } = load('provider', {
    './api': { chartApi: { bars: async query => {
      if (query.limit !== 200) throw failure
      return { symbol: info, bars: Array.from({ length: 200 }, (_, i) => bar(800 + i)) }
    } } }, './locale': { cw: key => key }, './symbolIcons': {}, './symbolSearch': {},
  })
  const provider = new OpenTradingProvider(() => {}); provider.catalog = [info]
  try {
    await assert.rejects(provider.getBarsProgressive(info.id, '60', { limit: 1000 }, batch => batches.push(batch)), failure)
    assert.equal(batches.at(-1).length, 200)
  } finally { provider.destroy() }
})
