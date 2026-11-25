import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { browserSession } from './helpers/browserSession.mjs'

let session
const browser = async () => session ??= await browserSession()
after(async () => { await session?.close() })
const options = { timeout: 45_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER }

const mountScreeners = `
  const { createApp, nextTick, createRouter, createMemoryHistory } = await import('/test/helpers/vuePage.ts');
  const { default: i18n } = await import('/src/i18n/index.ts');
  i18n.global.locale.value = 'en';
  const { researchApi } = await import('/src/modules/research/api.ts');
  window.api = researchApi;
  window.a = await api.createScreener({ name: 'Screener A', filters: { market: 'all', symbols: [], includeWeb3: false } });
  window.b = await api.createScreener({ name: 'Screener B', filters: { market: 'all', symbols: [], includeWeb3: false } });
  window.pending = [];
  const originalFetch = window.fetch;
  window.fetch = (url, init) => String(url).includes('screener-preview')
    ? new Promise((resolve, reject) => pending.push({ resolve, reject })) : originalFetch(url, init);
  window.waitFor = async predicate => {
    const deadline = performance.now() + 5000;
    while (!await predicate()) { if (performance.now() > deadline) throw new Error('Page state did not settle'); await new Promise(requestAnimationFrame) }
    await nextTick();
  };
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] });
  const { default: Page } = await import('/src/views/research/MarketScreeners.vue');
  window.app = createApp(Page).use(i18n).use(router); app.mount('#app');
  await waitFor(() => document.querySelectorAll('aside button').length === 2);
  window.choose = async name => { [...document.querySelectorAll('aside button')].find(node => node.textContent.includes(name)).click(); await nextTick() };
  window.runButton = () => document.querySelector('main button.app-button-primary');
  await choose('Screener A'); runButton().click(); await waitFor(() => pending.length === 1);
`;

test('screener page keeps a late successful result with its original selection', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context())
  try {
    const result = await page.evaluate(`
      ${mountScreeners}
      await choose('Screener B');
      pending[0].resolve(new Response(JSON.stringify({ snapshotAsOf: new Date().toISOString(), historicalReplay: false,
        resultItems: [{ symbol: 'A-RESULT', market: 'spot' }], resultCount: 1 })));
      await waitFor(async () => (await api.listScreenerRuns(a.id)).items.length === 1);
      await new Promise(requestAnimationFrame);
      return { heading: document.querySelector('main h2')?.textContent, misplaced: document.querySelector('main')?.textContent.includes('A-RESULT'),
        aRuns: (await api.listScreenerRuns(a.id)).items.length, bRuns: (await api.listScreenerRuns(b.id)).items.length };
    `)
    assert.deepEqual(result, { heading: 'Screener B', misplaced: false, aRuns: 1, bRuns: 0 })
  } finally { await page.close() }
})

test('screener page ignores an old failure and its cleanup while the next selection runs', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context())
  try {
    const result = await page.evaluate(`
      ${mountScreeners}
      await choose('Screener B');
      const available = !runButton().disabled;
      if (available) { runButton().click(); await waitFor(() => pending.length === 2) }
      pending[0].reject(new Error('A failed after selection changed'));
      await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
      const protectedState = { available, busy: runButton().disabled, error: document.querySelector('[role=alert]')?.textContent ?? '' };
      if (available) {
        pending[1].resolve(new Response(JSON.stringify({ snapshotAsOf: new Date().toISOString(), historicalReplay: false,
          resultItems: [{ symbol: 'B-RESULT', market: 'spot' }], resultCount: 1 })));
        await waitFor(() => document.querySelector('main')?.textContent.includes('B-RESULT') && !runButton().disabled);
      }
      return protectedState;
    `)
    assert.deepEqual(result, { available: true, busy: true, error: '' })
  } finally { await page.close() }
})

