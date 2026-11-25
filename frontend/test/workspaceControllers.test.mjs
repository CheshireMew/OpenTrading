import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'

const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
const tick = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() }
function load(name, modules) {
  const exports = {}
  const code = ts.transpileModule(fs.readFileSync(new URL('../src/modules/chartWorkspace/' + name + '.ts', import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  new Function('require', 'exports', code)(id => id === 'vue' ? vue : id === './locale' ? { cw: key => key } :
    id in modules ? modules[id] : (() => { throw Error('Missing test boundary: ' + id) })(), exports)
  return exports
}

test('all registered pages retain independent state across navigation and dispose on app exit', async () => {
  const navigation = load('../../app/navigation', {
    '@/modules/market/macroSections': { MACRO_SECTIONS: [], preferredMacroSection: () => ({ name: 'MacroDollarLiquidity' }) },
    './publicSite': { PUBLIC_SITE: true },
  })
  const componentName = fs.readFileSync(new URL('../src/views/ChartWorkspace.vue', import.meta.url), 'utf8')
    .match(/defineOptions\(\{\s*name:\s*'([^']+)'/)[1]
  const node = () => ({ children: [], parent: null })
  const remove = child => {
    if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1)
    child.parent = null
  }
  const { render } = vue.createRenderer({
    createElement: node, createText: node, createComment: node,
    insert(child, parent, anchor) { remove(child); child.parent = parent; const at = parent.children.indexOf(anchor); parent.children.splice(at < 0 ? parent.children.length : at, 0, child) },
    remove, parentNode: child => child.parent,
    nextSibling: child => child.parent?.children[child.parent.children.indexOf(child) + 1],
    patchProp() {}, setText() {}, setElementText() {},
  })
  const pages = navigation.APP_ROUTE_DEFINITIONS.filter(route => 'component' in route)
  const mounts = new Map(), states = new Map()
  let unmounts = 0
  const components = new Map(pages.map(route => [route.name, {
    name: route.name === 'Dashboard' ? componentName : route.name,
    setup() {
      mounts.set(route.name, (mounts.get(route.name) ?? 0) + 1)
      const state = vue.ref('initial'); states.set(route.name, state)
      vue.onUnmounted(() => unmounts++)
      return () => vue.h('div', state.value)
    },
  }]))
  const selected = vue.ref(pages[0].name), host = node()
  render(vue.h({ setup: () => () => vue.h(vue.KeepAlive, { max: navigation.APP_PAGE_CACHE_LIMIT }, { default: () => vue.h(components.get(selected.value), { key: selected.value }) }) }), host)
  try {
    for (const page of pages) {
      selected.value = page.name; await vue.nextTick()
      states.get(page.name).value = 'edited:' + page.name
    }
    for (const page of [...pages].reverse()) {
      selected.value = page.name; await vue.nextTick()
      assert.equal(states.get(page.name).value, 'edited:' + page.name)
      assert.equal(mounts.get(page.name), 1)
    }
    assert.equal(unmounts, 0)
  } finally { render(null, host) }
  assert.equal(unmounts, pages.length)
})
function documents({ api = {}, drafts = {} } = {}) {
  const errors = [], writes = []
  const { createPineDocuments } = load('pineDocuments', {
    './api': { chartApi: api },
    './drafts': { deleteDraft:async()=>{}, readDraft: async () => undefined, writeDraft: async (key, value) => writes.push({ key, ...value }), ...drafts },
  })
  const controller = createPineDocuments({ requestName: async () => 'copy', openEditor() {}, onError: error => errors.push(error) })
  return { controller, errors, writes }
}
const A = () => ({ id: 'A', name: 'A', version: 1, data: { source: 'A' } })
const B = () => ({ id: 'B', name: 'B', version: 1, data: { source: 'B' } })

function indicatorWorkspace() {
  const emitter = () => {
    const listeners = new Map()
    return {
      on(event, callback) {
        if (!listeners.has(event)) listeners.set(event, new Set())
        listeners.get(event).add(callback)
        return () => listeners.get(event).delete(callback)
      },
      emit(event) { for (const callback of listeners.get(event) ?? []) callback() },
      listenerCount: () => [...listeners.values()].reduce((total, rows) => total + rows.size, 0),
    }
  }
  const cell = id => {
    const events = emitter(), handles = []
    const chart = { ...events, indicators: () => handles }
    return { id, chart, add(type, visible = true) {
      const handle = { id: id + '-' + type + '-' + handles.length, nativeType: type, visible, inputs: { length: 55 },
        inputValues() { return { ...this.inputs } },
        setInputs(values) { Object.assign(this.inputs, values) },
        remove() { handles.splice(handles.indexOf(this), 1); events.emit('indicator:removed') },
        setVisible(value) { this.visible = value; events.emit('indicator:visibility') } }
      handles.push(handle); events.emit('indicator:added')
      return handle
    } }
  }
  const c1 = cell('c1'), c2 = cell('c2'), cells = [c1, c2], added = [], errors = []
  const workspace = { ...emitter(), active: c1, cells: () => cells,
    context: () => ({ addNativeIndicator(type) { added.push(type); workspace.active.add(type) }, stateChanged() { workspace.emit('state:changed') } }) }
  const current = vue.shallowRef(workspace)
  const handlers = new Map()
  const { createWorkspaceIndicators } = load('workspaceIndicators', {
    '@luxalgo/vela/plugin': { registerStatePersistence: handler => handlers.set(handler.key, handler) },
  })
  const controller = createWorkspaceIndicators({ workspace: current, onError: error => errors.push(error) })
  return { controller, workspace, current, c1, c2, cells, added, errors, persistence: handlers.get('opentrading.indicatorShortcuts') }
}

test('indicator shortcuts remove disabled studies and restore all instances and their saved periods', () => {
  const { controller, workspace, c1, added, errors, persistence } = indicatorWorkspace()
  try {
    assert.equal(controller.selected.value.size, 0)
    controller.toggle('average-directional-index')
    assert.equal(controller.selected.value.has('average-directional-index'), true)
    assert.deepEqual(added, ['average-directional-index'])
    controller.toggle('average-directional-index')
    assert.equal(controller.selected.value.has('average-directional-index'), false)
    assert.equal(c1.chart.indicators().length, 0)
    controller.toggle('average-directional-index')
    assert.equal(c1.chart.indicators().length, 1)
    const fast = c1.add('sma'), slow = c1.add('sma', false)
    slow.inputs.length = 200
    controller.toggle('sma')
    assert.equal(c1.chart.indicators().some(handle => handle.nativeType === 'sma'), false)
    const snapshot = persistence.serialize({ chart: c1.chart })
    assert.deepEqual(snapshot.sma, [{ length: 55 }, { length: 200 }])
    persistence.restore({}, { chart: c1.chart })
    persistence.restore(snapshot, { chart: c1.chart })
    controller.toggle('sma')
    const restored = c1.chart.indicators().filter(handle => handle.nativeType === 'sma')
    assert.equal(restored.every(handle => handle.visible), true)
    assert.deepEqual(restored.map(handle => handle.inputs.length), [55, 200])
    controller.toggle('unknown')
    assert.deepEqual(added, ['average-directional-index', 'average-directional-index', 'sma', 'sma'])
    assert.deepEqual(errors, [])
  } finally { controller.dispose() }
  assert.equal(workspace.listenerCount(), 0)
  assert.equal(c1.chart.listenerCount(), 0)
})

test('indicator shortcuts follow external visibility, removal, active cells and restored charts', () => {
  const { controller, workspace, current, c1, c2, cells } = indicatorWorkspace()
  try {
    const volume = c1.add('volume')
    assert.equal(controller.selected.value.has('volume'), true)
    volume.setVisible(false)
    assert.equal(controller.selected.value.has('volume'), false)
    c2.add('rsi')
    workspace.active = c2; workspace.emit('cell:active')
    assert.deepEqual([...controller.selected.value], ['rsi'])
    c2.chart.indicators().splice(0); c2.chart.emit('indicator:removed')
    assert.equal(controller.selected.value.size, 0)
    cells.splice(0, 1); workspace.emit('layout:changed')
    assert.equal(c1.chart.listenerCount(), 0)
    c1.chart.indicators().splice(0); c1.add('ema')
    cells.push(c1); workspace.active = c1; workspace.emit('state:changed')
    assert.deepEqual([...controller.selected.value], ['ema'])
    current.value = undefined
    assert.equal(controller.selected.value.size, 0)
    assert.equal(workspace.listenerCount(), 0)
    assert.equal(c1.chart.listenerCount(), 0)
    assert.equal(c2.chart.listenerCount(), 0)
  } finally { controller.dispose() }
})

test('ADX reference lines are opt-in, adjustable, dashed and retained during bar updates', () => {
  const output = [], originalLines = [{ id: 'original', price: 25 }]
  let emitter, registrations = 0
  let descriptor = {
    type: 'average-directional-index', title: 'ADX',
    inputsSchema: () => [{ key: 'diLength', type: 'int', defval: 14 }],
    defaultInputs: () => ({ diLength: 14 }),
    create: () => ({
      start(ctx) { emitter = () => ctx.emit({ series: [], priceLines: originalLines }); emitter() },
      setInputs() { emitter() }, onBars() { emitter() }, onViewport() {}, suspend() {}, resume() { emitter() }, stop() {},
    }),
  }
  const { registerWorkspaceIndicatorDefinitions } = load('workspaceIndicatorDefinitions', {
    '@luxalgo/vela/plugin': { getNativeIndicator: () => descriptor, registerNativeIndicator(value) { descriptor = value; registrations++ } },
  })
  registerWorkspaceIndicatorDefinitions(); registerWorkspaceIndicatorDefinitions()
  assert.equal(registrations, 1)
  const defaults = descriptor.defaultInputs()
  assert.equal(defaults.showUpperLevel, false)
  assert.equal(defaults.showLowerLevel, false)
  assert.equal(defaults.upperLevel, 30)
  assert.equal(defaults.lowerLevel, 10)
  const instance = descriptor.create()
  instance.start({ id: 'adx1', emit: result => output.push(result) }, defaults)
  assert.deepEqual(output.at(-1).priceLines, [])
  instance.setInputs({ showUpperLevel: true })
  assert.deepEqual(output.at(-1).priceLines.map(line => [line.price, line.lineStyle]), [[30, 'dashed']])
  instance.setInputs({ showLowerLevel: true, upperLevel: 35, lowerLevel: 12 })
  instance.onBars()
  assert.deepEqual(output.at(-1).priceLines.map(line => [line.price, line.lineStyle]), [[35, 'dashed'], [12, 'dashed']])
  instance.setInputs({ showUpperLevel: false })
  assert.deepEqual(output.at(-1).priceLines.map(line => line.price), [12])
})

test('a clean draft from an older version never replaces newer server source', async () => {
  const { controller: docs } = documents({ drafts: { readDraft: async () => ({ source: 'old', base: 'old', version: 1, pending: false }) } })
  docs.scripts.value = [{ ...A(), version: 2, data: { source: 'server' } }]
  docs.scriptId.value = 'A'; await docs.openScript()
  assert.equal(docs.source.value, 'server')
  assert.equal(docs.scriptDirty.value, false)
  docs.dispose()
})

test('a conflicting or unversioned Pine draft can only save a separate copy', async () => {
  for (const draft of [{ source: 'legacy' }, { source: 'local', base: 'old', version: 1, pending: true }]) {
    const calls = []
    const { controller: docs } = documents({
      drafts: { readDraft: async () => draft },
      api: { save: async (_kind, id, body) => { calls.push({ id, ...body }); return { id, version: 1, ...body } } },
    })
    docs.scripts.value = [{ ...A(), version: 2, data: { source: 'server' } }]
    docs.scriptId.value = 'A'; await docs.openScript()
    assert.equal(docs.scriptConflict.value, true)
    await docs.saveScript(false)
    assert.notEqual(calls[0].id, 'A')
    assert.equal(calls[0].expected_version, 0)
    assert.equal(calls[0].data.source, draft.source)
    assert.equal(docs.scriptConflict.value, false)
    docs.dispose()
  }
})

test('a pending draft resumes against its original version and can accept the server version explicitly', async () => {
  const { controller: docs, writes } = documents({
    drafts: { readDraft: async () => ({ source: 'edited', base: 'A', version: 1, pending: true }) },
    api: { document: async () => ({ ...A(), version: 2, data: { source: 'server' } }) },
  })
  docs.scripts.value = [A()]; docs.scriptId.value = 'A'; await docs.openScript()
  assert.equal(docs.scriptConflict.value, false)
  assert.equal(docs.source.value, 'edited')
  await docs.useSavedScript()
  assert.equal(docs.source.value, 'server')
  assert.equal(writes.at(-1).pending, false)
  assert.equal(writes.at(-1).version, 2)
  docs.dispose()
})

test('Pine A-to-B-to-A discards the first A draft response through the public controller', async () => {
  const reads = [deferred(), deferred(), deferred()]
  let count = 0
  const { controller: docs } = documents({ drafts: { readDraft: () => reads[count++].promise } })
  docs.scripts.value = [A(), B()]
  docs.scriptId.value = 'A'
  const first = docs.openScript(); await tick()
  docs.scriptId.value = 'B'
  const second = docs.openScript(); await tick()
  docs.scriptId.value = 'A'
  const third = docs.openScript(); await tick()
  reads[2].resolve({ source: 'latest A' }); await third
  reads[1].resolve({ source: 'B draft' }); await second
  reads[0].resolve({ source: 'old A' }); await first
  assert.equal(docs.source.value, 'latest A')
  docs.dispose()
})

test('Pine save response cannot select a previous document or copy another document into its draft', async () => {
  const pending = deferred()
  const { controller: docs, writes } = documents({ api: { save: () => pending.promise } })
  docs.scripts.value = [A(), B()]
  docs.scriptId.value = 'A'; await docs.openScript()
  docs.source.value = 'A edited'
  const saving = docs.saveScript(false); await tick()
  docs.scriptId.value = 'B'; await docs.openScript()
  docs.source.value = 'B edited'
  pending.resolve({ ...A(), version: 2, data: { source: 'A edited' } }); await saving
  assert.equal(docs.scriptId.value, 'B')
  assert.equal(docs.source.value, 'B edited')
  assert.equal(docs.scriptDirty.value, true)
  assert.ok(!writes.some(draft => draft.key === 'script:A' && draft.source === 'B edited'))
  docs.dispose()
})

test('Pine edits made while saving retain dirty status and the newest draft', async () => {
  const pending = deferred()
  const { controller: docs, writes } = documents({ api: { save: () => pending.promise } })
  docs.scripts.value = [A()]; docs.scriptId.value = 'A'; await docs.openScript()
  docs.source.value = 'first'
  const saving = docs.saveScript(false); await tick()
  docs.source.value = 'second'
  pending.resolve({ ...A(), version: 2, data: { source: 'first' } }); await saving
  assert.equal(docs.scriptDirty.value, true)
  assert.ok(writes.some(draft => draft.key === 'script:A' && draft.source === 'second'))
  docs.dispose()
})

test('a late Pine import cannot replace a newly selected document', async () => {
  const file = deferred()
  const { controller: docs } = documents()
  docs.scripts.value = [A()]; docs.scriptId.value = 'A'
  const importing = docs.importScript({ target: { files: [{ text: () => file.promise }], value: 'input' } })
  await tick()
  await docs.openScript()
  file.resolve('late imported source'); await importing
  assert.equal(docs.source.value, 'A')
  docs.dispose()
})

function watchlists(api) {
  const { createWorkspaceWatchlists } = load('workspaceWatchlists', {
    './api': { chartApi: api }, './drafts': { deleteDraft:async()=>{}, readDraft: async () => undefined, writeDraft: async () => {} },
  })
  return createWorkspaceWatchlists({ activeSymbolId: vue.ref('BTC'), requestName: async () => 'renamed', onError: error => { throw error } })
}

test('hidden workspace pauses quotes, ignores an old response and resumes with retained prices', async () => {
  const requests = [deferred(), deferred()]
  let calls = 0
  const lists = watchlists({ quotes: () => requests[calls++].promise })
  try {
    lists.quotes.value.BTC = { id: 'BTC', price: 10 }
    const first = lists.refreshQuotes()
    lists.pause()
    await lists.refreshQuotes()
    requests[0].resolve([{ id: 'BTC', price: 20 }]); await first
    assert.equal(calls, 1)
    assert.equal(lists.quotes.value.BTC.price, 10)
    lists.resume()
    assert.equal(calls, 2)
    assert.equal(lists.quotes.value.BTC.price, 10)
    requests[1].resolve([{ id: 'BTC', price: 30 }]); await tick()
    assert.equal(lists.quotes.value.BTC.price, 30)
  } finally { lists.dispose() }
})
test('watchlist quotes discard old requests and cannot restart after disposal', async () => {
  const requests = [deferred(), deferred()]
  let calls = 0
  const lists = watchlists({ quotes: () => requests[calls++].promise })
  const first = lists.refreshQuotes(), second = lists.refreshQuotes()
  requests[1].resolve([{ id: 'BTC', price: 2 }]); await second
  lists.dispose()
  requests[0].resolve([{ id: 'BTC', price: 1 }]); await first
  await lists.refreshQuotes()
  assert.equal(lists.quotes.value.BTC.price, 2)
  assert.equal(calls, 2)
})
test('watchlist rename and content edits use the same versioned save queue', async () => {
  const pending = deferred(), calls = []
  const lists = watchlists({
    save: async (_kind, _id, body) => { calls.push(body); return calls.length === 1 ? pending.promise : { version: 3, name: body.name } },
    quotes: async () => [],
  })
  await lists.initialize([{ id: 'default', name: 'list', version: 1, data: { symbols: [] } }])
  const content = lists.persistWatch(['BTC']); await tick()
  const rename = lists.renameWatchlist(); await tick()
  assert.equal(calls.length, 1)
  pending.resolve({ version: 2 }); await content; await rename
  assert.deepEqual(calls.map(call => call.expected_version), [1, 2])
  assert.deepEqual(calls[1].data.symbols, ['BTC'])
  lists.dispose()
})

test('the other workspace keeps the selected watchlist and waits for edits to save', async () => {
  const save = deferred()
  let reads = 0
  const server = [
    { id: 'default', name: 'Default', version: 1, data: { symbols: ['ETH'] } },
    { id: 'rates', name: 'Rates', version: 1, data: { symbols: [] } },
  ]
  const { createSharedWorkspaceWatchlists } = load('workspaceWatchlists', {
    './api': { chartApi: {
      documents: async () => { reads++; return structuredClone(server) },
      quotes: async () => [],
      save: async (_kind, _id, body) => {
        await save.promise
        Object.assign(server[1], { version: body.expected_version + 1, data: JSON.parse(JSON.stringify(body.data)) })
        return server[1]
      },
    } },
    './drafts': { deleteDraft:async()=>{}, readDraft: async () => undefined, writeDraft: async () => {} },
  })
  const deps = { activeSymbolId: vue.ref('BTC'), requestName: async () => null, onError: assert.fail }
  const chart = createSharedWorkspaceWatchlists(deps)
  const observation = createSharedWorkspaceWatchlists(deps)
  try {
    await chart.loadWatchlists()
    chart.watchlistId.value = 'rates'
    assert.equal(observation.watchlistId.value, 'rates')
    const edit = chart.persistWatch(['BTC'])
    chart.dispose()
    const reloading = observation.loadWatchlists()
    await tick()
    assert.equal(reads, 1)
    assert.deepEqual(observation.watchSymbols.value, ['BTC'])
    save.resolve()
    await Promise.all([edit, reloading])
    assert.equal(reads, 2)
    assert.deepEqual(observation.watchSymbols.value, ['BTC'])
    assert.equal(observation.watchlist.value.version, 2)
    assert.deepEqual(observation.pendingWatch.value, [])
  } finally {
    chart.dispose()
    observation.dispose()
  }
})

function layouts(api, snapshot = () => ({ state: { layout: '1' } })) {
  const applied = [], drafts = []
  const { createWorkspaceLayouts } = load('workspaceLayouts', {
    './api': { chartApi: api }, './drafts': { deleteDraft:async()=>{}, readDraft: async () => undefined, writeDraft: async (key, value) => drafts.push({ key, value }) },
    './legacyState': { migrateWorkspaceState: value => value },
    './layoutMerge': load('layoutMerge', {}),
  })
  const controller = createWorkspaceLayouts({ snapshot, apply: value => applied.push(value), requestName: async () => 'copy', onError: error => { throw error } })
  return { controller, applied, drafts }
}
test('layout save acknowledges only its captured snapshot while retaining edits made in flight', async () => {
  const pending = deferred()
  let value = 0, calls = 0
  const { controller: state, drafts } = layouts({ save: (_kind, _id, body) => ++calls === 1 ? pending.promise : Promise.resolve({ id: 'default', version: 3, data: body.data }) }, () => ({ value }))
  await state.initialize([{ id: 'default', version: 1, data: { value: 0 } }])
  value = 1
  const saving = state.saveNow(); await tick()
  value = 2; state.dirty()
  pending.resolve({ id: 'default', version: 2, data: { value: 1 } }); await saving
  assert.equal(state.saveStatus.value, 'saving')
  assert.deepEqual(drafts.at(-1).value, { version: 2, base: { value: 1 }, data: { value: 2 }, pending: true })
  state.dispose()
})
test('late layout selection cannot overwrite a more recent selection', async () => {
  const old = deferred(), latest = deferred()
  let calls = 0
  const { controller: state, applied } = layouts({
    save: async () => ({ id: 'default', version: 1 }), documents: () => [old, latest][calls++].promise,
  })
  const first = state.switchLayout('A'); await tick()
  const second = state.switchLayout('B'); await tick()
  latest.resolve([{ id: 'B', version: 2, data: { layout: 'B' } }]); await second
  old.resolve([{ id: 'A', version: 1, data: { layout: 'A' } }]); await first
  assert.equal(state.layoutId.value, 'B')
  assert.deepEqual(applied, [{ layout: 'B' }])
  state.dispose()
})

const clone = value => JSON.parse(JSON.stringify(value))
function layoutServer(data) {
  let saved = { id: 'default', name: 'layout', version: 1, data: clone(data) }
  const revisions = new Map([[1, clone(saved)]]), calls = []
  return {
    calls, latest: () => clone(saved),
    api: {
      document: async (_kind, _id, version) => clone(version ? revisions.get(version) : saved),
      documents: async () => [clone(saved)],
      save: async (_kind, id, body) => {
        calls.push(clone(body))
        if (body.expected_version !== saved.version) throw Object.assign(new Error('conflict'), { status: 409 })
        saved = { id, name: body.name, version: saved.version + 1, data: clone(body.data) }
        revisions.set(saved.version, clone(saved))
        return clone(saved)
      },
    },
  }
}
function automaticLayout(api, localDraft) {
  let view = {}
  const errors = [], drafts = []
  const { createWorkspaceLayouts } = load('workspaceLayouts', {
    './api': { chartApi: api }, './legacyState': { migrateWorkspaceState: value => value },
    './layoutMerge': load('layoutMerge', {}),
    './drafts': { readDraft: async key => key === 'layout:default' ? localDraft : undefined,
      writeDraft: async (key, data) => drafts.push({ key, data: clone(data) }) },
  })
  const controller = createWorkspaceLayouts({ snapshot: () => view, apply: data => { view = clone(data) },
    requestName: async () => 'copy', onError: error => errors.push(error) })
  return { controller, errors, drafts, view: () => view, change: change => { change(view); controller.dirty() } }
}

test('two windows merge separate layout edits automatically and current changes win on the same field', async () => {
  const server = layoutServer({ rightWidth: 300, rightOpen: true, bottomHeight: 340 })
  const a = automaticLayout(server.api), b = automaticLayout(server.api)
  await a.controller.initialize([server.latest()]); await b.controller.initialize([server.latest()])
  a.change(view => { view.rightWidth = 380 }); await a.controller.saveNow()
  b.change(view => { view.bottomHeight = 400 }); await b.controller.saveNow()
  assert.deepEqual(server.latest().data, { rightWidth: 380, rightOpen: true, bottomHeight: 400 })
  assert.deepEqual(b.view(), server.latest().data)
  a.change(view => { view.rightWidth = 420 }); await a.controller.saveNow()
  b.change(view => { view.rightWidth = 450 }); await b.controller.saveNow()
  assert.equal(server.latest().data.rightWidth, 450)
  assert.deepEqual([...a.errors, ...b.errors], [])
  a.controller.dispose(); b.controller.dispose(); await tick()
})

test('initial loading, unchanged saves and closing an idle stale window do not write revisions', async () => {
  const server = layoutServer({ rightOpen: true })
  const a = automaticLayout(server.api), b = automaticLayout(server.api)
  a.controller.dirty(); await a.controller.saveNow()
  assert.equal(server.calls.length, 0)
  await a.controller.initialize([server.latest()]); await b.controller.initialize([server.latest()])
  await a.controller.saveNow(); assert.equal(server.calls.length, 0)
  // SDK snapshots contain optional undefined properties; the JSON document
  // omits them. They must not turn an unchanged chart into another save.
  a.change(view => { view.optional = undefined })
  await a.controller.saveNow(); assert.equal(server.calls.length, 0)
  b.change(view => { view.rightOpen = false }); await b.controller.saveNow()
  const count = server.calls.length
  a.controller.dispose(); b.controller.dispose(); await tick()
  assert.equal(server.calls.length, count)
  assert.equal(server.latest().data.rightOpen, false)
})

test('an existing unsaved draft rebases against its historical version without a recovery prompt', async () => {
  const server = layoutServer({ rightWidth: 300, bottomHeight: 340 })
  await server.api.save('layouts', 'default', { name: 'layout', expected_version: 1, data: { rightWidth: 420, bottomHeight: 340 } })
  const state = automaticLayout(server.api, { version: 1, data: { rightWidth: 300, bottomHeight: 500 }, pending: true })
  await state.controller.initialize([server.latest()])
  assert.deepEqual(server.latest().data, { rightWidth: 420, bottomHeight: 500 })
  assert.equal(state.controller.saveStatus.value, 'saved')
  assert.deepEqual(state.errors, [])
  assert.equal(state.drafts.at(-1).data.pending, false)
  state.controller.dispose(); await tick()
})

test('a conflict retry retains edits made while the first save is in flight', async () => {
  const server = layoutServer({ rightWidth: 300, bottomHeight: 340 }), wait = deferred()
  let first = true
  const state = automaticLayout({ ...server.api, save: async (...args) => {
    if (first) { first = false; await wait.promise }
    return server.api.save(...args)
  } })
  await state.controller.initialize([server.latest()])
  state.change(view => { view.rightWidth = 380 })
  const saving = state.controller.saveNow(); await tick()
  await server.api.save('layouts', 'default', { name: 'layout', expected_version: 1, data: { rightWidth: 300, bottomHeight: 500 } })
  state.change(view => { view.rightWidth = 420 })
  wait.resolve(); await saving
  assert.equal(state.view().rightWidth, 420)
  assert.equal(state.view().bottomHeight, 500)
  await state.controller.saveNow()
  assert.deepEqual(server.latest().data, { rightWidth: 420, bottomHeight: 500 })
  assert.deepEqual(state.errors, [])
  state.controller.dispose(); await tick()
})

test('layout merge preserves other cells and drawing IDs, and keeps a market with its viewport', () => {
  const { mergeLayout } = load('layoutMerge', {})
  const cell = { id: 'c1', symbol: 'ETH', timeframe: '60', ext: { 'opentrading.viewport': { from: 10, to: 20 } }, drawings: [{ id: 'line1', color: 'red' }] }
  const base = { state: { charts: [cell, { ...cell, id: 'c2' }] } }, local = clone(base), remote = clone(base)
  local.state.charts[0].ext['opentrading.viewport'] = { from: 12, to: 22 }
  remote.state.charts[0].symbol = 'BTC'
  remote.state.charts[0].drawings.push({ id: 'line2', color: 'blue' })
  remote.state.charts[1].timeframe = 'D'
  const merged = mergeLayout(base, local, remote)
  assert.equal(merged.state.charts[0].symbol, 'ETH')
  assert.deepEqual(merged.state.charts[0].ext['opentrading.viewport'], { from: 12, to: 22 })
  assert.equal(merged.state.charts[0].drawings.length, 2)
  assert.equal(merged.state.charts[1].timeframe, 'D')
})

test('repeated version contention stays quiet and a later retry saves the retained draft', async () => {
  const server = layoutServer({ rightWidth: 300 })
  let conflicts = 3
  const state = automaticLayout({ ...server.api, save: async (...args) => {
    if (conflicts-- > 0) throw Object.assign(new Error('conflict'), { status: 409 })
    return server.api.save(...args)
  } })
  await state.controller.initialize([server.latest()])
  state.change(view => { view.rightWidth = 400 }); await state.controller.saveNow()
  assert.deepEqual(state.errors, [])
  assert.equal(state.drafts.at(-1).data.pending, true)
  await state.controller.saveNow()
  assert.equal(server.latest().data.rightWidth, 400)
  assert.equal(state.controller.saveStatus.value, 'saved')
  state.controller.dispose(); await tick()
})

test('a connection failure retains the draft and does not masquerade as a successful save', async () => {
  const server = layoutServer({ rightOpen: false })
  let offline = true
  const state = automaticLayout({ ...server.api, save: async (...args) => {
    if (offline) throw new Error('Failed to fetch')
    return server.api.save(...args)
  } })
  await state.controller.initialize([server.latest()])
  state.change(view => { view.rightOpen = true }); await state.controller.saveNow()
  assert.equal(state.controller.saveStatus.value, 'unsaved')
  assert.equal(state.drafts.at(-1).data.pending, true)
  assert.equal(state.errors.length, 1)
  offline = false; await state.controller.saveNow()
  assert.equal(server.latest().data.rightOpen, true)
  assert.equal(state.controller.saveStatus.value, 'saved')
  state.controller.dispose(); await tick()
})
test('Pine execution cancellation removes pending handles and prevents a late ready result', async () => {
  const events = {}, removed = [], logs = []
  const handle = { id: '', on: (kind, callback) => { events[kind] = callback; return () => {} }, remove: () => removed.push('removed') }
  const cell = { id: 'c1', chart: { indicators: () => [handle] } }
  const workspace = { active: cell, context: () => ({ addIndicator: options => { handle.id = options.id } }) }
  const { createPineExecution } = load('pineExecution', {
    './persistence': { markScript: () => assert.fail('cancelled indicators cannot be saved') },
    './pineCompatibility.mjs': { checkPine: () => {} },
  })
  const execution = createPineExecution({
    workspace: () => workspace,
    documents: { selectedScript: vue.ref(A()), source: vue.ref('A'), scriptDirty: vue.ref(false),
      scriptLoading: vue.ref(false), selectionEpoch: () => 1 },
    onError: error => assert.fail(String(error)), log: text => logs.push(text), dirty: () => assert.fail('cancelled'),
  })
  const running = execution.addPine()
  execution.dispose()
  events.ready()
  await running
  assert.equal(execution.executing.value, false)
  assert.equal(removed.length, 1)
  assert.deepEqual(logs, [])
})


test('renaming a Pine document preserves unsaved source and deleting it selects a surviving script',async()=>{
  const removed=[],draftRemovals=[]
  const {controller:docs}=documents({api:{save:async(_kind,id,body)=>({id,...body,version:2}),remove:async(kind,id,version)=>removed.push({kind,id,version})},drafts:{deleteDraft:async key=>draftRemovals.push(key)}})
  try{
    docs.scripts.value=[A(),B()];docs.scriptId.value='A';await docs.openScript();docs.source.value='unsaved source'
    await docs.renameScript()
    assert.equal(docs.selectedScript.value.name,'copy');assert.equal(docs.source.value,'unsaved source');assert.equal(docs.scriptDirty.value,true)
    await docs.deleteScript()
    assert.deepEqual(removed,[{kind:'scripts',id:'A',version:2}]);assert.deepEqual(draftRemovals,['script:A'])
    assert.equal(docs.scriptId.value,'B');assert.equal(docs.source.value,'B')
  }finally{docs.dispose()}
})

test('deleting a watchlist waits for queued writes and switches to a remaining list',async()=>{
  const pending=deferred(),calls=[]
  const lists=watchlists({quotes:async()=>[],save:async(_kind,id,body)=>{await pending.promise;return{id,...body,version:2}},remove:async(kind,id,version)=>calls.push({kind,id,version})})
  try{
    await lists.initialize([{id:'A',version:1,name:'A',data:{symbols:[]}},{id:'B',version:1,name:'B',data:{symbols:[]}}]);lists.watchlistId.value='A'
    const save=lists.persistWatch(['BTC']),remove=lists.deleteWatchlist();await tick();assert.deepEqual(calls,[])
    pending.resolve();await save;await remove
    assert.deepEqual(calls,[{kind:'watchlists',id:'A',version:2}]);assert.equal(lists.watchlistId.value,'B')
  }finally{lists.dispose()}
})

test('layout rename and deletion use the current revision and do not recreate an empty library on disposal',async()=>{
  const saved=[],removed=[]
  const {controller:state}=layouts({save:async(_kind,id,body)=>{saved.push(body);return{id,...body,version:body.expected_version+1}},remove:async(kind,id,version)=>removed.push({kind,id,version})},()=>({state:{layout:'1'}}))
  await state.initialize([{id:'A',version:1,name:'A',data:{state:{layout:'1'}}}])
  await state.renameLayout();assert.equal(state.layouts.value[0].name,'copy')
  await state.deleteLayout();assert.deepEqual(removed,[{kind:'layouts',id:'A',version:2}]);assert.equal(state.layouts.value.length,0);assert.notEqual(state.layoutId.value,'A');assert.equal(state.saveStatus.value,'unsaved')
  state.dispose();await tick();assert.equal(saved.length,1)
})

test('the unsaved view after deleting the last layout can be saved as a new document',async()=>{
  const saved=[]
  const {controller:state}=layouts({save:async(_kind,id,body)=>{saved.push(id);return{id,...body,version:body.expected_version+1}},remove:async()=>{}},()=>({state:{layout:'1'}}))
  await state.initialize([{id:'A',version:1,name:'A',data:{state:{layout:'1'}}}])
  await state.deleteLayout();await state.saveNow();assert.equal(saved.length,0);await state.saveNow(true)
  assert.equal(saved.length,1);assert.notEqual(saved[0],'A');assert.equal(state.saveStatus.value,'saved')
  state.dispose()
})
