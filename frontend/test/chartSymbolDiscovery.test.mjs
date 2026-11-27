import test from 'node:test'
import assert from 'node:assert/strict'
import { browserSession } from './helpers/browserSession.mjs'

test('the chart automatically publishes new catalog entries and pauses refreshes with its lifecycle', {
  timeout: 45_000, skip: !process.env.OPENTRADING_TEST_BROWSER,
}, async () => {
  const browser = await browserSession()
  const page = await browser.page(await browser.context())
  try {
    const result = await page.evaluate(`
      const { ref } = await import('/test/helpers/vuePage.ts');
      const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
      const { createWorkspaceChart } = await import('/src/modules/chartWorkspace/workspaceChart.ts');
      const { OpenTradingProvider } = await import('/src/modules/chartWorkspace/provider.ts');
      const product = (base, market = 'usdm') => ({ id: 'binance:' + market + ':' + base + 'USDT',
        symbol: base + 'USDT', name: base + '/USDT', exchange: 'binance', market, currency: 'USDT',
        timezone: 'Etc/UTC', session: '24x7', timeframes: ['1m', '1h'],
        metadata: { mintick: .01, minmove: 1, pricescale: 100, mincontract: .01 } });
      const spot = product('BTC', 'spot'), etf = product('QQQ'), newProduct = product('BRANDNEW');
      let catalog = [spot], fail = false, release;
      let gate = new Promise(resolve => { release = resolve });
      const requests = [], timers = new Map();
      const fetchOriginal = window.fetch, intervalOriginal = window.setInterval, clearOriginal = window.clearInterval;
      window.fetch = async (url, init) => {
        const parsed = new URL(String(url), location.origin);
        if (parsed.pathname !== '/api/v1/chart-workspace/symbols') return fetchOriginal(url, init);
        requests.push(parsed.searchParams.get('wait'));
        if (gate) await gate;
        return new Response(JSON.stringify(fail ? { detail: 'temporary source outage' } : catalog),
          { status: fail ? 503 : 200, headers: { 'Content-Type': 'application/json' } });
      };
      window.setInterval = (callback, delay, ...args) => {
        const id = intervalOriginal(callback, delay, ...args);
        if (delay === 60000) timers.set(id, callback);
        return id;
      };
      window.clearInterval = id => { timers.delete(id); clearOriginal(id) };
      chartApi.bars = async query => ({ symbol: catalog.find(item => item.id === query.symbol), timeframe: query.timeframe,
        source: 'binance', bars: [{ time: 60000, closeTime: 120000, open: 100, high: 103, low: 99,
          close: 101, volume: 10, closed: true }] });
      chartApi.cachedBars = () => undefined;
      OpenTradingProvider.prototype.subscribe = () => () => {};
      const host = document.createElement('div'); host.style.cssText = 'width:1000px;height:600px'; document.body.append(host);
      const errors = [];
      const control = createWorkspaceChart({ host: ref(host), theme: ref('dark'), dirty() {}, refreshQuotes() {},
        log() {}, onError: error => errors.push(String(error)) });
      try {
        control.initialize([spot]);
        const pending = control.refreshCatalog(), shared = pending === control.refreshCatalog();
        const initialCount = control.symbols.value.length;
        catalog = [spot, etf]; release(); gate = undefined;
        await pending;
        const initialUpdated = control.symbols.value.some(item => item.id === etf.id);
        await control.selectSymbol(etf.id);
        const selectedEtf = control.activeSymbolId.value === etf.id;
        catalog = [spot, etf, newProduct];
        for (const refresh of timers.values()) refresh();
        await control.refreshCatalog();
        const newProductAdded = control.symbols.value.some(item => item.id === newProduct.id);
        fail = true;
        for (const refresh of timers.values()) refresh();
        await control.refreshCatalog().catch(() => {});
        const keptAfterFailure = control.symbols.value.some(item => item.id === newProduct.id);
        control.pause(); const pausedTimers = timers.size;
        fail = false; catalog = [spot, etf];
        control.resume(); await control.refreshCatalog();
        const resumedTimers = timers.size, refreshedOnReturn = control.symbols.value.length === 2;
        gate = new Promise(resolve => { release = resolve }); catalog = [spot];
        const late = control.refreshCatalog();
        control.dispose(); release(); await late;
        return { shared, initialCount, initialUpdated, selectedEtf, newProductAdded, keptAfterFailure,
          pausedTimers, resumedTimers, refreshedOnReturn, disposedTimers: timers.size,
          ignoredLateResponse: control.symbols.value.length === 2, requests, errors };
      } finally {
        control.dispose(); window.fetch = fetchOriginal;
        window.setInterval = intervalOriginal; window.clearInterval = clearOriginal;
      }
    `)
    assert.equal(result.shared, true)
    assert.equal(result.initialCount, 1)
    assert.equal(result.initialUpdated, true)
    assert.equal(result.selectedEtf, true)
    assert.equal(result.newProductAdded, true)
    assert.equal(result.keptAfterFailure, true)
    assert.equal(result.pausedTimers, 0)
    assert.equal(result.resumedTimers, 1)
    assert.equal(result.refreshedOnReturn, true)
    assert.equal(result.disposedTimers, 0)
    assert.equal(result.ignoredLateResponse, true)
    assert.ok(result.requests.length >= 5)
    assert.ok(result.requests.every(wait => wait === 'true'))
    assert.deepEqual(result.errors, [])
  } finally { await page.close(); await browser.close() }
})
