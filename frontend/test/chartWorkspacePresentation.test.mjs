import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { computed } from 'vue'
import { createI18n } from 'vue-i18n'
import ts from 'typescript'
import { payoffRatio } from '../src/modules/chartWorkspace/metrics.mjs'
import { createMessageTranslator } from '../src/modules/chartWorkspace/messageTranslation.mjs'
import { browserSession } from './helpers/browserSession.mjs'

const zh = JSON.parse(fs.readFileSync(new URL('../src/i18n/zh-CN.json', import.meta.url))).chartWorkspace
const en = JSON.parse(fs.readFileSync(new URL('../src/i18n/en.json', import.meta.url))).chartWorkspace

const load = (path, modules) => {
  const source = fs.readFileSync(new URL('../src/modules/chartWorkspace/' + path, import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(id => modules[id], exports)
  return exports
}

test('default candle bodies remain about 10px wide across chart widths and history depths', () => {
  const { readableCandleRange } = load('chartPresentation.ts', {
    '@luxalgo/vela': { NativeRenderer: class {} }, '@luxalgo/vela/plugin': { registerRendererLayer() {} },
    '@/theme/palette.mjs': {}, './priceAlertLayer': {}, './canvasLocale': {},
  })
  const interval = 15 * 60_000
  const bars = Array.from({ length: 1000 }, (_, index) => ({ time: index * interval }))
  for (const width of [360, 800, 1600, 2400]) {
    const range = readableCandleRange(bars, width)
    const spacing = width / ((range.to - range.from) / interval)
    assert.ok(spacing >= 14 && spacing <= 14.5, `width ${width}: ${spacing}`)
    assert.ok(Math.floor(spacing * 0.7) >= 9, `candle body at width ${width}`)
    assert.equal(range.to, bars.at(-1).time + 6 * interval)
    assert.equal(range.to - range.from, readableCandleRange(bars.slice(-500), width).to - readableCandleRange(bars.slice(-500), width).from)
  }
  assert.equal(readableCandleRange([], 800), null)
  assert.equal(readableCandleRange(bars, 0), null)
})

test('indicator picking follows strokes, gaps, steps and column bounds in the correct pane', () => {
  const { pickIndicator } = load('indicatorInteraction.ts', { '@luxalgo/vela/plugin': { registerRendererLayer() {} } })
  const point = (x, y) => ({ x, y, color: '#2962ff' })
  const line = { id: 'ema', kind: 'line', points: [point(20, 40), point(40, 60), null, point(70, 90), point(90, 100)],
    width: 2, top: 0, bottom: 120, right: 140, base: 120, halfWidth: 4 }
  assert.equal(pickIndicator([line], 30, 52), 'ema')
  assert.equal(pickIndicator([line], 55, 75), null, 'a gap is never a selectable connecting line')
  assert.equal(pickIndicator([line], 30, 85), null)
  assert.equal(pickIndicator([{ ...line, top: 80 }], 30, 50), null)
  const step = { ...line, kind: 'step', points: [point(20, 40), point(40, 80)] }
  assert.equal(pickIndicator([step], 30, 40), 'ema')
  assert.equal(pickIndicator([step], 40, 65), 'ema')
  assert.equal(pickIndicator([step], 30, 60), null, 'step plots do not contain a diagonal segment')
  const volume = { ...line, id: 'volume', kind: 'columns', points: [point(30, 35)], base: 120 }
  assert.equal(pickIndicator([volume], 31, 100), 'volume')
  assert.equal(pickIndicator([volume], 50, 100), null)
  assert.equal(pickIndicator([line, { ...line, id: 'front' }], 30, 50), 'front')
})

test('viewport migration binds the native renderer through the cell host, then preserves saved zoom', () => {
  const handlers = new Map(), host = {}, moves = [], events = new Map()
  let frames = 0
  const native = { hasReadableViewport: true, frameRecentCandles: () => frames++ }
  const { bindWorkspaceRenderer } = load('persistence.ts', {
    '@luxalgo/vela/plugin': { registerStatePersistence(handler) { handlers.set(handler.key, handler) } },
    './pineCompatibility.mjs': {}, './chartPresentation': { WorkspaceRenderer: { forHost: element => element === host ? native : undefined } },
  })
  // Vela's public chart.renderer is a control object, not the native renderer.
  const chart = { renderer: {}, getVisibleRange: () => ({ from: 10, to: 40 }), setVisibleRange: range => moves.push(range),
    on(event, callback) { events.set(event, callback); return () => events.delete(event) } }
  bindWorkspaceRenderer(chart, host)
  const handler = handlers.get('opentrading.viewport'), ctx = { chart }
  handler.restore({ version: 4, range: { from: 0, to: 1000 } }, ctx)
  assert.equal(frames, 1)
  events.get('load:end')()
  assert.equal(frames, 2)
  assert.equal(events.has('load:end'), false)
  const saved = handler.serialize(ctx)
  assert.deepEqual(saved, { version: 5, range: { from: 10, to: 40 } })
  handler.restore(saved, ctx)
  events.get('load:end')()
  assert.equal(frames, 2)
  assert.deepEqual(moves, [saved.range, saved.range])
})

test('historical closed-trade totals distinguish average win/loss from profit factor', () => {
  // Two wins (80 + 20), one loss (-25) and three breakeven trades.
  const summary = Object.freeze({ grossprofit: 100, grossloss: -25, wintrades: 2,
    losstrades: 1, eventrades: 3, profit_factor: 4, openprofit: 9999, commission: 12 })
  assert.equal(payoffRatio(summary), 2)
  assert.equal(summary.profit_factor, 4)
  // Commission is already reflected according to the engine's accounting basis;
  // do not subtract it again or include open P&L / breakeven counts.
  assert.equal(payoffRatio({ ...summary, grossloss: 25 }), 2)
})

test('one-sided trades and missing historical evidence have no observed win/loss ratio', () => {
  for (const summary of [undefined, {},
    { grossprofit: 100, grossloss: 0, wintrades: 2, losstrades: 0 },
    { grossprofit: 0, grossloss: -25, wintrades: 0, losstrades: 1 },
    { grossprofit: 100, grossloss: -25, wintrades: null, losstrades: 1 },
    { grossprofit: Infinity, grossloss: -25, wintrades: 2, losstrades: 1 },
  ]) assert.equal(payoffRatio(summary), null)
})

test('locale switches update labels and saved diagnostics while retaining source details', () => {
  const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': zh, en } })
  const translate = createMessageTranslator([zh, en], (key, params) => i18n.global.t(key, params))
  const display = computed(() => [i18n.global.t('payoffRatio'), translate('原版脚本只读，请另存副本')])
  assert.deepEqual(display.value, ['盈亏比', zh.readonlyCopy])
  i18n.global.locale.value = 'en'
  assert.deepEqual(display.value, ['Average win / loss', en.readonlyCopy])
  assert.equal(translate('Error: 暂不支持 OCA 订单联动（第 8 行，第 3 列）'),
    'OCA order groups are unsupported (line 8, column 3)')
  assert.equal(translate('ETH 不支持 1m 周期'), 'ETH does not support the 1m timeframe')
  assert.equal(translate('脚本编译失败（第 2 行，第 4 列）：Unexpected token "原版"'),
    'Script compilation failed (line 2, column 4): Unexpected token "原版"')
  const log = translate('我的测试 v2 已在 c1 运行')
  assert.equal(log, '我的测试 v2 is running on c1')
  assert.equal(translate('Unknown compiler error: "我的指标"'), 'Unknown compiler error: "我的指标"')
  i18n.global.locale.value = 'zh-CN'
  assert.equal(translate(log), '我的测试 v2 已在 c1 运行')
  assert.deepEqual(display.value, ['盈亏比', zh.readonlyCopy])
})

test('workspace messages compile with matching placeholders in both locales', () => {
  assert.deepEqual(Object.keys(en).sort(), Object.keys(zh).sort())
  const errors = []
  const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': zh, en },
    onError: error => errors.push(error) })
  for (const locale of ['zh-CN', 'en']) {
    i18n.global.locale.value = locale
    for (const [key, message] of Object.entries(locale === 'en' ? en : zh)) {
      const names = [...message.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort()
      const expected = [...zh[key].matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort()
      assert.deepEqual(names, expected, key)
      assert.ok(i18n.global.t(key, Object.fromEntries(names.map(name => [name, 'sample']))))
    }
  }
  assert.deepEqual(errors, [])
})

let session
after(async () => { await session?.close() })
const browserOptions = { timeout: 45_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER }
async function withCharts(body) {
  session ??= await browserSession()
  const page = await session.page(await session.context())
  try {
    return await page.evaluate(`
      const { ref, shallowRef } = await import('/test/helpers/vuePage.ts');
      const { createWorkspaceChart } = await import('/src/modules/chartWorkspace/workspaceChart.ts');
      const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
      const i18n = (await import('/src/i18n/index.ts')).default;
      await import('/src/style.css');
      await import('/src/views/ChartWorkspace.vue');
      i18n.global.locale.value = 'zh-CN';
      const catalog = [
        { id: 'binance:spot:BTCUSDT', symbol: 'BTCUSDT', name: 'BTC/USDT', exchange: 'binance', market: 'spot',
          currency: 'USDT', timezone: 'Etc/UTC', session: '24x7', metadata: { mintick: 0.01 },
          timeframes: ['1m','5m','15m','30m','1h','4h','1d','1w','1M'] },
        { id: 'index:SP500', symbol: 'SP500', name: 'S&P 500', exchange: 'index', market: 'index',
          currency: 'USD', close_only: true, timeframes: ['1d','1w','1M'] },
      ];
      chartApi.bars = async query => {
        const step = { '1m':60000, '5m':300000, '15m':900000, '30m':1800000, '1h':3600000,
          '4h':14400000, '1d':86400000, '1w':604800000, '1M':2592000000 }[query.timeframe];
        const end = Math.floor(Number(query.end ?? Date.now()) / step) * step;
        const count = Number(query.limit ?? 1000);
        return { symbol: catalog.find(item => item.id === query.symbol), timeframe: query.timeframe, source: 'fixture',
          bars: Array.from({ length: count }, (_, index) => ({ time: end - (count - index) * step,
            closeTime: end - (count - index - 1) * step, open: 100 + index % 10, high: 112, low: 98,
            close: 101 + index % 10, volume: 20, closed: true })) };
      };
      const shell = document.createElement('section');
      shell.className = 'chart-workspace cw-dark'; shell.style.cssText = 'width:1280px;height:800px';
      const host = document.createElement('div'); host.className = 'cw-chart'; shell.append(host); document.body.append(shell);
      const errors = [];
      const controller = createWorkspaceChart({ host: shallowRef(host), theme: ref('dark'),
        dirty() {}, refreshQuotes() {}, log() {}, onError: error => errors.push(String(error)) });
      controller.pause(); controller.initialize(catalog); await controller.setLayout('4');
      const workspace = controller.workspace.value;
      const waitFor = async check => { const end = performance.now() + 5000;
        while (!check()) { if (performance.now() > end) throw Error('Chart interaction did not settle');
          await new Promise(resolve => setTimeout(resolve, 20)); } };
      const settle = async () => { await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); };
      const field = id => workspace.cells().find(cell => cell.id === id).host.querySelector('.cw-cell-timeframe');
      const values = () => workspace.cells().map(cell => cell.timeframe);
      const choose = (id, value) => { const select = field(id); select.value = value;
        select.dispatchEvent(new Event('change', { bubbles: true })); };
      try { await waitFor(() => workspace.cells().every(cell => cell.chart.getVisibleRange())); await settle();
        ${body}
      } finally { controller.dispose(); shell.remove(); }
    `)
  } finally { await page.close() }
}

test('each chart title switches its own supported periods and survives layout and locale changes', browserOptions, async () => {
  const result = await withCharts(`
    const ids = workspace.cells().map(cell => cell.id), initial = values();
    const visible = workspace.cells().every(cell => {
      const select = field(cell.id), rect = select.getBoundingClientRect(), bounds = cell.host.getBoundingClientRect();
      return select.options.length === 9 && rect.width > 0 && rect.height >= 24 && rect.right <= bounds.right;
    });
    choose(ids[1], '15'); await waitFor(() => values()[1] === '15'); await settle();
    const independent = values(), active = controller.activeCell.value, period = controller.backendPeriod.value;
    await controller.setPeriod('240'); await settle(); const fromToolbar = field(ids[1]).value;
    await controller.selectSymbol(catalog[1].id); await settle();
    const dailyOnly = [...field(ids[1]).options].map(option => option.value);
    workspace.cells()[1].setTimeframe('1D'); await settle(); const dailyAlias = field(ids[1]).value;
    await controller.setLayout('1'); await controller.setLayout('4'); await settle();
    const restored = { count: host.querySelectorAll('.cw-cell-timeframe').length,
      value: field(ids[1]).value, symbol: workspace.cells().find(cell => cell.id === ids[1]).symbol };
    i18n.global.locale.value = 'en'; await settle();
    const translated = field(ids[1]).options[0].textContent;
    workspace.setActiveCell(ids[1]); controller.setSync('timeframe', true); choose(ids[0], 'W'); await settle();
    return { initial, visible, independent, active, expectedActive: ids[1], period, fromToolbar,
      dailyOnly, dailyAlias, restored, translated,
      synchronized: values().every(value => value === 'W'), errors };
  `)
  assert.deepEqual(result.initial, ['60', '60', '60', '60'])
  assert.equal(result.visible, true)
  assert.deepEqual(result.independent, ['60', '15', '60', '60'])
  assert.equal(result.active, result.expectedActive)
  assert.equal(result.period, '15m')
  assert.equal(result.fromToolbar, '240')
  assert.deepEqual(result.dailyOnly, ['D', 'W', 'M'])
  assert.equal(result.dailyAlias, 'D')
  assert.deepEqual(result.restored, { count: 4, value: 'D', symbol: 'opentrading:index:SP500' })
  assert.equal(result.translated, en.day)
  assert.equal(result.synchronized, true)
  assert.deepEqual(result.errors, [])
})

test('four-chart zoom is independent by default and old layouts migrate while explicit sync persists', browserOptions, async () => {
  const result = await withCharts(`
    const initial = controller.sync.value.viewport;
    const legacy = controller.snapshot(); delete legacy.viewportSyncVersion; legacy.sync.viewport = true;
    controller.restore({ state: legacy }); await settle();
    const migrated = controller.sync.value.viewport;
    const spans = () => workspace.cells().map(cell => cell.chart.getVisibleRange());
    const before = spans(), canvas = [...workspace.cells()[0].host.querySelectorAll('canvas')]
      .find(canvas => getComputedStyle(canvas).pointerEvents !== 'none');
    const rect = canvas.getBoundingClientRect();
    canvas.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: -180,
      clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 }));
    await waitFor(() => JSON.stringify(spans()[0]) !== JSON.stringify(before[0])); await settle();
    const after = spans();
    controller.setSync('viewport', true); const saved = controller.snapshot();
    controller.setSync('viewport', false); controller.restore({ state: saved }); await settle();
    const restoredSync = controller.sync.value.viewport;
    const target = { from: before[0].from + 3600000, to: before[0].to - 3600000 };
    workspace.cells()[0].chart.setVisibleRange(target); await settle();
    const linked = spans();
    return { initial, migrated, zoomed: JSON.stringify(before[0]) !== JSON.stringify(after[0]),
      othersUnchanged: JSON.stringify(before.slice(1)) === JSON.stringify(after.slice(1)),
      restoredSync, followsWhenEnabled: linked.every(range => Math.abs(range.from-linked[0].from) < 2 && Math.abs(range.to-linked[0].to) < 2), errors };
  `)
  assert.equal(result.initial, false)
  assert.equal(result.migrated, false)
  assert.equal(result.zoomed, true)
  assert.equal(result.othersUnchanged, true)
  assert.equal(result.restoredSync, true)
  assert.equal(result.followsWhenEnabled, true)
  assert.deepEqual(result.errors, [])
})
