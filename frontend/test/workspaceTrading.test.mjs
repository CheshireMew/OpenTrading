import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import * as vue from 'vue'

function loader(boundaries = {}) {
  const cache = new Map()
  function load(name) {
    if (cache.has(name)) return cache.get(name)
    const exports = {}; cache.set(name, exports)
    const code = ts.transpileModule(fs.readFileSync(new URL('../src/modules/chartWorkspace/' + name + '.ts', import.meta.url), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
    new Function('require', 'exports', code)(id => boundaries[id] ?? (id === 'vue' ? vue : id === './locale' ? { cw: key => key, formatNumber: String } :
      id.startsWith('./') ? load(id.slice(2)) : (() => { throw Error(id) })()), exports)
    return exports
  }
  return load
}

function trading(load) {
  const { ReplayAccount } = load('replayModel')
  const symbol = { id: 'BTC', currency: 'USDT', metadata: { mincontract: 0.01, basecurrency: 'BTC' } }
  function target(active) {
    const account = vue.reactive(new ReplayAccount())
    account.quote(100, 1)
    return { account, active: vue.ref(active), loading: vue.ref(false), error: vue.ref(''), symbol: vue.ref(symbol), timeframe: vue.ref('1m'),
      roundedPrice: value => value, chart: undefined }
  }
  const replay = { ...target(true), now: vue.ref(2), place: (side, kind, price) => replay.account.place(side, kind, price, 1, replay.now.value) }
  let paperCalls = 0, cancelled = 0
  const paper = { ...target(true), place: async (side, kind, price) => { paperCalls++; return paper.account.place(side, kind, price, 2, 3) } }
  const selected = vue.computed(() => replay.active.value ? replay : paper)
  const orders = load('workspaceTradingOrders').createWorkspaceTradingOrders({ target: selected, replay, paper: () => paper, beforeChange: () => { cancelled++ } })
  return { replay, paper, selected, orders, paperCalls: () => paperCalls, cancelled: () => cancelled }
}

test('trading commands select the active account and validate partial exits before committing edits', async () => {
  const state = trading(loader()), { orders, replay, paper } = state
  try {
    await orders.place(1, 'market')
    assert.equal(replay.account.position.quantity, 1)
    assert.equal(state.paperCalls(), 0)
    orders.openMenu(110, 30); orders.menu.value.quantity = 2
    orders.submitExitAt()
    assert.equal(orders.menuError.value, 'replayInvalidSize')
    assert.equal(replay.account.position.exits.length, 0)
    orders.menu.value.quantity = 0.5; orders.submitExitAt()
    assert.equal(replay.account.position.exits.length, 1)
    const exit = replay.account.position.exits[0]
    orders.openEditor(exit.target, exit.price)
    orders.editQuantity.value = 2; orders.applyPrice()
    assert.equal(orders.editError.value, 'replayInvalidSize')
    assert.equal(exit.quantity, 0.5)
    replay.active.value = false
    await vue.nextTick()
    assert.equal(orders.editing.value, undefined)
    assert.equal(orders.menu.value, undefined)
    await orders.place(-1, 'market')
    assert.equal(state.paperCalls(), 1)
    assert.equal(paper.account.position.quantity, 2)
    assert.equal(replay.account.position.quantity, 1)
    orders.remove('entry')
    assert.equal(paper.account.position, undefined)
    assert.ok(state.cancelled() > 0)
  } finally { orders.dispose() }
})

test('chart trading drag commits through the order controller and releases chart marks and menus', async () => {
  global.window = new EventTarget()
  const renderers = new Map(), actions = new Set()
  const load = loader({
    '@luxalgo/vela/plugin': { registerWidgetAction: action => { actions.add(action); return () => actions.delete(action) } },
    './chartPresentation': { WorkspaceRenderer: { forHost: host => renderers.get(host) } }, './provider': { fromVela: value => value },
  })
  const state = trading(load), { orders, replay, paper, selected } = state
  const host = new EventTarget()
  Object.assign(host, { contains: () => true, getBoundingClientRect: () => ({ top: 0, left: 0 }) })
  const marks = () => { const values = new Map(); return { values, add: mark => values.set(mark.id, mark), remove: id => values.delete(id) } }
  replay.chart = { marks: marks() }; paper.chart = { marks: marks() }
  const renderer = { replayOrders: { host, pointAt: (_x, y) => ({ price: y, time: 1 }) }, getConfig: () => ({ timeScale: { timezone: 'UTC' } }),
    setReplayOrders(value) { this.value = value } }
  renderers.set(host, renderer)
  const workspace = vue.shallowRef({ active: { chart: replay.chart, host, symbol: 'BTC' }, cells: () => [], context: () => ({ host }), on: () => () => {} })
  const interaction = load('workspaceTradingInteraction').createWorkspaceTradingInteraction({ workspace: () => workspace.value, replay, target: selected, orders, picked() {} })
  try {
    await orders.place(1, 'market')
    orders.addExit(110)
    await vue.nextTick()
    const exit = replay.account.position.exits[0]
    interaction.beginDrag({ button: 0, preventDefault() {}, stopPropagation() {} }, exit.target)
    const move = new Event('pointermove'); Object.assign(move, { clientX: 0, clientY: 120 }); window.dispatchEvent(move)
    window.dispatchEvent(new Event('pointerup'))
    assert.equal(exit.price, 120)
    await vue.nextTick()
    assert.ok(replay.chart.marks.values.has('replay-open'))
    replay.active.value = false
    await vue.nextTick()
    assert.equal(replay.chart.marks.values.size, 0)
    assert.ok(actions.size > 0)
  } finally { interaction.dispose(); orders.dispose() }
  assert.equal(actions.size, 0)
  assert.equal(paper.chart.marks.values.size, 0)
  assert.deepEqual(renderer.value.lines, [])
})

test('playback navigation ignores hidden pages and date dialogs and removes its keyboard listener', () => {
  const previousElement = global.Element, previousDocument = global.document
  global.window = new EventTarget(); global.Element = class {}; global.document = { hidden: false, querySelectorAll: () => [] }
  let deactivate, unmount, prepared = 0
  const hooks = { ...vue, onMounted: fn => fn(), onActivated() {}, onDeactivated: fn => { deactivate = fn }, onBeforeUnmount: fn => { unmount = fn } }
  const load = loader({ vue: hooks })
  const replay = { open: vue.ref(true), active: vue.ref(true), ended: vue.ref(false), loading: vue.ref(false), playing: vue.ref(false),
    picking: vue.ref(false), now: vue.ref(Date.UTC(2026, 10, 20)), error: vue.ref(''),
    play() { this.playing.value = true }, pause() { this.playing.value = false } }
  const navigation = load('workspaceReplayNavigation').useWorkspaceReplayNavigation({ replay, workspace: () => ({ context: () => ({ host: { getClientRects: () => [1] } }) }),
    timeZone: vue.ref('UTC'), prepare: () => { prepared++ } })
  const press = () => { const event = new Event('keydown', { cancelable: true }); Object.assign(event, { key: ' ', code: 'Space' }); window.dispatchEvent(event); return event }
  try {
    assert.equal(press().defaultPrevented, true)
    assert.equal(replay.playing.value, true)
    navigation.showDate()
    assert.equal(prepared, 1)
    assert.equal(replay.playing.value, false)
    assert.equal(press().defaultPrevented, false)
    navigation.picked(); deactivate()
    assert.equal(press().defaultPrevented, false)
    unmount(); navigation.pageActive.value = true
    assert.equal(press().defaultPrevented, false)
  } finally { unmount(); global.Element = previousElement; global.document = previousDocument }
})
