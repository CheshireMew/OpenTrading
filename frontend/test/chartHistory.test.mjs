import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import { browserSession } from './helpers/browserSession.mjs'

const source = fs.readFileSync(new URL('../src/modules/chartWorkspace/chartHistory.ts', import.meta.url), 'utf8')
const exports = {}
new Function('exports', ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(exports)
const { installChartHistory } = exports
const settle = async () => { for (let i = 0; i < 8; i++) await Promise.resolve() }

function fixture(t) {
  const handlers = new Map(), requests = [], depths = [], loading = [], errors = []
  let complete = Promise.resolve(), resolveComplete = () => {}, enabled = true
  const chart = {
    market: { symbol: 'opentrading:binance:spot:PAXGUSDT', timeframe: '60', bars: 1000, offline: false },
    getVisibleRange: () => ({ from: 1900, to: 1999 }),
    historyComplete: () => complete,
    on(event, callback) {
      const listeners = handlers.get(event) ?? new Set()
      handlers.set(event, listeners); listeners.add(callback)
      return () => listeners.delete(callback)
    },
    async setMarket(next) {
      Object.assign(this.market, next); requests.push(next)
      complete = new Promise(resolve => { resolveComplete = resolve })
    },
  }
  const emit = (event, value) => { for (const listener of handlers.get(event) ?? []) listener(value) }
  const loader = installChartHistory(chart, { enabled: () => enabled, onDepth: value => depths.push(value),
    onLoading: value => loading.push(value), onError: error => errors.push(error) })
  t.after(() => loader.dispose())
  const finish = (oldestTime, barsLoaded, reason = 'depth') => {
    emit('history:complete', { oldestTime, barsLoaded, reason }); resolveComplete()
  }
  return { chart, loader, emit, finish, requests, depths, loading, errors, pause: value => { enabled = !value } }
}

test('panning loads older batches once and keeps filling a viewport beyond the loaded candles', async t => {
  const f = fixture(t)
  f.finish(1000, 1000); await settle()
  assert.equal(f.requests.length, 0, 'the recent startup view needs no extra history')
  f.emit('viewport:changed', { from: 1000, to: 1100 }); await settle()
  for (let i = 0; i < 10; i++) f.loader.refresh({ from: 990, to: 1090 })
  await settle()
  assert.deepEqual(f.requests, [{ bars: 2000 }], 'an in-flight batch must not be restarted')
  assert.deepEqual(f.loading, [1000])
  f.finish(0, 2000); await settle()
  assert.equal(f.requests.length, 1)
  f.loader.refresh({ from: -1600, to: -1500 }); await settle()
  f.finish(-1000, 3000); await settle()
  f.finish(-2000, 4000); await settle()
  assert.deepEqual(f.requests.map(request => request.bars), [2000, 3000, 4000])
  assert.deepEqual(f.depths, [2000, 3000, 4000])
})

test('failed history can retry on another pan, genesis stops loading, and a new market resets that boundary', async t => {
  const f = fixture(t)
  const range = { from: 1000, to: 1100 }
  f.finish(1000, 1000); f.loader.refresh(range); await settle()
  f.finish(1000, 1000, 'aborted'); await settle()
  for (let i = 0; i < 10; i++) f.loader.refresh(range)
  await settle()
  assert.equal(f.requests.length, 1, 'repainting an unchanged viewport must not retry an error')
  f.loader.refresh({ from: 990, to: 1090 }); await settle()
  assert.equal(f.requests.length, 2, 'another pan can retry the failed request')
  f.finish(1000, 1000, 'genesis')
  f.loader.refresh({ from: -1000, to: -900 }); await settle()
  assert.equal(f.requests.length, 2)
  f.chart.market = { ...f.chart.market, symbol: 'opentrading:binance:spot:ETHUSDT', bars: 1000 }
  f.emit('load:start', {}); f.finish(1000, 1000)
  f.loader.refresh(range); await settle()
  assert.equal(f.requests.length, 3, 'one symbol reaching its beginning must not block another')
})

test('a temporary history failure retries without another pan and stops after three attempts', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const f = fixture(t)
  f.finish(1000, 1000); f.loader.refresh({ from: 1000, to: 1100 }); await settle()
  for (const wait of [1500, 3000, 6000]) {
    const count = f.requests.length
    f.finish(1000, 1000, 'aborted'); await settle()
    t.mock.timers.tick(wait - 1); await settle()
    assert.equal(f.requests.length, count)
    t.mock.timers.tick(1); await settle()
    assert.equal(f.requests.length, count + 1)
    assert.equal(f.requests.at(-1).bars, 2000, 'a retry must not increase the amount of requested history')
  }
  f.finish(1000, 1000, 'aborted'); await settle()
  t.mock.timers.tick(60_000); await settle()
  assert.equal(f.requests.length, 4)
  f.finish(1000, 2000, 'genesis'); await settle()
  t.mock.timers.tick(60_000); await settle()
  assert.equal(f.requests.length, 4)
})

