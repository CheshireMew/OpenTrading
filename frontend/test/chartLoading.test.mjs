import test from 'node:test'
import assert from 'node:assert/strict'
import { browserSession } from './helpers/browserSession.mjs'

test('market switches and replay paint promptly while full history continues loading', {
  timeout: 60_000, skip: !process.env.OPENTRADING_TEST_BROWSER,
}, async t => {
  const browser = await browserSession()
  const page = await browser.page(await browser.context())
  t.after(async () => { await page.close(); await browser.close() })
  const result = await page.evaluate(`
    const { ref } = await import('/test/helpers/vuePage.ts');
    const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
    const { createWorkspaceChart } = await import('/src/modules/chartWorkspace/workspaceChart.ts');
    const { OpenTradingProvider } = await import('/src/modules/chartWorkspace/provider.ts');
    const { periodStart, periodEnd, periodDuration } = await import('/src/modules/chartWorkspace/replayModel.ts');
    const { createBarRequests } = await import('/src/modules/chartWorkspace/barRequests.ts');
    await import('/src/style.css');
    const catalog = ['BTC', 'ETH'].map(base => ({ id: 'binance:spot:' + base + 'USDT', symbol: base + 'USDT', name: base + '/USDT',
      exchange: 'binance', market: 'spot', currency: 'USDT', timezone: 'Etc/UTC', session: '24x7',
      timeframes: ['1m','5m','15m','30m','1h','4h','1d','1w','1M'], metadata: { mintick: .01, pricescale: 100, minmove: 1 } }));
    const requests = [], errors = []; let failHistory = false;
    const respond = async (query, signal, replay) => {
      const started = performance.now(); requests.push({ ...query, replay, started });
      await new Promise((resolve, reject) => { const timer = setTimeout(resolve, 40 + query.limit * .25);
        signal?.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true }); });
      if (failHistory && !replay && query.timeframe === '30m' && query.limit > 200) throw new Error('background history unavailable');
      const end = query.end ?? Date.now(), step = query.timeframe === '1M' ? 30 * 86400000 : periodDuration(query.timeframe);
      const last = periodStart(end - (replay ? 1 : 0), query.timeframe);
      const start = query.start ?? last - (query.limit - 1) * step;
      return { symbol: catalog.find(s => s.id === query.symbol), bars: Array.from({ length: Math.max(0, Math.min(query.limit, Math.floor((end - start) / step) + (replay ? 0 : 1))) }, (_, i) => {
        const time = start + i * step; return { time, closeTime: periodEnd(time, query.timeframe), open: 100, high: 102, low: 99, close: 101, volume: step / 60000, closed: replay || time + step <= Date.now() };
      }) };
    };
    const marketBars = createBarRequests((query, signal) => respond(query, signal, false));
    const replayBars = createBarRequests((query, signal) => respond(query, signal, true), { historical: true });
    chartApi.bars = marketBars.load; chartApi.cachedBars = marketBars.peek;
    chartApi.replayBars = replayBars.load;
    OpenTradingProvider.prototype.subscribe = () => () => {};
    const host = document.createElement('div'); host.style.cssText = 'width:1000px;height:600px'; document.body.append(host);
    const control = createWorkspaceChart({ host: ref(host), theme: ref('dark'), dirty() {}, log() {}, refreshQuotes() {}, onError: error => errors.push(String(error)) });
    control.initialize(catalog); const chart = control.workspace.value.active.chart;
    const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
    const waitFor = async check => { const deadline = performance.now() + 10000;
      while (!check()) { if (performance.now() > deadline) throw new Error('Loading timed out: ' + JSON.stringify({errors, requests})); await frame(); } };
    await chart.ready(); await chart.historyComplete();
    const metrics = {};
    const measure = async (name, action) => {
      const began = performance.now(), before = requests.length;
      await action(); await waitFor(() => !!chart.getVisibleRange()); await frame();
      metrics[name] = { paintMs: Math.round(performance.now() - began), requests: requests.length - before };
      await chart.historyComplete();
      metrics[name].completeMs = Math.round(performance.now() - began);
    };
    try {
      await measure('coldPeriod', () => control.setPeriod('15'));
      await measure('warmPeriod', () => control.setPeriod('60'));
      await measure('coldSymbol', () => control.selectSymbol(catalog[1].id));
      await measure('warmSymbol', () => control.selectSymbol(catalog[0].id));
      control.preloadPeriod('5');
      await waitFor(() => requests.some(query => query.timeframe === '5m'));
      await new Promise(resolve => setTimeout(resolve, 120));
      await measure('preloadedPeriod', () => control.setPeriod('5'));
      await control.setPeriod('60'); await chart.historyComplete();
      let historyReason;
      const offHistory = chart.on('history:complete', event => { historyReason = event.reason });
      failHistory = true; await control.setPeriod('30');
      await waitFor(() => chart.market.timeframe === '30' && historyReason === 'aborted');
      const failedPreviewRetained = !!chart.getVisibleRange();
      failHistory = false; offHistory();
      await control.setPeriod('60'); await chart.historyComplete();
      const old = control.setPeriod('240');
      await control.setPeriod('15'); await old; await chart.historyComplete();
      const latestSelectionWon = chart.market.timeframe === '15';
      await control.setPeriod('60'); await chart.historyComplete();
      const replayAt = periodStart(Date.now() - 86400000 * 30, '1d') + 8 * 3600000;
      await measure('replayStart', () => control.replay.start(replayAt));
      for (let i = 0; i < 10; i++) await control.replay.step();
      const clock = control.replay.now.value;
      await measure('replayDay', () => control.replay.setTimeframe('D'));
      await measure('replayHour', () => control.replay.setTimeframe('60'));
      return { metrics, failedPreviewRetained, latestSelectionWon, replayClockPreserved: control.replay.now.value === clock,
        knownHistoryOnly: control.replay.visibleBars.every(bar => bar.time < clock), errors };
    } finally { control.dispose() }
  `)
  console.log('Chart loading latency with 40ms round trips and 0.25ms/candle:', JSON.stringify(result))
  assert.deepEqual(result.errors, [])
  assert.equal(result.replayClockPreserved, true)
  assert.equal(result.knownHistoryOnly, true)
  assert.equal(result.failedPreviewRetained, true)
  assert.equal(result.latestSelectionWon, true)
  assert.ok(result.metrics.coldPeriod.paintMs < result.metrics.coldPeriod.completeMs)
  assert.ok(result.metrics.coldSymbol.paintMs < result.metrics.coldSymbol.completeMs)
  assert.ok(result.metrics.replayStart.paintMs < result.metrics.replayStart.completeMs)
})
