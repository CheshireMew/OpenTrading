import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import * as vue from 'vue'

const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
const rule = () => ({ id: 'A', version: 1, symbol: 'BTC/USDT', name: 'BTC price', metric: 'price', operator: 'crosses', threshold: 100,
  enabled: true, cooldownMinutes: 1, notificationChannels: ['in_app'], configuration: { chartSymbolId: 'binance:spot:BTCUSDT', initialPrice: 90, once: true } })
function setup(api = {}) {
  global.window = new EventTarget()
  const host = new EventTarget(), writes = [], values = [rule()]
  Object.assign(host, { contains: () => true, getBoundingClientRect: () => ({ top: 0 }), tagName: 'DIV' })
  const renderer = { priceAlerts: { host, hitAt: () => 'A' }, priceAtClient: (_x, y) => 200 - y,
    setPriceAlerts(lines) { this.priceAlerts.alerts = lines; this.priceAlerts.geometry?.({ left: 0, right: 500, top: 0, bottom: 200, lines: lines.map(line => ({ ...line, y: 200 - line.price })) }) } }
  const researchApi = {
    getWorkbench: async () => ({ alerts: values }),
    deleteAlert: async (id, version) => { writes.push({ delete: id, version }); return { deleted: true } },
    updateAlert: async (id, body) => { writes.push({ id, ...body }); return { ...rule(), ...body, id, version: 2 } }, ...api,
  }
  const modules = {
    vue, '@luxalgo/vela/plugin': { registerWidgetAction: () => () => {} },
    '@/modules/research/api': { researchApi }, '@/modules/research/alertDelivery': { prepareAlertAudio: async () => true, enableAlertDelivery: async () => {} },
    './chartPresentation': { WorkspaceRenderer: { forHost: () => renderer } }, './api': { chartApi: { quotes: async () => [{ price: 95 }] } },
    './provider': { fromVela: () => 'binance:spot:BTCUSDT' }, './locale': { cw: key => key, formatNumber: String },
  }
  const code = ts.transpileModule(fs.readFileSync(new URL('../src/modules/chartWorkspace/workspaceAlerts.ts', import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(id => modules[id] ?? (() => { throw Error(id) })(), exports)
  const workspace = vue.shallowRef(), symbols = vue.ref([{ id: 'binance:spot:BTCUSDT', name: 'BTC/USDT', market: 'spot', metadata: { mintick: .01 } }])
  const controller = exports.createWorkspaceAlerts({ workspace, symbols })
  const cell = { id: 'cell', host, symbol: 'BTC' }
  workspace.value = { cells: () => [cell], context: () => ({ host }), on: () => () => {}, setActiveCell() {} }
  function pointer(target, type, y) {
    const event = new Event(type, { cancelable: true })
    Object.assign(event, { button: 0, isPrimary: true, pointerId: 1, clientX: 150, clientY: y })
    target.dispatchEvent(event)
  }
  return { controller, renderer, host, writes, pointer }
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