test('an initial failed page can recover even when there is no visible data yet', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const f = fixture(t)
  f.chart.getVisibleRange = () => null
  f.finish(0, 0, 'aborted'); await settle()
  t.mock.timers.tick(1500); await settle()
  assert.equal(f.requests.length, 1)
  f.finish(1000, 1000); await settle()
  t.mock.timers.tick(60_000); await settle()
  assert.equal(f.requests.length, 1)
})

test('manual depth loading, replay, offline data, hidden charts and disposed cells are not superseded', async t => {
  const f = fixture(t)
  f.finish(1000, 1000)
  await f.chart.setMarket({ bars: 5000 })
  f.loader.refresh({ from: 1000, to: 1100 }); await settle()
  assert.equal(f.requests.length, 1, 'a manual history load already owns the pending history cycle')
  f.finish(-3000, 5000)
  for (const market of [
    { offline: true, symbol: 'opentrading:binance:spot:PAXGUSDT' },
    { offline: false, symbol: 'replay1:binance:spot:PAXGUSDT' },
  ]) {
    Object.assign(f.chart.market, market)
    f.loader.refresh({ from: -4000, to: -3900 }); await settle()
    assert.equal(f.requests.length, 1)
  }
  Object.assign(f.chart.market, { symbol: 'opentrading:binance:spot:PAXGUSDT' })
  f.pause(true); f.loader.refresh(); await settle()
  assert.equal(f.requests.length, 1)
  f.pause(false); f.loader.refresh(); await settle()
  assert.equal(f.requests.length, 2)
  f.loader.dispose(); f.finish(-4000, 6000)
  f.loader.refresh({ from: -5000, to: -4900 }); await settle()
  assert.equal(f.requests.length, 2)
})

