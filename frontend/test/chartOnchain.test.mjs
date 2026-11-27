import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import { browserSession } from './helpers/browserSession.mjs'

function load(name, modules = {}) {
  const exports = {}
  const source = fs.readFileSync(new URL('../src/modules/chartWorkspace/' + name + '.ts', import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  new Function('require', 'exports', code)(id => modules[id] ?? (() => { throw Error('Unexpected import ' + id) })(), exports)
  return exports
}

test('a saved chain address resolves its own source even when its token name matches Alpha', async () => {
  const search = load('symbolSearch')
  const address = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
  const alpha = { id: 'binance:alpha:ALPHA_1USDT', symbol: 'ALPHA_1USDT', name: 'SAME/USDT',
    market: 'alpha', exchange: 'binance', currency: 'USDT', timeframes: ['1m'], metadata: { basecurrency: 'SAME' } }
  const chain = { ...alpha, id: 'web3:solana:' + address, symbol: address, name: 'SAME/USD',
    market: 'web3', exchange: 'solana', currency: 'USD', metadata: { contract_address: address, basecurrency: 'SAME' } }
  const calls = []
  const { OpenTradingProvider } = load('provider', {
    './api': { chartApi: {
      symbols: async key => { calls.push(['resolve', key]); return [alpha, chain] },
      bars: async query => { calls.push(['bars', query.symbol]); return { symbol: chain, bars: [
        { time: 0, closeTime: 60000, open: 200, high: 203, low: 199, close: 201, volume: 10, closed: true }] } },
    } }, './locale': { cw: key => key, exchangeLabel: value => value }, './symbolIcons': {}, './symbolSearch': search,
  })
  const provider = new OpenTradingProvider(() => {})
  provider.catalog = [alpha]
  assert.equal((await provider.resolve(chain.id)).symbol, address)
  const bars = await provider.getBars('opentrading:' + chain.id, '1', { from: 0, to: 59999, limit: 1 })
  assert.equal(bars[0].close, 201)
  assert.deepEqual(calls, [['resolve', chain.id], ['bars', chain.id]])
  assert.equal((await provider.getSymbolInfo(chain.id)).currency, 'USD')
  assert.equal((await provider.listSymbols()).find(info => info.ticker === chain.id).type, 'crypto')
  assert.equal(search.isOnchainAddressQuery(address), true)
  assert.equal(search.isOnchainAddressQuery('bsc:0x' + 'ab'.repeat(20)), true)
  assert.equal(search.isOnchainAddressQuery('SAME'), false)
  assert.equal(search.matchesChartSymbol(chain, address), true)
  assert.equal(search.matchesChartSymbol(chain, address.toLowerCase()), false)
  assert.equal(search.matchesChartSymbol(chain, 'bsc:' + address), false)
  provider.destroy()
})

let browser
after(async () => { await browser?.close() })

test('the real symbol picker separates chain prices, searches addresses and ignores cancelled searches', {
  timeout: 45_000, skip: !process.env.OPENTRADING_TEST_BROWSER,
}, async () => {
  browser ??= await browserSession()
  const page = await browser.page(await browser.context())
  try {
    const result = await page.evaluate(`
      const { createApp, h, ref, nextTick } = await import('/test/helpers/vuePage.ts');
      const { default: i18n } = await import('/src/i18n/index.ts'); i18n.global.locale.value = 'en';
      const { default: Picker } = await import('/src/components/chartWorkspace/WorkspaceSymbolPicker.vue');
      await import('/src/style.css');
      const known = '0x' + 'ab'.repeat(20), stale = '0x' + 'cd'.repeat(20), address = '0x' + 'ef'.repeat(20);
      const alpha = { id: 'binance:alpha:ALPHA_1USDT', symbol: 'ALPHA_1USDT', name: 'NVDAon/USDT',
        market: 'alpha', exchange: 'binance', currency: 'USDT', timeframes: ['1m'], metadata: {} };
      const chain = { ...alpha, id: 'web3:bsc:' + known, symbol: known, name: 'NVDAon/USD',
        market: 'web3', exchange: 'bsc', currency: 'USD' };
      const discovered = { ...chain, id: 'web3:base:' + address, symbol: address, name: 'NEW/USD' };
      const original = window.fetch, requests = [], pending = new Map(), selected = [], updates = [];
      window.fetch = async (url, init) => {
        const parsed = new URL(String(url), location.origin);
        if (parsed.pathname !== '/api/v1/chart-workspace/symbols/search') return original(url, init);
        const query = parsed.searchParams.get('query'); requests.push(query);
        return await new Promise((resolve, reject) => {
          pending.set(query, resolve);
          init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
        });
      };
      const open = ref(true), symbols = ref([alpha, chain]);
      const app = createApp({ setup: () => () => h(Picker, { modelValue: open.value, symbols: symbols.value,
        title: 'switchSymbol', 'onUpdate:modelValue': value => { open.value = value },
        onSelect: id => selected.push(id), onDiscovered: items => { updates.push(items.map(item => item.id)); symbols.value.push(...items) } }) });
      const host = document.createElement('div'); document.body.append(host); app.use(i18n); app.mount(host);
      const waitFor = async check => { const until = performance.now() + 5000; while (!check()) {
        if (performance.now() > until) throw Error('Picker did not settle'); await new Promise(resolve => setTimeout(resolve, 10)); } };
      const searchField = () => document.querySelector('.symbol-picker input');
      const enter = async text => { searchField().value = text; searchField().dispatchEvent(new Event('input', { bubbles: true })); await nextTick() };
      const names = () => [...document.querySelectorAll('.symbol-results button strong')].map(node => node.textContent);
      try {
        await nextTick(); await enter('NVDAon'); const both = names();
        const labels = [...document.querySelectorAll('.symbol-results button small')].map(node => node.textContent);
        [...document.querySelectorAll('.symbol-filters button')].find(node => node.textContent === 'On-chain').click();
        await nextTick(); const chainOnly = names();
        await enter(stale); await waitFor(() => requests.length === 1);
        await enter('cancelled'); pending.get(stale)(new Response(JSON.stringify([{ ...discovered, id: 'stale' }])));
        await nextTick(); await new Promise(resolve => setTimeout(resolve, 20));
        const ignoredStale = !updates.length;
        await enter(address); await waitFor(() => requests.length === 2);
        pending.get(address)(new Response(JSON.stringify([discovered]), { headers: { 'Content-Type': 'application/json' } }));
        await waitFor(() => names().includes('NEW/USD'));
        document.querySelector('.symbol-results button').click(); await nextTick();
        open.value = true; await nextTick();
        const savedSelection = symbols.value.some(item => item.id === discovered.id);
        const section = document.querySelector('.symbol-picker').getBoundingClientRect();
        return { both, labels, chainOnly, ignoredStale, selected, savedSelection,
          fits: section.left >= 0 && section.right <= innerWidth && section.bottom <= innerHeight };
      } finally { app.unmount(); window.fetch = original }
    `)
    assert.deepEqual(result.both.sort(), ['NVDAon/USD', 'NVDAon/USDT'])
    assert.ok(result.labels.includes('Binance Alpha'))
    assert.ok(result.labels.some(label => label.includes('BSC') && label.includes('On-chain')))
    assert.deepEqual(result.chainOnly, ['NVDAon/USD'])
    assert.equal(result.ignoredStale, true)
    assert.deepEqual(result.selected, ['web3:base:0x' + 'ef'.repeat(20)])
    assert.equal(result.savedSelection, true)
    assert.equal(result.fits, true)
  } finally { await page.close() }
})

test('a real chart switches between Alpha and chain candles and restores the saved chain identity', {
  timeout: 45_000, skip: !process.env.OPENTRADING_TEST_BROWSER,
}, async () => {
  browser ??= await browserSession()
  const page = await browser.page(await browser.context())
  try {
    const result = await page.evaluate(`
      const { ref } = await import('/test/helpers/vuePage.ts');
      const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
      const { createWorkspaceChart } = await import('/src/modules/chartWorkspace/workspaceChart.ts');
      const { OpenTradingProvider } = await import('/src/modules/chartWorkspace/provider.ts');
      const alpha = { id: 'binance:alpha:ALPHA_1USDT', symbol: 'ALPHA_1USDT', name: 'SAME/USDT',
        market: 'alpha', exchange: 'binance', currency: 'USDT', timeframes: ['1m','1h'], timezone: 'Etc/UTC', session: '24x7',
        metadata: { mintick: .01, pricescale: 100, minmove: 1, mincontract: .001, basecurrency: 'SAME' } };
      const address = '0x' + 'ab'.repeat(20), chain = { ...alpha, id: 'web3:bsc:' + address,
        symbol: address, name: 'SAME/USD', market: 'web3', exchange: 'bsc', currency: 'USD' };
      let completeCatalog = false; const keys = [], lookups = [], errors = [];
      chartApi.symbols = async key => { if (key) { lookups.push(key); return [alpha, chain] } return completeCatalog ? [alpha, chain] : [alpha] };
      chartApi.bars = async query => { keys.push(query.symbol); const info = query.symbol === chain.id ? chain : alpha;
        const price = info.market === 'web3' ? 200 : 100, time = Math.floor(Date.now() / 3600000) * 3600000;
        return { symbol: info, timeframe: query.timeframe, source: info.market, bars: [{ time, closeTime: time + 3600000,
          open: price, high: price + 3, low: price - 1, close: price + 1, volume: 10, closed: false }] }; };
      chartApi.cachedBars = () => undefined;
      OpenTradingProvider.prototype.subscribe = () => () => {};
      const host = document.createElement('div'); host.style.cssText = 'width:1000px;height:600px'; document.body.append(host);
      const build = () => createWorkspaceChart({ host: ref(host), theme: ref('dark'), dirty() {}, refreshQuotes() {},
        log() {}, onError: error => errors.push(String(error)) });
      const waitFor = async check => { const until = performance.now() + 5000; while (!check()) {
        if (performance.now() > until) throw Error('Chart did not settle'); await new Promise(resolve => setTimeout(resolve, 10)); } };
      let control = build();
      try {
        control.initialize([alpha]); await waitFor(() => keys.includes(alpha.id));
        await control.selectSymbol(chain.id);
        await waitFor(() => keys.includes(chain.id));
        const switched = control.activeSymbolId.value, state = control.snapshot();
        control.dispose(); control = build(); control.initialize([alpha]); control.restore({ state });
        await waitFor(() => lookups.includes(chain.id) && control.activeSymbol.value?.id === chain.id);
        await control.refreshCatalog();
        return { switched, restored: control.activeSymbolId.value, currency: control.activeSymbol.value.currency, keys, lookups, errors };
      } finally { control.dispose() }
    `)
    const key = 'web3:bsc:0x' + 'ab'.repeat(20)
    assert.equal(result.switched, key)
    assert.equal(result.restored, key)
    assert.equal(result.currency, 'USD')
    assert.ok(result.keys.includes('binance:alpha:ALPHA_1USDT'))
    assert.ok(result.lookups.includes(key))
    assert.deepEqual(result.errors, [])
  } finally { await page.close() }
})
