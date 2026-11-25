import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import * as vue from 'vue'

const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
const rule = () => ({ id: 'A', version: 1, symbol: 'BTC/USDT', name: 'BTC price', metric: 'price', operator: 'crosses', threshold: 100,
  enabled: true, cooldownMinutes: 1, notificationChannels: ['in_app'], configuration: { chartSymbolId: 'binance:spot:BTCUSDT', initialPrice: 90, once: true } })
const replayMatcher = {}
new Function('exports', ts.transpileModule(fs.readFileSync(new URL('../src/modules/chartWorkspace/replayPriceAlerts.ts', import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText)(replayMatcher)
function setup(api = {}, options = {}) {
  global.window = new EventTarget()
  const host = new EventTarget(), writes = [], delivered = [], values = [rule()]
  let quoteCalls = 0
  Object.assign(host, { contains: () => true, getBoundingClientRect: () => ({ top: 0 }), tagName: 'DIV' })
  const renderer = { priceAlerts: { host, hitAt: () => 'A' }, priceAtClient: (_x, y) => 200 - y,
    setPriceAlerts(lines) { this.priceAlerts.alerts = lines; this.priceAlerts.geometry?.({ left: 0, right: 500, top: 0, bottom: 200, lines: lines.map(line => ({ ...line, y: 200 - line.price })) }) } }
  const researchApi = {
    getWorkbench: async () => ({ alerts: values }),
    createAlert: async body => { writes.push({ create: body }); return { ...rule(), ...body, id: 'created', version: 1 } },
    deleteAlert: async (id, version) => { writes.push({ delete: id, version }); return { deleted: true } },
    updateAlert: async (id, body) => { writes.push({ id, ...body }); return { ...rule(), ...body, id, version: 2 } }, ...api,
  }
  const modules = {
    vue, '@luxalgo/vela/plugin': { registerWidgetAction: () => () => {} },
    '@/modules/research/api': { researchApi }, '@/modules/research/alertDelivery': { prepareAlertAudio: async () => true, enableAlertDelivery: options.enableDelivery ?? (async () => {}), deliverAlertEvent: async event => { delivered.push(event) } },
    './chartPresentation': { WorkspaceRenderer: { forHost: () => renderer } }, './api': { chartApi: { quotes: async () => { quoteCalls++; return [{ price: 95 }] } } },
    './replayPriceAlerts': replayMatcher,
    './provider': { fromVela: () => 'binance:spot:BTCUSDT' }, './locale': { cw: key => key, formatNumber: String },
  }
  const code = ts.transpileModule(fs.readFileSync(new URL('../src/modules/chartWorkspace/workspaceAlerts.ts', import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(id => modules[id] ?? (() => { throw Error(id) })(), exports)
  const workspace = vue.shallowRef(), symbols = vue.ref([{ id: 'binance:spot:BTCUSDT', name: 'BTC/USDT', market: 'spot', metadata: { mintick: .01 } }])
  const callbacks = new Set(), start = Date.UTC(2026, 10, 20)
  const replay = options.replay ? { active: vue.ref(true), sessionId: vue.ref('session-1'), cellId: vue.ref('cell'),
    symbol: vue.ref({ id: 'binance:spot:BTCUSDT' }), now: vue.ref(start), account: { price: 90 },
    subscribeSourceBars(callback) { callbacks.add(callback); return () => callbacks.delete(callback) } } : undefined
  const controller = exports.createWorkspaceAlerts({ workspace, symbols, replay })
  const cell = { id: 'cell', host, symbol: 'BTC' }
  workspace.value = { active: cell, cells: () => [cell], context: () => ({ host }), on: () => () => {}, setActiveCell() {} }
  function pointer(target, type, y) {
    const event = new Event(type, { cancelable: true })
    Object.assign(event, { button: 0, isPrimary: true, pointerId: 1, clientX: 150, clientY: y })
    target.dispatchEvent(event)
  }
  function minute(index, prices = {}) {
    const bar = { time: start + index * 60000, closeTime: start + (index + 1) * 60000, open: 90, high: 110, low: 89, close: 90, closed: true, ...prices }
    replay.now.value = bar.closeTime; replay.account.price = bar.close
    for (const cb of callbacks) cb({ sessionId: replay.sessionId.value, symbolId: 'binance:spot:BTCUSDT', bar })
  }
  return { controller, renderer, host, writes, pointer, delivered, replay, minute, quoteCalls: () => quoteCalls }
}

test('dragging previews the price, Escape cancels, and releasing saves only the final price', async () => {
  const { controller: c, renderer, host, writes, pointer } = setup()
  try {
    await flush()
    pointer(host, 'pointerdown', 100); pointer(window, 'pointermove', 120)
    assert.equal(renderer.priceAlerts.alerts[0].price, 80)
    assert.deepEqual(writes, [])
    const escape = new Event('keydown', { cancelable: true }); Object.assign(escape, { key: 'Escape' }); window.dispatchEvent(escape)
    assert.equal(renderer.priceAlerts.alerts[0].price, 100)
    pointer(host, 'pointerdown', 100); pointer(window, 'pointermove', 110); pointer(window, 'pointerup', 110)
    await flush()
    assert.equal(writes.length, 1)
    assert.equal(writes[0].threshold, 90)
    assert.equal(writes[0].configuration.initialPrice, 95)
    assert.equal(c.alerts.value[0].threshold, 90)
  } finally { c.dispose() }
})

test('clicking the line opens its editor; direct deletion removes both the rule and line', async () => {
  const { controller: c, renderer, host, writes, pointer } = setup()
  try {
    await flush()
    pointer(host, 'pointerdown', 100); pointer(window, 'pointerup', 100)
    assert.equal(c.open.value, true)
    assert.equal(c.form.id, 'A')
    c.open.value = false
    await c.remove(c.alerts.value[0])
    assert.deepEqual(writes, [{ delete: 'A', version: 1 }])
    assert.deepEqual(renderer.priceAlerts.alerts, [])
    assert.deepEqual(c.alerts.value, [])
  } finally { c.dispose() }
})

test('a failed move restores the original price and reports the error', async () => {
  const { controller: c, renderer, host, pointer } = setup({ updateAlert: async () => { throw new Error('Save failed') } })
  try {
    await flush()
    pointer(host, 'pointerdown', 100); pointer(window, 'pointermove', 120); pointer(window, 'pointerup', 120)
    await flush()
    assert.equal(c.error.value, 'Save failed')
    assert.equal(renderer.priceAlerts.alerts[0].price, 100)
  } finally { c.dispose() }
})

test('a one-shot trigger removes its chart line immediately, without enabling it for reuse', async () => {
  let triggered = false
  const active = setup({ getWorkbench: async () => ({ alerts: triggered ? [] : [rule()] }) })
  try {
    await flush()
    triggered = true
    window.dispatchEvent(new CustomEvent('opentrading:alert-triggered', { detail: { entityId: 'A' } }))
    assert.deepEqual(active.renderer.priceAlerts.alerts, [])
    await flush()
    assert.deepEqual(active.renderer.priceAlerts.alerts, [])
  } finally { active.controller.dispose() }
})

test('saving a live alert returns to the chart even while desktop permission is pending', async () => {
  const test = setup({}, { enableDelivery: () => new Promise(() => {}) }), c = test.controller
  try {
    await flush(); c.startForm({ symbolId: 'binance:spot:BTCUSDT', price: 100 })
    await c.save()
    assert.equal(c.open.value, false)
    assert.equal(c.editing.value, false)
    assert.equal(test.writes[0].create.configuration.initialPrice, 95)
  } finally { c.dispose() }
})

test('a failed save keeps the alert editor and the entered value available', async () => {
  const { controller: c } = setup({ createAlert: async () => { throw new Error('Save failed') } })
  try {
    await flush(); c.startForm({ symbolId: 'binance:spot:BTCUSDT', price: 100 })
    await c.save()
    assert.equal(c.open.value, true)
    assert.equal(c.editing.value, true)
    assert.equal(c.form.price, '100')
    assert.equal(c.error.value, 'Save failed')
  } finally { c.dispose() }
})

test('a replay wick crossing triggers sound delivery even when both closes stay below the alert', async () => {
  const test = setup({}, { replay: true }), c = test.controller
  try {
    await flush(); c.startForm({ symbolId: 'binance:spot:BTCUSDT', price: 100 })
    await c.save()
    assert.equal(c.open.value, false)
    assert.equal(c.replayMode.value, true)
    assert.equal(c.alerts.value[0].lastValue, 90)
    test.minute(0)
    assert.equal(test.delivered.length, 1)
    assert.ok(test.delivered[0].payload.notificationChannels.includes('sound'))
    assert.equal(test.delivered[0].occurredAt, new Date(test.replay.now.value).toISOString())
    assert.deepEqual(c.alerts.value, [])
    assert.deepEqual(test.renderer.priceAlerts.alerts, [])
    test.minute(1)
    assert.equal(test.delivered.length, 1)
    assert.equal(test.quoteCalls(), 0)
    assert.deepEqual(test.writes, [])
  } finally { c.dispose() }
})

test('repeating replay alerts use replay minutes and do not reuse an old wick on a later candle', async () => {
  const test = setup({}, { replay: true }), c = test.controller
  try {
    await flush(); c.startForm({ symbolId: 'binance:spot:BTCUSDT', price: 100 }); c.form.once = false
    await c.save()
    test.minute(0); test.minute(0)
    assert.equal(test.delivered.length, 1)
    test.minute(1)
    assert.equal(test.delivered.length, 2)
    test.minute(2, { high: 99 })
    assert.equal(test.delivered.length, 2)
    assert.equal(c.alerts.value.length, 1)
    await c.remove(c.alerts.value[0]); test.minute(3)
    assert.equal(test.delivered.length, 2)
    assert.deepEqual(test.writes, [])
  } finally { c.dispose() }
})

test('replay alert baselines ignore candles revealed before creation and stay separate from live rules', async () => {
  const test = setup({}, { replay: true }), c = test.controller
  try {
    await flush(); test.minute(0)
    c.startForm({ symbolId: 'binance:spot:BTCUSDT', price: 100 }); await c.save()
    test.minute(0)
    assert.equal(test.delivered.length, 0)
    test.replay.active.value = false
    assert.equal(c.alerts.value[0].id, 'A')
    test.minute(1)
    assert.equal(test.delivered.length, 0)
    test.replay.sessionId.value = 'session-2'; test.replay.active.value = true
    assert.deepEqual(c.alerts.value, [])
    assert.deepEqual(test.writes, [])
  } finally { c.dispose() }
})

test('replay crossing checks include lower wicks and opening gaps without inventing an intraminute order', () => {
  const matches = replayMatcher.replayPriceAlertMatches
  const bar = { open: 110, high: 112, low: 90, close: 110 }
  assert.equal(matches({ ...rule(), lastValue: 110 }, bar), true)
  assert.equal(matches({ ...rule(), operator: 'crosses_below', lastValue: 110 }, bar), true)
  assert.equal(matches({ ...rule(), lastValue: 90 }, { open: 105, high: 110, low: 104, close: 106 }), true)
  assert.equal(matches({ ...rule(), operator: 'crosses_above', lastValue: 110 }, { open: 110, high: 120, low: 90, close: 95 }), false)
})