test('the real workspace loads beyond 1000 candles, preserves the view and continues after symbol and period changes', {
  timeout: 60_000, skip: !process.env.OPENTRADING_TEST_BROWSER,
}, async t => {
  const browser = await browserSession()
  const page = await browser.page(await browser.context())
  t.after(async () => { await page.close(); await browser.close() })
  const initial = await page.evaluate(`
    const { ref } = await import('/test/helpers/vuePage.ts');
    await import('/src/style.css');
    const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
    const { OpenTradingProvider } = await import('/src/modules/chartWorkspace/provider.ts');
    const { createWorkspaceChart } = await import('/src/modules/chartWorkspace/workspaceChart.ts');
    const { WorkspaceRenderer } = await import('/src/modules/chartWorkspace/chartPresentation.ts');
    window.errors = []; window.queries = []; window.historyEvents = []; window.fullRanges = [];
    const bindViewport = WorkspaceRenderer.prototype.onHistoryViewport;
    WorkspaceRenderer.prototype.onHistoryViewport = function(listener) {
      return bindViewport.call(this, range => { fullRanges.push(range); if (fullRanges.length > 6) fullRanges.shift(); listener(range) });
    };
    window.catalog = ['PAXG', 'ETH'].map(base => ({ id: 'binance:spot:' + base + 'USDT', symbol: base + 'USDT',
      name: base + '/USDT', exchange: 'binance', market: 'spot', currency: 'USDT', timezone: 'Etc/UTC',
      session: '24x7', timeframes: ['1h', '5m'], metadata: { mintick: .01, pricescale: 100, minmove: 1 } }));
    chartApi.symbols = async () => catalog; chartApi.quotes = async () => [];
    chartApi.bars = async query => {
      queries.push(query);
      await new Promise(resolve => setTimeout(resolve, 5));
      const symbol = catalog.find(info => info.id === query.symbol), step = query.timeframe === '5m' ? 300000 : 3600000;
      const end = Math.floor(query.end / step) * step, genesis = Math.floor(Date.now() / step) * step - 12000 * step;
      const start = Math.max(genesis, query.start ?? end - (query.limit - 1) * step);
      return { symbol, bars: Array.from({ length: Math.max(0, Math.min(query.limit, Math.floor((end - start) / step) + 1)) }, (_, i) => {
        const time = start + i * step; return { time, closeTime: time + step, open: 100, high: 102, low: 99, close: 101, volume: 1 };
      }) };
    };
    OpenTradingProvider.prototype.subscribe = () => () => {};
    const host = document.createElement('div'); host.style.cssText = 'width:1000px;height:600px'; document.body.append(host);
    window.control = createWorkspaceChart({ host: ref(host), theme: ref('dark'), dirty() {}, refreshQuotes() {}, log() {},
      onError: error => errors.push(String(error)) });
    control.activeSymbolId.value = catalog[0].id; control.initialize(catalog);
    window.chart = control.workspace.value.active.chart;
    chart.on('history:complete', event => historyEvents.push(event));
    await chart.ready(); await chart.historyComplete();
    window.waitFor = async predicate => { const until = Date.now() + 5000;
      while (!predicate()) { if (Date.now() > until) throw new Error('History did not reach the viewport: ' + JSON.stringify({ queries, historyEvents, fullRanges, range: chart.getVisibleRange(), errors }));
        await new Promise(resolve => setTimeout(resolve, 20)); } };
    window.waitForHistory = async () => {
      // Superseding a backfill resolves its old promise. Follow the current
      // load before using its oldest candle as the next pan's starting point.
      let complete;
      do { complete = chart.historyComplete(); await complete; } while (complete !== chart.historyComplete());
    };
    return { depth: chart.market.bars, loaded: historyEvents.at(-1).barsLoaded, requests: queries.length, errors };
  `)
  assert.deepEqual(initial, { depth: 1000, loaded: 1000, requests: 2, errors: [] })

  const panned = await page.evaluate(`
    const step = 3600000, oldest = historyEvents.at(-1).oldestTime;
    const from = oldest - 30 * step, to = oldest + 30 * step;
    chart.setVisibleRange({ from, to });
    await waitFor(() => historyEvents.at(-1).oldestTime < oldest && chart.getVisibleRange()?.from <= from + step);
    return { from, to, range: chart.getVisibleRange(), depth: chart.market.bars, loaded: historyEvents.at(-1).barsLoaded,
      savedDepth: control.snapshot().charts[0].bars, displayedDepth: control.historyDepth.value, errors };
  `)
  assert.equal(panned.depth, 2000)
  assert.equal(panned.loaded, 2000)
  assert.equal(panned.savedDepth, 2000)
  assert.equal(panned.displayedDepth, 2000)
  assert.ok(Math.abs(panned.range.from - panned.from) <= 3600000)
  assert.ok(Math.abs(panned.range.to - panned.to) <= 3600000)

  const blank = await page.evaluate(`
    const step = 3600000, oldest = historyEvents.at(-1).oldestTime;
    const from = oldest - 59 * step, to = oldest + step;
    chart.setVisibleRange({ from, to }); const clippedBefore = chart.getVisibleRange();
    await waitFor(() => historyEvents.at(-1).oldestTime < oldest && chart.getVisibleRange() !== null);
    return { clippedBefore, from, to, range: chart.getVisibleRange(), depth: chart.market.bars, errors };
  `)
  assert.ok(!blank.clippedBefore || blank.clippedBefore.to - blank.clippedBefore.from <= 3600000)
  assert.equal(blank.depth, 3000)
  assert.ok(Math.abs(blank.range.from - blank.from) <= 3600000, JSON.stringify(blank))
  assert.ok(Math.abs(blank.range.to - blank.to) <= 3600000, JSON.stringify(blank))

  for (const change of ['symbol', 'period']) {
    const result = await page.evaluate(`
      if (input === 'symbol') await control.selectSymbol(catalog[1].id); else await control.setPeriod('5');
      await waitForHistory();
      const step = input === 'symbol' ? 3600000 : 300000, event = historyEvents.at(-1), before = chart.market.bars;
      chart.setVisibleRange({ from: event.oldestTime - 20 * step, to: event.oldestTime + 20 * step });
      await waitFor(() => historyEvents.at(-1).oldestTime < event.oldestTime);
      return { before, after: chart.market.bars, symbol: chart.market.symbol, timeframe: chart.market.timeframe,
        queries: queries.slice(-2).map(query => ({ symbol: query.symbol, timeframe: query.timeframe })), errors };
    `, change)
    assert.equal(result.after, result.before + 1000)
    assert.equal(result.symbol, 'opentrading:binance:spot:ETHUSDT')
    assert.equal(result.timeframe, change === 'symbol' ? '60' : '5')
    assert.ok(result.queries.every(query => query.symbol === 'binance:spot:ETHUSDT'))
    assert.ok(result.queries.every(query => query.timeframe === (change === 'symbol' ? '1h' : '5m')))
    assert.deepEqual(result.errors, [])
  }
  const recovered = await page.evaluate(`
    const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
    const original = chartApi.bars; let failures = 0;
    chartApi.bars = async (...args) => {
      if (!failures++) throw new Error('controlled temporary history failure');
      return original(...args);
    };
    let failureState;
    const stopFailure = chart.on('history:complete', event => {
      if (event.reason === 'aborted') failureState = {
        visible: chart.getVisibleRange(), errorReported: control.feedError.value.includes('controlled temporary'),
      };
    });
    const oldest = historyEvents.at(-1).oldestTime;
    chart.setVisibleRange({ from: oldest - 20 * 300000, to: oldest + 20 * 300000 });
    // A subsequent viewport event can retry before the next polling tick.
    // Observe the failure itself rather than requiring it to remain last.
    await waitFor(() => failureState !== undefined);
    stopFailure();
    await waitFor(() => historyEvents.at(-1).oldestTime < oldest && historyEvents.at(-1).reason === 'depth');
    return { retried: failures > 1, recovered: historyEvents.at(-1).oldestTime < oldest,
      retained: failureState.visible !== null, errorReported: failureState.errorReported, errorCleared: !control.feedError.value };
  `)
  assert.deepEqual(recovered, { retried: true, recovered: true, retained: true, errorReported: true, errorCleared: true })
  await page.evaluate('control.dispose()')

  const coldRecovery = await page.evaluate(`
    const { ref } = await import('/test/helpers/vuePage.ts');
    const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
    const { createWorkspaceChart } = await import('/src/modules/chartWorkspace/workspaceChart.ts');
    const info = { ...catalog[0], id: 'binance:spot:ZECUSDT', symbol: 'ZECUSDT', name: 'ZEC/USDT' };
    catalog.push(info);
    const original = chartApi.bars; let calls = 0;
    chartApi.bars = async (...args) => { if (++calls === 1) throw new Error('controlled initial failure'); return original(...args) };
    const host = document.createElement('div'); host.style.cssText = 'width:1000px;height:600px'; document.body.append(host);
    const fresh = createWorkspaceChart({ host: ref(host), theme: ref('dark'), dirty() {}, refreshQuotes() {}, log() {}, onError() {} });
    fresh.activeSymbolId.value = info.id; fresh.initialize([info]);
    const first = fresh.workspace.value.active.chart, events = [];
    first.on('history:complete', event => events.push(event));
    await first.ready(); await waitFor(() => events.some(event => event.reason === 'aborted'));
    const failed = events.find(event => event.reason === 'aborted');
    await waitFor(() => events.at(-1).reason === 'depth' && events.at(-1).barsLoaded >= 1000);
    const result = { initiallyEmpty: failed.barsLoaded === 0, recovered: !!first.getVisibleRange(), calls, errorCleared: !fresh.feedError.value };
    fresh.dispose(); return result;
  `)
  assert.ok(coldRecovery.initiallyEmpty && coldRecovery.recovered && coldRecovery.calls > 1 && coldRecovery.errorCleared,
    JSON.stringify(coldRecovery))
})
