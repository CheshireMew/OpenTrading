import assert from 'node:assert/strict'
import { createHash, randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import { browserSession } from './helpers/browserSession.mjs'

// Exact historical producer, not a handwritten approximation of the v1 store.
const legacy = readFileSync(new URL('./fixtures/browser-history/browserStore.v1.ts', import.meta.url))
assert.equal(createHash('sha256').update(legacy).digest('hex'), '28b57307077ef5db53603f9cd3c95eebb83abddcbb6af66d7e41fea74a0da72d')
let session, fixture
const browser = async () => session ??= await browserSession()
after(async () => { await session?.close() })
// Resource-free collection preserves the identities used by the normal runner.
const options = { timeout: 45_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER }

async function historicalRun() {
  if (!fixture) {
    const { runPineComputation } = await import('../src/modules/chartWorkspace/pineComputation.mjs')
    const start = Date.UTC(2024, 0, 1), interval = 3_600_000
    const bars = Array.from({ length: 12_050 }, (_, i) => ({ time: start + i * interval, closeTime: start + (i + 1) * interval,
      open: 100, high: 102, low: 99, close: 100 + i % 10 / 10, volume: 1, closed: true }))
    const source = '//@version=6\nstrategy("Persistence", initial_capital=10000)\nif bar_index == 1\n    strategy.entry("L", strategy.long, qty=1)\nif bar_index == 10\n    strategy.close("L")'
    const request = { script_id: 'persistence-fixture', script_version: 1, script_source: source,
      symbol: 'binance:spot:ETHUSDT', timeframe: '1h', start, end: bars.at(-1).closeTime, inputs: {}, props: {} }
    const symbol = { id: request.symbol, symbol: 'ETHUSDT', name: 'ETH/USDT', exchange: 'binance', market: 'spot', currency: 'USDT',
      timezone: 'Etc/UTC', session: '24x7', close_only: false, metadata: { mintick: 0.01, minmove: 1, pricescale: 100, pointvalue: 1 } }
    const result = await runPineComputation({ source, request, symbol, bars, frozen: true }, {
      hash: async value => createHash('sha256').update(JSON.stringify(value)).digest('hex'),
    })
    assert.equal(result.equity.length, bars.length)
    fixture = JSON.parse(JSON.stringify({ run: { id: 'historical-' + randomUUID(), status: 'completed', progress: 100, created_at: Date.now(),
      request, recording: 'report', summary: result.summary, provenance: result.provenance }, result }
    ))
  }
  return fixture
}

async function legacyPage() {
  const instance = await browser(), context = await instance.context(), page = await instance.page(context)
  const value = await historicalRun()
  await page.evaluate(`const store = await import('/test/fixtures/browser-history/browserStore.v1.ts');
    await store.restoreBrowserRecords({ ['pine-run:' + input.run.id]: input });`, value)
  await page.close()
  return { context, page: await instance.page(context), value }
}

const observeReads = `
  const counts = { rows: 0, bytes: 0 };
  const observe = value => {
    if (!value) return;
    counts.bytes += new TextEncoder().encode(JSON.stringify(value)).byteLength;
    const values = Array.isArray(value) ? value : [value];
    for (const item of values) {
      if (item?.run && item.result) {
        for (const rows of Object.values(item.result)) if (Array.isArray(rows)) counts.rows += rows.length;
      } else if (item && typeof item.equity === 'number' && typeof item.time === 'number') counts.rows++;
    }
  };
  for (const method of ['get', 'getAll', 'openCursor']) {
    const original = IDBObjectStore.prototype[method];
    IDBObjectStore.prototype[method] = function(...args) {
      const request = original.apply(this, args);
      request.addEventListener('success', () => observe(method === 'openCursor' ? request.result?.value : request.result));
      return request;
    };
  }
`

test('backup remaps a conflicting screener and every saved run to the copied parent', options, async () => {
  const instance = await browser(), context = await instance.context()
  let page = await instance.page(context)
  const original = await page.evaluate(`
    const { createBrowserResearchApi } = await import('/src/modules/research/browserResearch.ts');
    const backup = await import('/src/modules/chartWorkspace/browserDataBackup.ts');
    const api = createBrowserResearchApi({});
    const screener = await api.createScreener({ name: 'Imported screener', filters: { market: 'all', symbols: [] } });
    const originalFetch = window.fetch;
    window.fetch = (url, init) => String(url).includes('/screener-preview')
      ? Promise.resolve(new Response(JSON.stringify({ snapshotAsOf: new Date().toISOString(), evaluatedAt: new Date().toISOString(), filters: screener.filters, resultCount: 1, resultItems: [{ symbol: 'BTCUSDT' }], historicalReplay: false }))) : originalFetch(url, init);
    const run = await api.runScreener(screener.id);
    const exported = await backup.exportBrowserData();
    await api.updateScreener(screener.id, { expectedVersion: screener.version, name: 'Keep current screener', filters: screener.filters });
    await backup.importBrowserData(JSON.stringify(exported));
    return { screener: screener.id, run: run.id };
  `)
  await page.close(); page = await instance.page(context)
  const result = await page.evaluate(`
    const api = (await import('/src/modules/research/browserResearch.ts')).createBrowserResearchApi({});
    const rows = (await api.listScreeners()).items;
    const copy = rows.find(row => row.name === 'Imported screener');
    const copiedRuns = (await api.listScreenerRuns(copy.id)).items;
    const originalRuns = (await api.listScreenerRuns(input.screener)).items;
    return { copiedParent: copy.id !== input.screener, keptOriginal: originalRuns[0]?.id === input.run,
      copiedRun: copiedRuns[0]?.id !== input.run, copiedCount: copiedRuns.length, symbol: copiedRuns[0]?.resultItems[0]?.symbol };
  `, original)
  assert.deepEqual(result, { copiedParent: true, keptOriginal: true, copiedRun: true, copiedCount: 1, symbol: 'BTCUSDT' })
  await page.close()
})

test('a complete Pine report survives an actual browser restart in its own profile', options, async () => {
  const instance = await browser(), value = await historicalRun()
  let page = await instance.page()
  await page.evaluate(`await (await import('/src/modules/personal/browserStore.ts')).browserPineStore.restore(input);`, value)
  await page.close(); await instance.restart(); page = await instance.page()
  const result = await page.evaluate(`
    const pine = (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns;
    const run = await pine.getRun(input);
    const tail = await pine.records(input, 'equity', 12000, 100);
    return { status: run.status, progress: run.progress, tail };
  `, value.run.id)
  assert.equal(result.status, 'completed')
  assert.equal(result.progress, null)
  assert.equal(result.tail.total, value.result.equity.length)
  assert.deepEqual(result.tail.items, value.result.equity.slice(12000))
  await page.close()
})

test('browser backup preserves copied descendants and survives a new page', options, async () => {
  const instance = await browser(), context = await instance.context()
  let page = await instance.page(context)
  const identities = await page.evaluate(`
    const { createBrowserResearchApi } = await import('/src/modules/research/browserResearch.ts');
    const backup = await import('/src/modules/chartWorkspace/browserDataBackup.ts');
    const api = createBrowserResearchApi({});
    const list = await api.createWatchlist({ name: 'Backup list', description: '' });
    const item = await api.createItem({ watchlistId: list.id, symbol: 'BTC/USDT' });
    const note = await api.createNote({ watchItemId: item.id, symbol: item.symbol, title: 'Linked note', content: 'Keep' });
    const alert = await api.createAlert({ watchItemId: item.id, symbol: item.symbol, name: 'Linked alert', metric: 'price', operator: 'gte', threshold: 100, configuration: {} });
    const exported = await backup.exportBrowserData();
    await api.updateWatchlist(list.id, { name: 'Current edited list', expectedVersion: list.version });
    await backup.importBrowserData(JSON.stringify(exported));
    return { list: list.id, item: item.id, note: note.id, alert: alert.id };
  `)
  await page.close()
  page = await instance.page(context)
  const result = await page.evaluate(`
    const { createBrowserResearchApi } = await import('/src/modules/research/browserResearch.ts');
    const state = await createBrowserResearchApi({}).getWorkbench();
    const imported = state.watchlists.find(row => row.name === 'Backup list');
    const child = state.items.find(row => row.watchlistId === imported?.id);
    return { copied: imported?.id !== input.list, original: state.items.some(row => row.id === input.item && row.watchlistId === input.list),
      items: state.items.filter(row => row.watchlistId === imported?.id).length,
      notes: state.notes.filter(row => row.watchItemId === child?.id).length,
      alerts: state.alerts.filter(row => row.watchItemId === child?.id).length,
      eventsValid: state.events.every(row => [...state.watchlists, ...state.items, ...state.notes, ...state.alerts].some(entity => entity.id === row.entityId)) };
  `, identities)
  assert.deepEqual(result, { copied: true, original: true, items: 1, notes: 1, alerts: 1, eventsValid: true })
  await page.close()
})

test('Pine run lists read metadata instead of complete report payloads', options, async () => {
  const { page, value } = await legacyPage()
  const result = await page.evaluate(`
    const { browserPineRuns } = await import('/src/modules/chartWorkspace/browserPineRuns.ts');
    await browserPineRuns.getRun(input);
    ${observeReads}
    const runs = await browserPineRuns.runs();
    return { exists: runs.some(row => row.id === input), ...counts };
  `, value.run.id)
  assert.equal(result.exists, true)
  assert.equal(result.rows, 0, `list decoded ${result.rows} report rows (${result.bytes} bytes)`)
  await page.close()
})

test('Pine pages and backups preserve historical reports without reading entire results per page', options, async () => {
  const { context, page, value } = await legacyPage()
  const result = await page.evaluate(`
    const { browserPineRuns } = await import('/src/modules/chartWorkspace/browserPineRuns.ts');
    await browserPineRuns.getRun(input);
    ${observeReads}
    const page = await browserPineRuns.records(input, 'equity', 11, 7);
    return { page, ...counts };
  `, value.run.id)
  assert.equal(result.page.total, value.result.equity.length)
  assert.deepEqual(result.page.items, value.result.equity.slice(11, 18))
  assert.ok(result.rows <= 7, `one page decoded ${result.rows} report rows (${result.bytes} bytes)`)
  const exported = await page.evaluate(`return await (await import('/src/modules/chartWorkspace/browserDataBackup.ts')).exportBrowserData();`)
  assert.deepEqual(exported.records['pine-run:' + value.run.id].result, value.result)
  await page.close()
  const instance = await browser(), importedContext = await instance.context()
  let reopened = await instance.page(importedContext)
  await reopened.evaluate(`await (await import('/src/modules/chartWorkspace/browserDataBackup.ts')).importBrowserData(JSON.stringify(input));`, exported)
  await reopened.close()
  reopened = await instance.page(importedContext)
  const tail = await reopened.evaluate(`return await (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns.records(input, 'equity', 10_000, 10_000);`, value.run.id)
  assert.deepEqual(tail.items, value.result.equity.slice(10_000))
  assert.equal(tail.total, value.result.equity.length)
  assert.ok(context)
  await reopened.close()
})

for (const action of ['delete', 'edit']) test(`browser lifecycle: a late screener preview cannot survive ${action}`, options, async () => {
  const instance = await browser(), context = await instance.context()
  const page = await instance.page(context), other = await instance.page(context)
  const screener = await page.evaluate(`
    const { createBrowserResearchApi } = await import('/src/modules/research/browserResearch.ts');
    window.api = createBrowserResearchApi({});
    const row = await api.createScreener({ name: 'Racing screener', filters: { market: 'all', limit: 100 } });
    window.fetch = () => new Promise(resolve => { window.previewResponse = resolve });
    window.preview = api.runScreener(row.id).then(() => ({ accepted: true }), error => ({ status: error.status }));
    while (!window.previewResponse) await new Promise(resolve => setTimeout(resolve, 0));
    return row;
  `)
  await other.evaluate(`
    const { createBrowserResearchApi } = await import('/src/modules/research/browserResearch.ts');
    const api = createBrowserResearchApi({});
    if (input.action === 'delete') await api.deleteScreener(input.row.id, input.row.version);
    else await api.updateScreener(input.row.id, { expectedVersion: input.row.version, name: 'New filters', filters: { market: 'spot', limit: 10 } });
  `, { action, row: screener })
  const outcome = await page.evaluate(`
    window.previewResponse(new Response(JSON.stringify({ snapshotAsOf: '2026-11-25T00:00:00Z', filters: {}, items: [], total: 0 })));
    return await window.preview;
  `)
  await page.close(); await other.close()
  const reopened = await instance.page(context)
  const runs = await reopened.evaluate(`return await (await import('/src/modules/research/browserResearch.ts')).createBrowserResearchApi({}).listScreenerRuns(input);`, screener.id)
  assert.deepEqual(outcome, { status: action === 'delete' ? 404 : 409 })
  assert.equal(runs.items.length, 0)
  await reopened.close()
})

const pendingPine = `
  window.pine = (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns;
  window.owned = [];
  window.fetch = (_url, options = {}) => new Promise((_resolve, reject) => {
    options.signal?.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError')), { once: true });
  });
`
const cancelOwned = `await Promise.allSettled(window.owned.map(id => window.pine.cancel(id)));`

test('browser lifecycle: Pine admission reserves before asynchronous persistence', options, async () => {
  const instance = await browser(), context = await instance.context(), page = await instance.page(context)
  try {
    const accepted = await page.evaluate(`
      ${pendingPine}
      const results = await Promise.allSettled([pine.run(input), pine.run(input), pine.run(input)]);
      window.owned = results.filter(row => row.status === 'fulfilled').map(row => row.value.id);
      return { accepted: owned.length, rejected: results.filter(row => row.status === 'rejected').length };
    `, (await historicalRun()).run.request)
    assert.deepEqual(accepted, { accepted: 2, rejected: 1 })
  } finally { await page.evaluate(cancelOwned); await page.close() }
})

test('browser lifecycle: Pine slots are shared by tabs and released by cancellation', options, async () => {
  const instance = await browser(), context = await instance.context()
  const page = await instance.page(context), other = await instance.page(context)
  const request = (await historicalRun()).run.request
  try {
    const ids = await page.evaluate(`
      ${pendingPine}
      window.owned = (await Promise.all([pine.run(input), pine.run(input)])).map(row => row.id);
      return owned;
    `, request)
    const blocked = await other.evaluate(`
      ${pendingPine}
      try { const run = await pine.run(input); owned.push(run.id); return false } catch { return true }
    `, request)
    assert.equal(blocked, true, 'a third run in another tab must not acquire a slot')
    await page.evaluate(`await pine.cancel(input); owned = owned.filter(id => id !== input);`, ids[0])
    const replacement = await other.evaluate(`const run = await pine.run(input); owned.push(run.id); return run.status;`, request)
    assert.equal(replacement, 'loading')
  } finally {
    await page.evaluate(cancelOwned); await other.evaluate(cancelOwned)
    await page.close(); await other.close()
  }
})

test('browser lifecycle: failed Pine storage upgrade preserves genuine v1 data and retries', options, async () => {
  const { context, page, value } = await legacyPage()
  const rollback = await page.evaluate(`
    const original = IDBObjectStore.prototype.put;
    IDBObjectStore.prototype.put = function(...args) {
      if (this.transaction.mode === 'versionchange') throw new DOMException('Injected quota failure', 'QuotaExceededError');
      return original.apply(this, args);
    };
    let failed = false;
    try { await (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns.getRun(input.run.id) } catch { failed = true }
    IDBObjectStore.prototype.put = original;
    const old = await (await import('/test/fixtures/browser-history/browserStore.v1.ts')).browserRecord('pine-run:' + input.run.id);
    return { failed, preserved: JSON.stringify(old) === JSON.stringify(input) };
  `, value)
  assert.deepEqual(rollback, { failed: true, preserved: true })
  await page.close()
  const reopened = await (await browser()).page(context)
  const result = await reopened.evaluate(`return await (await import('/src/modules/chartWorkspace/browserPineRuns.ts')).browserPineRuns.records(input, 'equity', 12000, 100);`, value.run.id)
  assert.deepEqual(result.items, value.result.equity.slice(12000))
  await reopened.close()
})

test('backup import rolls documents, research, reports and selections back together on quota failure', options, async () => {
  const instance = await browser(), page = await instance.page(await instance.context()), report = await historicalRun()
  try {
    const result = await page.evaluate(`
      const {createBrowserResearchApi}=await import('/src/modules/research/browserResearch.ts');const api=createBrowserResearchApi({});
      const {browserWorkspaceDocuments:documents}=await import('/src/modules/chartWorkspace/api.ts');
      const backup=await import('/src/modules/chartWorkspace/browserDataBackup.ts');
      const {browserPineStore}=await import('/src/modules/personal/browserStore.ts');
      const {readDraft,writeDraft}=await import('/src/modules/chartWorkspace/drafts.ts');
      await api.createWatchlist({name:'Current'});await writeDraft('last-layout','current-layout');
      const data=await backup.exportBrowserData(),date=new Date().toISOString();
      data.documents.push({kind:'scripts',document:{id:'incoming-script',name:'Incoming',data:{source:'plot(close)'},version:1,updated_at:Date.now(),readonly:false}});
      data.records.research.watchlists.push({id:'incoming-list',name:'Incoming',description:'',position:1,version:1,createdAt:date,updatedAt:date,archivedAt:null});
      data.records['pine-run:'+input.run.id]=input;data.selection.layout='incoming-layout';
      const original=IDBObjectStore.prototype.put;let rejected=false;
      IDBObjectStore.prototype.put=function(...args){if(this.name==='pine-runs')throw new DOMException('controlled quota','QuotaExceededError');return original.apply(this,args)};
      try{await backup.importBrowserData(JSON.stringify(data))}catch{rejected=true}finally{IDBObjectStore.prototype.put=original}
      const rolledBack={rejected,scripts:(await documents.list('scripts')).length,lists:(await api.getWorkbench()).watchlists.length,runs:(await browserPineStore.list()).length,selection:await readDraft('last-layout')};
      await backup.importBrowserData(JSON.stringify(data));await backup.importBrowserData(JSON.stringify(data));
      return {rolledBack,restored:{scripts:(await documents.list('scripts')).length,lists:(await api.getWorkbench()).watchlists.length,runs:(await browserPineStore.list()).length,selection:await readDraft('last-layout')}};
    `, report)
    assert.deepEqual(result, { rolledBack: { rejected: true, scripts: 0, lists: 1, runs: 0, selection: 'current-layout' }, restored: { scripts: 1, lists: 2, runs: 1, selection: 'incoming-layout' } })
  } finally { await page.close() }
})

test('genuine v1 research migrates to indexed entities and polling never reads its event history', options, async () => {
  const instance=await browser(),page=await instance.page(await instance.context())
  try {
    const result=await page.evaluate(`
      const date='2026-01-01T00:00:00.000Z';
      const state={watchlists:[{id:'list',name:'Kept',description:'',position:0,version:1,createdAt:date,updatedAt:date,archivedAt:null}],
        items:[{id:'item',watchlistId:'list',symbol:'BTC/USDT',assetClass:'crypto',displayName:'BTC',thesis:'Kept',targetPrice:null,invalidationPrice:null,tags:[],sourceContext:{},position:0,version:1,createdAt:date,updatedAt:date,archivedAt:null}],
        notes:[{id:'note',watchItemId:'item',symbol:'BTC/USDT',kind:'thesis',title:'Kept note',content:'Original content',snapshot:{},version:1,occurredAt:date,createdAt:date,updatedAt:date,archivedAt:null}],alerts:[],screeners:[],screenerRuns:[],
        events:Array.from({length:1000},(_,i)=>({id:'event-'+String(i).padStart(4,'0'),entityType:'note',entityId:'note',symbol:'BTC/USDT',kind:'note_created',title:'Old',body:'',payload:{},occurredAt:date,createdAt:date,acknowledgedAt:null}))};
      const old=await import('/test/fixtures/browser-history/browserStore.v1.ts');await old.restoreBrowserRecords({research:state});
      const {createBrowserResearchApi,evaluateBrowserAlerts}=await import('/src/modules/research/browserResearch.ts');const api=createBrowserResearchApi({});
      const notes=await api.listNotes('BTC/USDT');
      await api.createAlert({symbol:'BTC/USDT',name:'Price',metric:'price',operator:'gt',threshold:100,configuration:{chartSymbolId:'binance:spot:BTCUSDT',once:true},notificationChannels:['in_app']});
      let eventRows=0,blobReads=0;const original=IDBObjectStore.prototype.getAll,originalGet=IDBObjectStore.prototype.get;
      IDBObjectStore.prototype.getAll=function(...args){const request=original.apply(this,args);if(this.name==='research-events')request.addEventListener('success',()=>{eventRows+=request.result.length});return request};
      IDBObjectStore.prototype.get=function(...args){if(this.name==='records'&&args[0]==='research')blobReads++;return originalGet.apply(this,args)};
      window.fetch=async()=>new Response(JSON.stringify([{id:'binance:spot:BTCUSDT',price:200}]));
      const evaluated=await evaluateBrowserAlerts();IDBObjectStore.prototype.getAll=original;IDBObjectStore.prototype.get=originalGet;
      const db=await import('/src/modules/personal/browserDatabase.ts');const blob=await db.personalTransaction(['records'],'readonly',tx=>db.idbValue(tx.objectStore('records').get('research')));
      const events=await api.listEvents('',false,20);
      return {note:notes.items[0].content,totalNotes:notes.total,triggered:evaluated.triggeredCount,eventRows,blobReads,blobRemoved:blob===undefined,events:events.total,page:events.items.length};
    `)
    assert.deepEqual(result,{note:'Original content',totalNotes:1,triggered:1,eventRows:0,blobReads:0,blobRemoved:true,events:1002,page:20})
  } finally {await page.close()}
})

test('legacy documents, historical revisions, tombstones and drafts migrate without the API', options, async()=>{
  const instance=await browser(),page=await instance.page(await instance.context())
  try {
    const result=await page.evaluate(`
      const open=(name,upgrade)=>new Promise((resolve,reject)=>{const request=indexedDB.open(name,1);request.onupgradeneeded=()=>upgrade(request.result);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error)});
      const legacy=await open('opentrading-personal-data',db=>{db.createObjectStore('documents',{keyPath:['kind','id']}).createIndex('kind','kind');db.createObjectStore('revisions',{keyPath:['kind','id','version']});db.createObjectStore('metadata')});
      const doc={id:'mine',name:'My script',data:{source:'plot(close)'},version:2,updated_at:1,readonly:false};
      await new Promise((resolve,reject)=>{const tx=legacy.transaction(['documents','revisions','metadata'],'readwrite');tx.objectStore('documents').put({kind:'scripts',id:'mine',document:doc,archived:false});tx.objectStore('revisions').put({kind:'scripts',id:'mine',version:1,document:{...doc,version:1,data:{source:'plot(open)'}}});tx.objectStore('metadata').put(true,'migrated:scripts');tx.objectStore('metadata').put(1,'deleted:scripts:removed');tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error)});legacy.close();
      const drafts=await open('opentrading-chart-workspace',db=>db.createObjectStore('drafts'));
      await new Promise((resolve,reject)=>{const tx=drafts.transaction('drafts','readwrite');tx.objectStore('drafts').put({source:'unsaved source',dirty:true},'pine:mine');tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error)});drafts.close();
      const {browserWorkspaceDocuments:documents}=await import('/src/modules/chartWorkspace/api.ts');const {readDraft}=await import('/src/modules/chartWorkspace/drafts.ts');
      let deletedStatus;try{await documents.save('scripts','removed',{name:'Late save',data:{source:'plot(close)'},expected_version:0})}catch(error){deletedStatus=error.status}
      return {source:(await documents.get('scripts','mine')).data.source,previous:(await documents.get('scripts','mine',1)).data.source,draft:await readDraft('pine:mine'),deletedStatus};
    `)
    assert.deepEqual(result,{source:'plot(close)',previous:'plot(open)',draft:{source:'unsaved source',dirty:true},deletedStatus:404})
  } finally {await page.close()}
})