const mountSignals = `
  const { createApp, nextTick, createRouter, createMemoryHistory } = await import('/test/helpers/vuePage.ts');
  const { default: i18n } = await import('/src/i18n/index.ts'); i18n.global.locale.value = 'en';
  const { researchApi } = await import('/src/modules/research/api.ts');
  window.pending = [];
  researchApi.listSignals = (query, signal) => new Promise((resolve, reject) => pending.push({ query, signal, resolve, reject }));
  researchApi.getSignalStats = async () => ({ overall: { total: 201, resolved: 0 }, confidenceCalibration: [], bySource: [], byStrategy: [] });
  const row = (symbol, id = symbol) => ({ id, symbol, timeframe: '1h', source: 'rules', outcomeStatus: 'pending', reason: '', version: 1 });
  window.waitFor = async predicate => { const deadline = performance.now() + 5000; while (!await predicate()) {
    if (performance.now() > deadline) throw new Error('Signal page did not settle: ' + document.body.textContent);
    await new Promise(requestAnimationFrame) } await nextTick() };
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }] });
  const { default: Page } = await import('/src/views/research/TradeSignalReview.vue');
  const app = createApp(Page).use(i18n).use(router); app.mount('#app');
  await waitFor(() => pending.length === 1);
  const filter = async symbol => { const input = document.querySelector('input.app-control'); input.value = symbol;
    input.dispatchEvent(new Event('input', { bubbles: true })); await nextTick();
    [...document.querySelectorAll('button')].find(node => node.textContent === i18n.global.t('signalReview.filter')).click(); await nextTick() };
`;

for (const outcome of ['success', 'failure']) {
  test(`signal page ignores an old ${outcome} after a new filter has completed`, options, async () => {
    const instance = await browser(), page = await instance.page(await instance.context())
    try {
      const result = await page.evaluate(`
        ${mountSignals}
        pending[0].resolve({ items: [], total: 0 }); await waitFor(() => !document.body.textContent.includes(i18n.global.t('signalReview.loading')));
        await filter('BTC'); await waitFor(() => pending.length === 2);
        await filter('ETH'); await waitFor(() => pending.length === 3);
        pending[2].resolve({ items: [row('ETH/USDT')], total: 1 });
        await waitFor(() => document.querySelector('article a')?.textContent === 'ETH/USDT');
        if (input === 'success') pending[1].resolve({ items: [row('BTC/USDT')], total: 1 });
        else pending[1].reject(new Error('old BTC request failed'));
        await new Promise(requestAnimationFrame); await nextTick();
        const result = { symbol: document.querySelector('article a')?.textContent, error: document.querySelector('[role=alert]')?.textContent ?? '', canceled: pending[1].signal.aborted };
        app.unmount(); return result;
      `, outcome)
      assert.deepEqual(result, { symbol: 'ETH/USDT', error: '', canceled: true })
    } finally { await page.close() }
  })
}

test('signal page reaches record 201, preserves the displayed range after failure and recovers a shrunken last page', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context())
  try {
    const result = await page.evaluate(`
      ${mountSignals}
      const all = Array.from({ length: 201 }, (_, index) => row('S' + index, String(index)));
      pending[0].resolve({ items: all.slice(0, 200), total: all.length });
      await waitFor(() => document.querySelectorAll('article a').length === 200);
      let fail = false;
      researchApi.listSignals = async query => { if (fail) throw new Error('Network Error'); return { items: all.slice(query.offset, query.offset + query.limit), total: all.length } };
      const pageButton = key => [...document.querySelectorAll('nav button')].find(node => node.textContent === i18n.global.t('signalReview.' + key));
      pageButton('nextPage').click(); await waitFor(() => document.querySelectorAll('article a').length === 1);
      const lastSymbol = document.querySelector('article a').textContent;
      fail = true; pageButton('previousPage').click(); await waitFor(() => document.querySelector('[role=alert]'));
      const failed = { symbol: document.querySelector('article a').textContent, range: document.querySelector('nav span').textContent, enabled: !pageButton('previousPage').disabled };
      fail = false;
      researchApi.setSignalArchived = async () => { all.pop(); return {} };
      [...document.querySelectorAll('article button')].find(node => node.textContent === i18n.global.t('signalReview.archive')).click();
      await waitFor(() => document.querySelectorAll('article a').length === 200 && !document.querySelector('nav'));
      const result = { lastSymbol, failed, afterArchive: document.querySelectorAll('article a').length, error: document.querySelector('[role=alert]')?.textContent ?? '' };
      app.unmount(); return result;
    `)
    assert.equal(result.lastSymbol, 'S200')
    assert.equal(result.failed.symbol, 'S200')
    assert.match(result.failed.range, /201.*201.*201/)
    assert.equal(result.failed.enabled, true)
    assert.equal(result.afterArchive, 200)
    assert.equal(result.error, '')
  } finally { await page.close() }
})
