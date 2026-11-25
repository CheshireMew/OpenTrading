import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import test, { after } from 'node:test'
import { browserSession } from './helpers/browserSession.mjs'

let session
const browser = async () => session ??= await browserSession()
after(async () => { await session?.close() })
const options = { timeout: 45_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER }
const prepare = `
  const { createApp, nextTick } = await import('/test/helpers/vuePage.ts');
  const { default: i18n } = await import('/src/i18n/index.ts'); i18n.global.locale.value = 'en';
  const { default: Tester } = await import('/src/components/chartWorkspace/StrategyTester.vue');
  window.waitFor = async predicate => { const deadline = performance.now() + 8000; while (!await predicate()) {
    if (performance.now() > deadline) throw new Error('Pine consumer did not settle: ' + document.body.textContent);
    await new Promise(requestAnimationFrame) } await nextTick() };
  window.mount = () => { const app = createApp(Tester, { timeframe: '1m', dark: false }).use(i18n); app.mount('#app'); return app };
`;
const request = { script_id: 'progress', script_version: 1, script_source: '//@version=6\nstrategy("Progress")\nplot(close)',
  symbol: 'binance:spot:BTCUSDT', timeframe: '1m', start: Date.UTC(2026, 0, 1), end: Date.UTC(2026, 0, 1) + 4001 * 60000, inputs: {}, props: {} }

test('Pine admission releases failed writes and remote cancellation releases the actual owner', options, async () => {
  const instance = await browser(), context = await instance.context(), page = await instance.page(context), other = await instance.page(context)
  try {
    const result = await page.evaluate(`
      window.pine = (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns;
      window.owned = [];
      const original = IDBObjectStore.prototype.put;
      IDBObjectStore.prototype.put = function(...args) { if (this.name === 'pine-runs') throw new DOMException('Quota', 'QuotaExceededError'); return original.apply(this, args) };
      let rejected = false; try { await pine.run(input) } catch { rejected = true } finally { IDBObjectStore.prototype.put = original }
      window.fetch = async () => new Response('Controlled history failure', { status: 503 });
      const failed = await pine.run(input);
      const deadline = performance.now() + 5000;
      while ((await pine.getRun(failed.id)).status !== 'failed') { if (performance.now() > deadline) throw new Error('History failure did not terminate'); await new Promise(resolve => setTimeout(resolve, 0)) }
      await navigator.locks.request('pine-run:' + failed.id, () => {});
      window.fetch = (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError'))));
      owned = (await Promise.all([pine.run(input), pine.run(input)])).map(run => run.id);
      let third = false; try { await pine.run(input) } catch { third = true }
      return { rejected, accepted: owned.length, third, id: owned[0] };
    `, request)
    assert.deepEqual({ ...result, id: undefined }, { rejected: true, accepted: 2, third: true, id: undefined })
    const cancelled = await other.evaluate(`return (await (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns.cancel(input)).status;`, result.id)
    assert.equal(cancelled, 'cancelled')
    const replacement = await page.evaluate(`const run = await pine.run(input); owned.push(run.id); return run.status;`, request)
    assert.equal(replacement, 'loading')
  } finally {
    await page.evaluate(`await Promise.allSettled((window.owned ?? []).map(id => window.pine.cancel(id)));`)
    await page.close(); await other.close()
  }
})

test('browser tester cancellation clears phase progress after the real fetch stops', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context())
  try {
    const result = await page.evaluate(`
      ${prepare}
      const pine = (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns;
      window.stopped = false;
      window.fetch = (_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => { stopped = true; reject(new DOMException('Cancelled', 'AbortError')) }));
      const run = await pine.run(input), app = mount();
      await waitFor(() => document.querySelector('.run-status progress'));
      [...document.querySelectorAll('.tester-controls button')].find(node => node.textContent === 'Cancel').click();
      await waitFor(() => document.querySelector('.run-status')?.textContent.includes('Cancelled'));
      const result = { stopped, progress: !!document.querySelector('.run-status progress'), status: (await pine.getRun(run.id)).status };
      app.unmount(); return result;
    `, request)
    assert.deepEqual(result, { stopped: true, progress: false, status: 'cancelled' })
  } finally { await page.close() }
})

