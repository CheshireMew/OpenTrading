import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import { reactive } from 'vue'

function browserAlerts() {
  let state
  const exports = {}, store = {
    browserRecord: async () => structuredClone(state),
    updateBrowserRecord: async (_key, change) => { state = structuredClone(change(structuredClone(state))); return structuredClone(state) },
  }
  class ApiRequestError extends Error { constructor(message, options) { super(message); Object.assign(this, options) } }
  const code = ts.transpileModule(fs.readFileSync(new URL('../src/modules/research/browserResearch.ts', import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  new Function('require', 'exports', code)(id => id.includes('browserStore') ? store : { ApiRequestError }, exports)
  return { api: exports.createBrowserResearchApi({}), evaluate: exports.evaluateBrowserAlerts, state: () => state }
}
const rule = (configuration = {}) => ({ symbol: 'BTC/USDT', name: 'BTC price', metric: 'price', operator: 'crosses', threshold: 100,
  enabled: true, cooldownMinutes: 1, notificationChannels: ['in_app', 'sound'], configuration: { chartSymbolId: 'binance:spot:BTCUSDT', initialPrice: 90, once: true, ...configuration } })
const quotes = async () => ({ ok: true, json: async () => [{ id: 'binance:spot:BTCUSDT', price: 105 }] })

test('a browser one-shot alert is physically removed while its notification survives', async () => {
  global.fetch = quotes
  const browser = browserAlerts(), alert = await browser.api.createAlert(rule())
  assert.equal((await browser.evaluate()).triggeredCount, 1)
  assert.deepEqual(browser.state().alerts, [])
  const events = (await browser.api.listEvents()).items
  assert.equal(events.length, 1)
  assert.equal(events[0].entityId, alert.id)
  assert.deepEqual(events[0].payload.notificationChannels, ['in_app', 'sound'])
  assert.equal((await browser.evaluate()).triggeredCount, 0)
})

test('explicit repeating rules stay active and paused rules are preserved', async () => {
  global.fetch = quotes
  const browser = browserAlerts()
  const repeat = await browser.api.createAlert(rule({ once: false }))
  const paused = await browser.api.createAlert({ ...rule(), enabled: false })
  await browser.evaluate()
  assert.equal(browser.state().alerts.find(row => row.id === repeat.id).enabled, true)
  assert.equal(browser.state().alerts.find(row => row.id === paused.id).lastTriggeredAt, undefined)
  assert.equal((await browser.api.getWorkbench()).alerts.length, 2)
})

test('reactive form and chart objects can be persisted and edited in IndexedDB', async () => {
  const browser = browserAlerts(), body = reactive(rule())
  const alert = await browser.api.createAlert(body)
  const values = reactive({ ...alert, threshold: 110, expectedVersion: alert.version })
  await browser.api.updateAlert(alert.id, values)
  assert.equal(browser.state().alerts[0].threshold, 110)
  assert.deepEqual(browser.state().alerts[0].configuration, rule().configuration)
})

test('delete checks revisions, removes the stored rule, and a stale evaluation cannot recreate it', async () => {
  const browser = browserAlerts(), alert = await browser.api.createAlert(rule())
  await assert.rejects(browser.api.deleteAlert(alert.id, alert.version + 1), { status: 409 })
  assert.equal(browser.state().alerts.length, 1)
  let respond
  global.fetch = () => new Promise(resolve => { respond = resolve })
  const evaluating = browser.evaluate()
  while (!respond) await Promise.resolve()
  await browser.api.deleteAlert(alert.id, alert.version)
  respond(await quotes())
  assert.equal((await evaluating).triggeredCount, 0)
  assert.deepEqual(browser.state().alerts, [])
})

test('an edit during quote loading invalidates the older evaluation and old completed rules are cleaned up', async () => {
  const browser = browserAlerts(), alert = await browser.api.createAlert(rule())
  let respond
  global.fetch = () => new Promise(resolve => { respond = resolve })
  const evaluating = browser.evaluate()
  while (!respond) await Promise.resolve()
  await browser.api.updateAlert(alert.id, { ...rule(), threshold: 200, expectedVersion: alert.version })
  respond(await quotes())
  assert.equal((await evaluating).triggeredCount, 0)
  await browser.api.updateAlert(alert.id, { enabled: false, lastTriggeredAt: new Date().toISOString(), expectedVersion: 2 })
  assert.deepEqual((await browser.api.getWorkbench()).alerts, [])
  assert.deepEqual(browser.state().alerts, [])
})

test('deleting a browser research list removes its linked records and keeps other lists', async () => {
  const browser=browserAlerts(),api=browser.api
  const list=await api.createWatchlist({name:'Delete'}),other=await api.createWatchlist({name:'Keep'})
  const item=await api.createItem({watchlistId:list.id,symbol:'BTC/USDT'})
  await api.createNote({watchItemId:item.id,symbol:item.symbol,title:'Linked',content:'Private'})
  await api.createAlert({...rule(),watchItemId:item.id})
  await assert.rejects(api.deleteWatchlist(list.id,list.version+1),{status:409})
  await api.deleteWatchlist(list.id,list.version)
  const saved=browser.state()
  assert.deepEqual(saved.watchlists.map(row=>row.id),[other.id])
  for(const kind of ['items','notes','alerts'])assert.deepEqual(saved[kind],[])
  assert.ok(saved.events.every(row=>row.entityId===other.id))
})

test('browser item, note and screener deletion remove their own data without erasing the parent list',async()=>{
  const browser=browserAlerts(),api=browser.api,list=await api.createWatchlist({name:'Keep'})
  const item=await api.createItem({watchlistId:list.id,symbol:'BTC/USDT'})
  const note=await api.createNote({watchItemId:item.id,symbol:item.symbol,title:'Delete'})
  await api.deleteNote(note.id,note.version)
  assert.equal(browser.state().items.length,1)
  await api.deleteItem(item.id,item.version)
  assert.equal(browser.state().watchlists.length,1)
  const screener=await api.createScreener({name:'Delete',filters:{}})
  await api.deleteScreener(screener.id,screener.version)
  assert.deepEqual(browser.state().screeners,[])
})
