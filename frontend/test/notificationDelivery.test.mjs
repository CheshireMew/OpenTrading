import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { browserSession } from './helpers/browserSession.mjs'

let session
after(async () => { await session?.close() })
const options = { timeout: 45_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER }
const mount = `
  const { createApp, h } = await import('/test/helpers/vuePage.ts');
  const { useDesktopAlertNotifications } = await import('/src/modules/research/useDesktopAlertNotifications.ts');
  const { researchApi } = await import('/src/modules/research/api.ts');
  window.delivered = []; window.reads = 0;
  window.addEventListener('opentrading:alert-triggered', event => delivered.push(event.detail.id));
  const list = researchApi.listEvents;
  researchApi.listEvents = async (...args) => { const page = await list(...args); reads++; return page };
  window.app = createApp({ setup() { useDesktopAlertNotifications(); return () => h('div') } }); app.mount('#app');
  const deadline = performance.now() + 5000;
  while (!reads) { if (performance.now() > deadline) throw new Error('Notification poll did not start'); await new Promise(requestAnimationFrame) }
  await navigator.locks.request('opentrading:alert-delivery', () => {});
`;

test('notification delivery drains more than one batch and stays deduplicated after reopening', options, async () => {
  session = await browserSession()
  const context = await session.context()
  let page = await session.page(context)
  const first = await page.evaluate(`
    const { createBrowserResearchApi, evaluateBrowserAlerts } = await import('/src/modules/research/browserResearch.ts');
    const api = createBrowserResearchApi({});
    for (let i = 0; i < 605; i++) await api.createAlert({ symbol: 'BTC/USDT', name: 'Backlog ' + i,
      metric: 'price', operator: 'gt', threshold: 100, notificationChannels: ['in_app'], configuration: { once: true } });
    const original = window.fetch;
    window.fetch = (url, init) => String(url).includes('/observations?')
      ? Promise.resolve(new Response(JSON.stringify({ BTCUSDT: { price: 200 } }))) : original(url, init);
    const produced = await evaluateBrowserAlerts();
    if (produced.triggeredCount !== 605) throw new Error('Trigger fixture is incomplete');
    ${mount}
    // One poll is bounded; further focus polls must eventually reach the tail.
    for (let i = 0; i < 3; i++) { window.dispatchEvent(new Event('focus')); await navigator.locks.request('opentrading:alert-delivery', () => {}) }
    app.unmount();
    return { delivered: delivered.length, unique: new Set(delivered).size, pending: (await api.listEvents('alert_triggered', true, 500)).total };
  `)
  assert.deepEqual(first, { delivered: 605, unique: 605, pending: 605 })
  await page.close()
  page = await session.page(context)
  const reopened = await page.evaluate(`
    ${mount}
    for (let i = 0; i < 3; i++) { window.dispatchEvent(new Event('focus')); await navigator.locks.request('opentrading:alert-delivery', () => {}) }
    app.unmount(); return delivered.length;
  `)
  assert.equal(reopened, 0)
  await page.close()
})

for (const failure of ['state', 'delivered', 'commit']) {
  test(`notifications still deliver once when receipt ${failure} storage fails`, options, async () => {
    session ??= await browserSession()
    const page = await session.page(await session.context())
    try {
      const result = await page.evaluate(`
        const { browserNotificationStore } = await import('/src/modules/personal/browserStore.ts');
        browserNotificationStore[input] = async () => { throw new DOMException('Storage is full', 'QuotaExceededError') };
        const { researchApi: api } = await import('/src/modules/research/api.ts');
        api.listEvents = async () => ({ items: [{ id: 'storage-fallback', entityType: 'alert', entityId: 'storage-rule',
          symbol: 'BTC/USDT', kind: 'alert_triggered', title: 'Stored alert', body: '', occurredAt: new Date().toISOString(),
          createdAt: new Date().toISOString(), payload: { notificationChannels: ['in_app'] } }], total: 1, nextCursor: null });
        ${mount}
        for (let i = 0; i < 2; i++) {
          window.dispatchEvent(new Event('focus'));
          await navigator.locks.request('opentrading:alert-delivery', () => {});
        }
        app.unmount();
        return delivered;
      `, failure)
      assert.deepEqual(result, ['storage-fallback'])
    } finally { await page.close() }
  })
}