test('remote cancellation reaches a persisted Pine run before submission returns', options, async () => {
  const instance = await browser(), context = await instance.context(), page = await instance.page(context), other = await instance.page(context)
  try {
    const id = await page.evaluate(`
      const NativeChannel = BroadcastChannel;
      window.BroadcastChannel = class extends NativeChannel { constructor(name) { super(name); this.addEventListener('message', () => { window.signalSeen = true }) } };
      const { browserPineStore } = await import('/src/modules/personal/browserStore.ts');
      window.pine = (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns;
      const update = browserPineStore.update; window.writes = [];
      browserPineStore.update = async (...args) => { writes.push('begin'); const value = await update(...args); writes.push(value.run.status); if (!window.pendingId) {
        window.pendingId = value.run.id; await new Promise(resolve => { window.releaseAdmission = resolve });
      } return value };
      window.admission = pine.run(input); admission.catch(() => {});
      const deadline = performance.now() + 5000;
      while (!window.pendingId) { if (performance.now() > deadline) throw new Error('Run was never persisted'); await new Promise(resolve => setTimeout(resolve, 0)) }
      return pendingId;
    `, request)
    await other.evaluate(`window.remote = (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns.cancel(input); remote.catch(() => {});`, id)
    const status = await page.evaluate(`
      const deadline = performance.now() + 5000;
      while (!window.signalSeen) { if (performance.now() > deadline) throw new Error('Early cancellation never reached the owner'); await new Promise(resolve => setTimeout(resolve, 0)) }
      releaseAdmission();
      return await Promise.race([admission.then(run => run.status), new Promise(resolve => setTimeout(async () => resolve({ writes, locks: await navigator.locks.query() }), 5000))]);
    `)
    assert.equal(status, 'cancelled')
    assert.equal(await other.evaluate(`return (await remote).status;`), 'cancelled')
  } finally {
    await page.evaluate(`window.releaseAdmission?.(); await Promise.race([window.admission?.catch(() => {}), new Promise(resolve => setTimeout(resolve, 1000))]);`)
    await page.close(); await other.close()
  }
})

test('actual browser Pine progress reaches the tester as phase work and ends with a usable report', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context())
  try {
    const values = await page.evaluate(`
      ${prepare}
      const pine = (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns;
      const bars = Array.from({ length: 4001 }, (_, i) => ({ time: input.start + i * 60000, closeTime: input.start + (i + 1) * 60000, open: 100, high: 101, low: 99, close: 100, volume: 1, closed: true }));
      const symbol = { id: input.symbol, symbol: 'BTCUSDT', name: 'BTC/USDT', exchange: 'binance', market: 'spot', currency: 'USDT', timezone: 'Etc/UTC', session: '24x7', close_only: false, metadata: {}, timeframes: ['1m'] };
      let allowMarket; const marketGate = new Promise(resolve => { allowMarket = resolve });
      const originalFetch = fetch;
      window.fetch = async (url, init) => {
        if (!String(url).includes('/chart-workspace/bars?')) return originalFetch(url, init);
        await marketGate;
        if (init.signal.aborted) throw new DOMException('Cancelled', 'AbortError');
        const start = Number(new URL(url, location.origin).searchParams.get('start'));
        return new Response(JSON.stringify({ symbol, bars: bars.filter(bar => bar.time >= start).slice(0, 1000), timeframe: '1m', source: 'controlled-exchange' }));
      };
      // Hold transport after a real counted producer update. The worker still
      // computes normally; queued messages retain their original order/payloads.
      let release; window.producerGate = new Promise(resolve => { release = resolve });
      const NativeWorker = Worker;
      window.Worker = class extends NativeWorker {
        set onmessage(consumer) { let chain = Promise.resolve(); super.onmessage = event => {
          chain = chain.then(async () => { await consumer.call(this, event);
            if (event.data.type === 'progress' && event.data.value.progress.mode === 'measured' && !window.firstFrame) {
              window.firstFrame = event.data.value; await producerGate;
            }
          });
        } }
      };
      const run = await pine.run(input), app = mount();
      await waitFor(() => document.querySelector('.run-status progress'));
      const loading = { status: (await pine.getRun(run.id)).status, measured: document.querySelector('progress').hasAttribute('value'), percent: document.querySelector('.run-status').textContent.includes('%') };
      allowMarket();
      await waitFor(() => document.querySelector('.run-status progress')?.hasAttribute('value'));
      const measured = { frame: firstFrame, value: Number(document.querySelector('progress').getAttribute('value')), text: document.querySelector('.run-status').textContent };
      release();
      await waitFor(() => document.querySelector('.tester-result'));
      const completed = { status: (await pine.getRun(run.id)).status, progress: !!document.querySelector('.run-status progress'), total: (await pine.records(run.id, 'equity', 3999, 2)).total };
      app.unmount(); return { loading, measured, completed };
    `, request)
    assert.deepEqual(values.loading, { status: 'loading', measured: false, percent: false })
    assert.equal(values.measured.frame.progress.total, 4001)
    assert.equal(values.measured.frame.progress.unit, 'candles')
    assert.equal(values.measured.value, values.measured.frame.progress.completed / 4001 * 100)
    assert.match(values.measured.text, /Computing strategy/)
    assert.deepEqual(values.completed, { status: 'completed', progress: false, total: 4001 })
  } finally { await page.close() }
})

