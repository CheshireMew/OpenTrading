import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import test, { after } from 'node:test'
import { browserSession } from './helpers/browserSession.mjs'

// Inputs must be actual HTTP outputs from test_repair_contracts.py, not page-side
// approximations. No browser or fixtures are started by the ordinary unit suite.
const directory = process.env.OPENTRADING_CONTRACT_FIXTURES
const fixture = name => JSON.parse(readFileSync(path.join(directory, name), 'utf8'))
const options = { timeout: 45_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER || !directory }
let session
const browser = async () => session ??= await browserSession()
after(async () => { await session?.close() })
const prepare = `
  const { createApp, nextTick, createRouter, createMemoryHistory } = await import('/test/helpers/vuePage.ts');
  const { default: i18n } = await import('/src/i18n/index.ts'); i18n.global.locale.value = 'en';
  window.waitFor = async predicate => { const deadline = performance.now() + 8000; while (!await predicate()) {
    if (performance.now() > deadline) throw new Error('Page did not consume its HTTP response: ' + document.body.textContent);
    await new Promise(requestAnimationFrame) } await nextTick() };
`;

for (const [scenario, expected] of [['values', ['1.25%', '-2.50%', '0.01%']], ['zero', ['0.00%', '0.00%', '0.00%']], ['missing', ['--', '--', '--']]]) {
  test(`asset page consumes normalized HTTP ${scenario} with the correct percentage units`, options, async () => {
    const instance = await browser(), page = await instance.page(await instance.context())
    const response = fixture(`asset-${scenario}.json`)
    instance.respond('/api/v1/research/assets/ETH%2FUSDT', response)
    try {
      const values = await page.evaluate(`
        ${prepare}
        const { default: Page } = await import('/src/views/research/AssetResearch.vue');
        const router = createRouter({ history: createMemoryHistory(), routes: [{ name: 'AssetResearch', path: '/research/assets/:symbol', component: Page }] });
        await router.push('/research/assets/ETH~USDT'); await router.isReady();
        const app = createApp(Page).use(i18n).use(router); app.mount('#app');
        await waitFor(() => [...document.querySelectorAll('section h2')].some(node => node.textContent === i18n.global.t('assetResearch.marketContext')));
        const heading = [...document.querySelectorAll('section h2')].find(node => node.textContent === i18n.global.t('assetResearch.marketContext'));
        const values = [...heading.parentElement.querySelectorAll('.break-all')].map(node => node.textContent);
        app.unmount(); return values;
      `)
      assert.deepEqual(values, expected)
    } finally { await page.close() }
  })
}

test('DCA page consumes the corrected public tools response and renders the same holdings and cash', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context())
  const data = fixture('dca.json')
  instance.respond('/api/v1/symbols', fixture('symbols.json'))
  instance.respond('/api/v1/tools/contract', fixture('tools-contract.json'))
  instance.respond('/api/v1/tools/dca_simulate', async request => {
    const chunks = []; for await (const chunk of request) chunks.push(chunk)
    const command = JSON.parse(Buffer.concat(chunks).toString())
    for (const key of ['symbol', 'start_date', 'amount', 'investment_time', 'timezone', 'strategy']) assert.equal(command[key], data.command[key], key)
    return data.response
  })
  try {
    const values = await page.evaluate(`
      ${prepare}
      const { setTimezone, setDisplayCurrency } = (await import('/src/composables/useUserPreferences.ts')).useUserPreferences();
      setTimezone('UTC'); setDisplayCurrency('USD');
      const { default: Page } = await import('/src/views/tools/DCA.vue');
      const app = createApp(Page).use(i18n); app.mount('#app');
      await waitFor(() => document.querySelector('form'));
      const change = (selector, value, event = 'input') => { const node = document.querySelector(selector); node.value = value; node.dispatchEvent(new Event(event, { bubbles: true })) };
      change('#dca-amount', input.amount); change('input[type=date]', input.start_date);
      change('#dca-strategy', input.strategy, 'change'); change('#dca-investment-time', input.investment_time, 'change');
      await nextTick(); document.querySelector('form').requestSubmit();
      await waitFor(() => document.querySelectorAll('.dca-output-values dd').length === 6);
      const values = [...document.querySelectorAll('.dca-output-values dd')].map(node => Number(node.textContent.replace(/[^0-9.-]/g, '')));
      app.unmount(); return values;
    `, data.command)
    assert.equal(values[1], data.response.final_value)
    assert.equal(values[2], data.response.total_invested)
    assert.equal(values[4], data.response.total_coins)
    assert.equal(values[5], data.response.total_days)
  } finally { await page.close() }
})

