import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import { browserSession } from './helpers/browserSession.mjs'

function load(name, modules = {}) {
  const source = fs.readFileSync(new URL('../src/modules/chartWorkspace/' + name, import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(id => modules[id], exports)
  return exports
}

test('daily symbols are searchable by Chinese names, source codes and aliases', () => {
  const { matchesChartSymbol, marketLabelKey, marketSymbolType } = load('symbolSearch.ts')
  const dollar = { id: 'index:index:US_DXY', symbol: 'US_DXY', name: 'US Dollar Index (DXY)', exchange: 'US', market: 'index', aliases: ['美元指数', '美指', 'DX-Y.NYB'] }
  const gold = { id: 'commodity:comex:GC1.COMEX', symbol: 'GC1.COMEX', name: 'COMEX Gold Continuous Contract', exchange: 'COMEX', market: 'commodity', aliases: ['黄金期货', 'GC=F'] }
  for (const query of ['美元指数', '美指', 'DX-Y.NYB', ' dxy ']) assert.ok(matchesChartSymbol(dollar, query))
  for (const query of ['黄金', 'gc=f', 'comex']) assert.ok(matchesChartSymbol(gold, query))
  assert.equal(matchesChartSymbol(dollar, '贸易加权'), false)
  assert.equal(marketLabelKey('fx'), 'fx')
  assert.equal(marketLabelKey('commodity'), 'commodity')
  assert.equal(marketSymbolType('commodity'), 'futures')
  assert.equal(marketSymbolType('fx'), 'forex')
  assert.equal(marketSymbolType('spot'), 'crypto')
})

test('chart provider preserves daily OHLC, paginates forward and exposes market types', async () => {
  const search = load('symbolSearch.ts')
  const info = { id: 'fx:otc:EUR/USD', symbol: 'EUR/USD', name: 'Euro / US Dollar', market: 'fx', exchange: 'OTC', currency: 'USD', timeframes: ['1d'], metadata: {}, aliases: ['欧元美元'] }
  const queries = []
  const bars = [0, 1, 2].map(i => ({ time: i * 86400000, closeTime: (i + 1) * 86400000, open: 1, high: 1.2, low: 0.9, close: 1.1, volume: 0, closed: true }))
  const { OpenTradingProvider } = load('provider.ts', {
    './api': { chartApi: { bars: async query => {
      queries.push(query)
      return { symbol: info, bars: bars.filter(b => b.time >= query.start && b.time <= query.end).slice(0, query.limit) }
    } } }, './locale': { cw: key => key, exchangeLabel: text => text },
    './symbolIcons': {}, './symbolSearch': search,
  })
  const provider = new OpenTradingProvider(() => {})
  provider.catalog = [info]
  const result = await provider.getBars('opentrading:' + info.id, 'D', { from: 0, to: 2 * 86400000, limit: 3 })
  assert.deepEqual(result.map(b => b.time), bars.map(b => b.time))
  assert.equal(result[0].high, 1.2)
  assert.equal((await provider.getSymbolInfo(info.id)).type, 'forex')
  assert.equal((await provider.listSymbols())[0].type, 'forex')
  assert.equal(queries[0].timeframe, '1d')
  await assert.rejects(provider.getBars(info.id, '60', { limit: 2 }), /onlyTimeframes/)
})

test('a saved chart resolves its own venue when the initial catalog only contains another market', async () => {
  const spot = { id: 'binance:spot:BTCUSDT', symbol: 'BTCUSDT', market: 'spot', exchange: 'binance' }
  const perpetual = { ...spot, id: 'binance:usdm:BTCUSDT', market: 'usdm' }
  const queries = []
  let release
  const ready = new Promise(resolve => { release = resolve })
  const { OpenTradingProvider } = load('provider.ts', {
    './api': { chartApi: { symbols: symbol => { queries.push(symbol); return ready } } },
    './locale': { cw: key => key }, './symbolIcons': {}, './symbolSearch': {},
  })
  const provider = new OpenTradingProvider(() => {})
  const sharedCatalog = provider.catalog = [spot]
  const requests = Promise.all([provider.resolve(perpetual.id), provider.resolve('opentrading:' + perpetual.id)])
  release([spot, perpetual])
  assert.deepEqual(await requests, [perpetual, perpetual])
  assert.deepEqual(queries, [perpetual.id])
  assert.equal(provider.catalog, sharedCatalog)
  assert.ok(sharedCatalog.includes(perpetual), 'the chart and its controls must receive the same resolved metadata')
  assert.equal(await provider.resolve(spot.id), spot)
})

function liveProvider(t, barsApi) {
  const originalSocket = globalThis.WebSocket, originalLocation = globalThis.location
  const sockets = []
  class Socket {
    static OPEN = 1
    readyState = 0
    sent = []
    constructor() { sockets.push(this) }
    send(data) { this.sent.push(JSON.parse(data)) }
    open() { this.readyState = 1; this.onopen?.() }
    close() { this.readyState = 3; this.onclose?.() }
    bar(bar, live = true) {
      const subscription = this.sent.findLast(message => message.type === 'subscribe')
      this.onmessage?.({ data: JSON.stringify({ ...subscription, type: 'bar', sequence: (this.sequence = (this.sequence ?? 0) + 1), bar, live, observed_at: Date.now() }) })
    }
  }
  globalThis.WebSocket = Socket; globalThis.location = { protocol: 'http:', host: 'localhost' }
  t.after(() => { globalThis.WebSocket = originalSocket; if (originalLocation === undefined) delete globalThis.location; else globalThis.location = originalLocation })
  const info = { id: 'binance:spot:BTCUSDT', symbol: 'BTCUSDT', market: 'spot', exchange: 'binance', timeframes: ['1m'] }
  const { OpenTradingProvider } = load('provider.ts', {
    './api': { chartApi: { bars: async (query, signal) => ({ symbol: info, bars: await barsApi(query, signal) }) }, BASE: '/api/v1/chart-workspace' },
    './locale': { cw: key => key }, './symbolIcons': {}, './symbolSearch': {},
  })
  const provider = new OpenTradingProvider(() => {}); provider.catalog = [info]
  t.after(() => provider.destroy())
  return { provider, sockets, info }
}
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { resolve, promise } }

test('hidden charts stop plot updates, keep live order quotes and repair all missed bars in order', async t => {
  const start = Math.floor(Date.now() / 60_000) * 60_000 - 180_000
  const bar = (index, close = 100) => ({ time: start + index * 60_000, closeTime: start + (index + 1) * 60_000, open: 100, high: Math.max(close, 100), low: 100, close, volume: 1 })
  const repair = deferred(), queries = []
  const { provider, sockets, info } = liveProvider(t, async query => {
    queries.push(query)
    return query.start === undefined ? [bar(0)] : repair.promise
  })
  const plotted = [], quotes = []
  const stopPlot = provider.subscribe(info.id, '1', value => plotted.push(value))
  const stopQuotes = provider.subscribeQuotes(info.id, '1', quote => quotes.push(quote.price))
  sockets[0].open()
  await provider.getBars(info.id, '1', { limit: 1 })
  sockets[0].bar(bar(0))
  provider.setPaused(true)
  sockets[0].bar(bar(1, 101))
  assert.equal(plotted.length, 1)
  assert.deepEqual(quotes, [100, 101])
  assert.equal(sockets[0].readyState, 1, 'live paper orders must retain their independent wire')
  provider.setPaused(false)
  await settle()
  assert.equal(queries[1].start, start, 'repair must re-read the last forming candle too')
  sockets[0].bar(bar(3, 999))
  assert.equal(plotted.length, 1, 'new live bars must wait until the intervening history lands')
  repair.resolve([bar(0, 102), bar(1, 103), bar(2, 104), bar(3, 105)])
  await settle()
  assert.deepEqual(plotted.slice(1).map(value => value.time), [0, 1, 2, 3].map(index => start + index * 60_000))
  assert.deepEqual(plotted.slice(1).map(value => value.close), [102, 103, 104, 999])
  assert.deepEqual(quotes, [100, 101, 999], 'historical repairs must never execute live orders')
  stopQuotes(); provider.setPaused(true)
  assert.equal(sockets[0].readyState, 3)
  assert.equal(provider.subscriptions.size, 0)
  assert.equal(provider.retry, undefined)
  stopPlot()
})

test('pausing again cancels pending history repair and disposal prevents late chart updates', async t => {
  const waiting = deferred(), start = Math.floor(Date.now() / 60_000) * 60_000
  const bar = { time: start, closeTime: start + 60_000, open: 1, high: 1, low: 1, close: 1, volume: 1 }
  let signal
  const { provider, sockets, info } = liveProvider(t, (query, currentSignal) => {
    if (query.start === undefined) return [bar]
    signal = currentSignal; return waiting.promise
  })
  const plotted = []
  provider.subscribe(info.id, '1', value => plotted.push(value)); sockets[0].open()
  await provider.getBars(info.id, '1', { limit: 1 })
  provider.setPaused(true)
  assert.equal(sockets[0].readyState, 3)
  provider.setPaused(false); await settle(); sockets[1].open()
  provider.setPaused(true)
  assert.equal(signal.aborted, true)
  provider.destroy(); waiting.resolve([bar]); await settle()
  assert.equal(plotted.length, 0)
  assert.equal(provider.repairs.size, 0)
  assert.equal(provider.retry, undefined)
})

let browser
after(async () => { await browser?.close() })
test('the real cached chart page pauses on navigation and tab hiding, then repairs before resuming', {
  timeout: 45_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER,
}, async () => {
  browser ??= await browserSession()
  const page = await browser.page(await browser.context())
  try {
    const result = await page.evaluate(`
      const { createApp, h, ref, KeepAlive, nextTick, createRouter, createMemoryHistory } = await import('/test/helpers/vuePage.ts');
      const { default: i18n } = await import('/src/i18n/index.ts'); i18n.global.locale.value = 'en';
      await import('/src/style.css'); await import('/src/styles/workspace-layouts.css');
      window.forcedVisibility = 'visible'; Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => forcedVisibility });
      window.sockets = []; window.pageErrors = []; addEventListener('unhandledrejection', event => pageErrors.push(String(event.reason)));
      class Socket {
        static OPEN = 1; readyState = 1; subscriptions = new Map(); sequence = 0;
        constructor() { sockets.push(this); setTimeout(() => this.onopen?.(), 0) }
        send(text) { const item = JSON.parse(text), key = JSON.stringify([item.symbol, item.timeframe]);
          if (item.type === 'subscribe') this.subscriptions.set(key, item); else this.subscriptions.delete(key) }
        close() { this.readyState = 3; this.subscriptions.clear(); this.onclose?.() }
        emit() { for (const item of this.subscriptions.values()) { const time = Math.floor(Date.now() / 3600000) * 3600000;
          this.onmessage?.({ data: JSON.stringify({ ...item, type: 'bar', sequence: ++this.sequence, live: true, observed_at: Date.now(),
            bar: { time, closeTime: time + 3600000, open: 100, high: 102, low: 98, close: 101, volume: 1, closed: false } }) }) } }
      }
      window.WebSocket = Socket;
      const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
      const { researchApi } = await import('/src/modules/research/api.ts'); researchApi.getWorkbench = async () => ({ alerts: [] });
      const info = { id: 'binance:spot:ETHUSDT', symbol: 'ETHUSDT', name: 'ETH/USDT', exchange: 'binance', market: 'spot', currency: 'USDT',
        timezone: 'Etc/UTC', session: '24x7', timeframes: ['1h'], metadata: { mintick: .01, pricescale: 100, minmove: 1, pointvalue: 1, mincontract: .001 } };
      chartApi.symbols = async () => [info]; chartApi.quotes = async () => []; chartApi.documents = async () => [];
      window.repairs = [];
      chartApi.bars = async query => {
        if (query.start !== undefined) repairs.push(query);
        const step = 3600000, end = Math.floor(Number(query.end ?? Date.now()) / step) * step;
        const start = query.start === undefined ? end - (query.limit - 1) * step : query.start;
        return { symbol: info, bars: Array.from({ length: Math.min(query.limit, Math.floor((end - start) / step) + 1) }, (_, index) => {
          const time = start + index * step; return { time, closeTime: time + step, open: 100, high: 102, low: 98, close: 100, volume: 1, closed: time + step <= Date.now() } }) };
      };
      const { OpenTradingProvider } = await import('/src/modules/chartWorkspace/provider.ts');
      window.plotted = 0; const subscribe = OpenTradingProvider.prototype.subscribe;
      OpenTradingProvider.prototype.subscribe = function(id, tf, callback) { return subscribe.call(this, id, tf, bar => { plotted++; callback(bar) }) };
      const { default: Page } = await import('/src/views/ChartWorkspace.vue');
      const selected = ref(true), Other = { render: () => h('div', 'Other page') };
      const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: Other }] });
      const app = createApp({ setup: () => () => h('div', { style: 'height:700px' }, [h(KeepAlive, {}, { default: () => h(selected.value ? Page : Other) })]) }).use(i18n).use(router);
      app.mount('#app');
      const waitFor = async predicate => { const deadline = performance.now() + 8000; while (!predicate()) {
        if (performance.now() > deadline) throw new Error('Chart lifecycle did not settle: ' + document.body.textContent);
        await new Promise(requestAnimationFrame) } await nextTick() };
      const wires = () => sockets.reduce((sum, socket) => sum + socket.subscriptions.size, 0);
      await waitFor(() => wires() === 1 && !document.querySelector('.cw-loading'));
      sockets.at(-1).emit(); await nextTick(); const before = plotted;
      const initialSymbol = document.querySelector('.cw-symbol').textContent;
      selected.value = false; await nextTick(); await waitFor(() => wires() === 0);
      sockets.forEach(socket => socket.emit()); const whileAway = plotted;
      selected.value = true; await nextTick(); await waitFor(() => wires() === 1 && repairs.length > 0 && plotted > before);
      const afterReturn = plotted, repaired = repairs.length;
      forcedVisibility = 'hidden'; document.dispatchEvent(new Event('visibilitychange')); await nextTick();
      const hiddenWires = wires(); sockets.forEach(socket => socket.emit()); const whileHidden = plotted;
      forcedVisibility = 'visible'; document.dispatchEvent(new Event('visibilitychange'));
      await waitFor(() => wires() === 1 && repairs.length > repaired && plotted > afterReturn);
      const result = { initialSymbol, before, whileAway, afterReturn, hiddenWires, whileHidden, final: plotted, errors: pageErrors };
      app.unmount(); result.disposedWires = wires(); return result;
    `)
    assert.match(result.initialSymbol, /ETH/)
    assert.equal(result.before, 1)
    assert.equal(result.whileAway, result.before)
    assert.ok(result.afterReturn > result.before)
    assert.equal(result.hiddenWires, 0)
    assert.equal(result.whileHidden, result.afterReturn)
    assert.ok(result.final > result.afterReturn)
    assert.equal(result.disposedWires, 0)
    assert.deepEqual(result.errors, [])
  } finally { await page.close() }
})