test('server Pine HTTP outputs use the same tester stages, cancellation and terminal presentation', {
  ...options, skip: options.skip || !process.env.OPENTRADING_CONTRACT_FIXTURES,
}, async () => {
  await session?.close(); session = await browserSession({ publicSite: false })
  const fixture = name => JSON.parse(readFileSync(path.join(process.env.OPENTRADING_CONTRACT_FIXTURES, name), 'utf8'))
  let current = fixture('pine-loading.json')
  session.respond('/api/v1/chart-workspace/pine-runs', () => [current])
  session.respond('/api/v1/chart-workspace/pine-runs/' + current.id, () => current)
  session.respond('/api/v1/chart-workspace/pine-runs/' + current.id + '/cancel', () => current = fixture('pine-cancelled.json'))
  let page = await session.page(await session.context())
  try {
    const cancelled = await page.evaluate(`
      ${prepare}
      const app = mount(); await waitFor(() => document.querySelector('.run-status progress'));
      const measured = document.querySelector('progress').hasAttribute('value');
      [...document.querySelectorAll('.tester-controls button')].find(node => node.textContent === 'Cancel').click();
      await waitFor(() => document.querySelector('.run-status')?.textContent.includes('Cancelled'));
      const result = { measured, progress: !!document.querySelector('.run-status progress') }; app.unmount(); return result;
    `)
    assert.deepEqual(cancelled, { measured: false, progress: false })
    await page.close()
    current = fixture('pine-saving.json')
    session.respond('/api/v1/chart-workspace/pine-runs/' + current.id, () => current)
    session.respond('/api/v1/chart-workspace/pine-runs/' + current.id + '/records', fixture('pine-equity.json'))
    page = await session.page(await session.context())
    const saving = await page.evaluate(`
      ${prepare}
      window.app = mount(); await waitFor(() => document.querySelector('.run-status')?.textContent.includes('Saving report'));
      return { measured: document.querySelector('progress').hasAttribute('value'), percent: document.querySelector('.run-status').textContent.includes('%') };
    `)
    assert.deepEqual(saving, { measured: false, percent: false })
    current = fixture('pine-completed.json')
    const completed = await page.evaluate(`await waitFor(() => document.querySelector('.tester-result')); const result = !document.querySelector('.run-status progress'); app.unmount(); return result;`)
    assert.equal(completed, true)
  } finally { await page.close() }
})