test('data health page consumes the measured archive summary through its public HTTP contract', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context()), response = fixture('health.json')
  instance.respond('/api/v1/data-health', response)
  try {
    const values = await page.evaluate(`
      ${prepare}
      const { default: Page } = await import('/src/views/system/DataHealth.vue');
      const app = createApp(Page).use(i18n); app.mount('#app');
      await waitFor(() => [...document.querySelectorAll('.health-source dd')].some(node => node.textContent.replace(/,/g, '') === '20000'));
      const article = [...document.querySelectorAll('.health-source')].find(node => [...node.querySelectorAll('dd')].some(value => value.textContent.replace(/,/g, '') === '20000'));
      const field = key => [...article.querySelectorAll('dl>div')].find(node => node.querySelector('dt').textContent === i18n.global.t('dataHealth.' + key)).querySelector('dd').textContent;
      const result = { records: Number(field('records').replace(/,/g, '')), gaps: Number(field('gaps')) };
      app.unmount(); return result;
    `)
    const source = response.sources.find(row => row.id === 'klines')
    assert.deepEqual(values, { records: source.recordCount, gaps: source.gapCount })
  } finally { await page.close() }
})

test('data health form accepts 1000 hourly days and displays the actual remaining repair gaps', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context()), response = fixture('health-repair-partial.json')
  instance.respond('/api/v1/data-health', fixture('health.json'))
  instance.respond('/api/v1/data-health/repair', async request => {
    const chunks = []; for await (const chunk of request) chunks.push(chunk)
    const command = JSON.parse(Buffer.concat(chunks).toString())
    assert.equal(command.days, 1000); assert.equal(command.timeframe, '1h')
    return response
  })
  try {
    const result = await page.evaluate(`
      ${prepare}
      const { default: Page } = await import('/src/views/system/DataHealth.vue');
      const app = createApp(Page).use(i18n); app.mount('#app');
      await waitFor(() => document.querySelector('.health-history-form') && !document.querySelector('[role=status]'));
      const days = document.querySelector('.health-history-form input[type=number]'); days.value = '1000';
      days.dispatchEvent(new Event('input', { bubbles: true })); await nextTick();
      document.querySelector('.health-history-form').requestSubmit();
      const expected = i18n.global.t('dataHealth.historyPartial', { symbol: input.result.symbol, count: input.result.pointCount });
      await nextTick();
      await waitFor(() => document.querySelector('[role=status]')?.textContent === expected && !document.querySelector('.health-history-form button').disabled);
      const result = { feedback: document.querySelector('[role=status]').textContent, expected,
        gaps: document.querySelector('[aria-live=polite] li')?.textContent, error: document.querySelector('[role=alert]')?.textContent ?? '' };
      app.unmount(); return result;
    `, response)
    assert.equal(result.feedback, result.expected)
    assert.match(result.gaps, new RegExp(response.coverage.startDate.slice(0, 4)))
    assert.equal(result.error, '')
  } finally { await page.close() }
})

test('both tools finish a real HTTP response slower than the ordinary 15 second timeout', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context())
  const slow = async () => { await new Promise(resolve => setTimeout(resolve, 16_000)); return { ok: true } }
  instance.respond('/api/v1/tools/dca_simulate', slow)
  instance.respond('/api/v1/tools/compare_pairs', slow)
  try {
    await page.evaluate(`
      const { toolsApi } = await import('/src/modules/tools/api.ts');
      window.slowResults = [];
      for (const task of [toolsApi.runSimulation({}), toolsApi.comparePairs({})])
        task.then(value => slowResults.push(value), error => slowResults.push({ error: error.message }));
    `)
    await new Promise(resolve => setTimeout(resolve, 16_500))
    assert.deepEqual(await page.evaluate('return window.slowResults'), [{ ok: true }, { ok: true }])
  } finally { await page.close() }
})
