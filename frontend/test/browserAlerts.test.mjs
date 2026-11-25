import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { browserSession } from './helpers/browserSession.mjs'

let session
const options = { timeout: 45000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER }
after(async () => { await session?.close() })
const prepare = `
  const {createBrowserResearchApi,evaluateBrowserAlerts}=await import('/src/modules/research/browserResearch.ts');
  const api=createBrowserResearchApi({});
  const db=await import('/src/modules/personal/browserDatabase.ts');
  const count=async kind=>db.personalTransaction(['research-'+kind],'readonly',tx=>db.idbValue(tx.objectStore('research-'+kind).count()));
  const rule=(configuration={})=>({symbol:'BTC/USDT',name:'BTC price',metric:'price',operator:'crosses',threshold:100,
    enabled:true,cooldownMinutes:1,notificationChannels:['in_app','sound'],configuration:{chartSymbolId:'binance:spot:BTCUSDT',initialPrice:90,once:true,...configuration}});
  const quotes=()=>Promise.resolve(new Response(JSON.stringify([{id:'binance:spot:BTCUSDT',price:105}])));
  const waitFor=async predicate=>{const end=performance.now()+3000;while(!predicate()){if(performance.now()>end)throw new Error('Pending quote did not start');await new Promise(resolve=>setTimeout(resolve,0))}};
  window.fetch=quotes;
`
async function run(body) {
  session ??= await browserSession()
  const page=await session.page(await session.context())
  try { return await page.evaluate(prepare+body) } finally {await page.close()}
}

test('a browser one-shot alert is physically removed while its notification survives',options,async()=>{
  const result=await run(`const alert=await api.createAlert(rule());const first=await evaluateBrowserAlerts();const events=(await api.listEvents()).items;
    return {triggered:first.triggeredCount,stored:await count('alerts'),events:events.length,sameEntity:events[0].entityId===alert.id,channels:events[0].payload.notificationChannels,again:(await evaluateBrowserAlerts()).triggeredCount};`)
  assert.deepEqual(result,{triggered:1,stored:0,events:1,sameEntity:true,channels:['in_app','sound'],again:0})
})
test('explicit repeating rules stay active and paused rules are preserved',options,async()=>{
  assert.deepEqual(await run(`const repeat=await api.createAlert(rule({once:false}));const paused=await api.createAlert({...rule(),enabled:false});await evaluateBrowserAlerts();
    const rows=(await api.getWorkbench()).alerts;return {repeat:rows.find(row=>row.id===repeat.id).enabled,paused:rows.find(row=>row.id===paused.id).enabled,pausedTrigger:rows.find(row=>row.id===paused.id).lastTriggeredAt,stored:await count('alerts')};`),
    {repeat:true,paused:false,pausedTrigger:null,stored:2})
})
test('reactive form and chart objects can be persisted and edited in IndexedDB',options,async()=>{
  assert.deepEqual(await run(`const {reactive}=await import('/test/helpers/vuePage.ts');const body=reactive(rule());const alert=await api.createAlert(body);
    const saved=await api.updateAlert(alert.id,reactive({...rule(),threshold:110,expectedVersion:alert.version}));return {threshold:saved.threshold,configuration:saved.configuration};`),
    {threshold:110,configuration:{chartSymbolId:'binance:spot:BTCUSDT',initialPrice:90,once:true}})
})
test('delete checks revisions, removes the stored rule, and a stale evaluation cannot recreate it',options,async()=>{
  assert.deepEqual(await run(`const alert=await api.createAlert(rule());let status;try{await api.deleteAlert(alert.id,2)}catch(error){status=error.status}
    let respond;window.fetch=()=>new Promise(resolve=>{respond=resolve});const evaluating=evaluateBrowserAlerts();await waitFor(()=>respond);
    await api.deleteAlert(alert.id,1);respond(await quotes());return {status,triggered:(await evaluating).triggeredCount,stored:await count('alerts')};`),{status:409,triggered:0,stored:0})
})
test('an edit during quote loading invalidates the older evaluation',options,async()=>{
  assert.deepEqual(await run(`const alert=await api.createAlert(rule());let respond;window.fetch=()=>new Promise(resolve=>{respond=resolve});
    const evaluating=evaluateBrowserAlerts();await waitFor(()=>respond);await api.updateAlert(alert.id,{...rule(),threshold:200,expectedVersion:1});respond(await quotes());
    return {triggered:(await evaluating).triggeredCount,threshold:(await api.getWorkbench()).alerts[0].threshold};`),{triggered:0,threshold:200})
})
test('deleting a browser research list removes its linked records and keeps other lists',options,async()=>{
  assert.deepEqual(await run(`const list=await api.createWatchlist({name:'Delete'}),other=await api.createWatchlist({name:'Keep'});
    const item=await api.createItem({watchlistId:list.id,symbol:'BTC/USDT'});await api.createNote({watchItemId:item.id,symbol:item.symbol,title:'Linked',content:'Private'});await api.createAlert({...rule(),watchItemId:item.id});
    let status;try{await api.deleteWatchlist(list.id,2)}catch(error){status=error.status}await api.deleteWatchlist(list.id,1);const saved=await api.getWorkbench();
    return {status,kept:saved.watchlists.length===1&&saved.watchlists[0].id===other.id,items:await count('items'),notes:await count('notes'),alerts:await count('alerts'),events:saved.events.every(row=>row.entityId===other.id)};`),
    {status:409,kept:true,items:0,notes:0,alerts:0,events:true})
})
test('browser item, note and screener deletion keep the parent list',options,async()=>{
  assert.deepEqual(await run(`const list=await api.createWatchlist({name:'Keep'}),item=await api.createItem({watchlistId:list.id,symbol:'BTC/USDT'});
    const note=await api.createNote({watchItemId:item.id,symbol:item.symbol,title:'Delete'});await api.deleteNote(note.id,1);const items=await count('items');await api.deleteItem(item.id,1);
    const screener=await api.createScreener({name:'Delete',filters:{}});await api.deleteScreener(screener.id,1);return {items,lists:await count('watchlists'),screeners:await count('screeners')};`),{items:1,lists:1,screeners:0})
})
test('browser research rejects duplicate identities, missing parents and invalid command fields atomically',options,async()=>{
  assert.deepEqual(await run(`const list=await api.createWatchlist({name:'Probe'}),a=await api.createItem({watchlistId:list.id,symbol:'BTC/USDT'}),b=await api.createItem({watchlistId:list.id,symbol:'ETH/USDT'});
    const statuses=[];for(const action of [()=>api.updateItem(b.id,{watchlistId:list.id,symbol:a.symbol,expectedVersion:b.version}),()=>api.createNote({symbol:a.symbol,watchItemId:'missing',title:'orphan'}),()=>api.createAlert({...rule(),operator:'between',secondaryThreshold:100}),()=>api.createItem({watchlistId:list.id,symbol:'XRP/USDT',tags:['x'.repeat(41)]})]){try{await action();statuses.push(200)}catch(error){statuses.push(error.status)}}
    return {statuses,items:await count('items'),notes:await count('notes'),alerts:await count('alerts')};`),{statuses:[409,404,422,422],items:2,notes:0,alerts:0})
})
test('cancelling a hung quote frees the cross-tab evaluation lock and allows the next poll',options,async()=>{
  assert.deepEqual(await run(`await api.createAlert(rule());let requested=false;window.fetch=(url,init)=>{requested=!!init.signal;return new Promise(()=>{})};
    const controller=new AbortController();const first=evaluateBrowserAlerts(controller.signal).then(()=>false,()=>true);await waitFor(()=>requested);controller.abort();const cancelled=await first;
    const released=await navigator.locks.request('opentrading:alert-evaluation',{ifAvailable:true},lock=>!!lock);window.fetch=quotes;
    return {requested,cancelled,released,retry:(await evaluateBrowserAlerts()).triggeredCount};`),{requested:true,cancelled:true,released:true,retry:1})
})

test('the real provider repairs chart history without filling live paper orders from that history',options,async()=>{
  assert.deepEqual(await run(`
    const {ref,shallowRef}=await import('/test/helpers/vuePage.ts');
    const {chartApi}=await import('/src/modules/chartWorkspace/api.ts');
    const {OpenTradingProvider}=await import('/src/modules/chartWorkspace/provider.ts');
    const {createWorkspacePaper}=await import('/src/modules/chartWorkspace/workspacePaper.ts');
    const sockets=[];class Socket{static OPEN=1;readyState=0;sent=[];constructor(){sockets.push(this)}send(value){this.sent.push(JSON.parse(value))}close(){this.readyState=3}}window.WebSocket=Socket;
    const info={id:'binance:spot:BTCUSDT',symbol:'BTCUSDT',timeframes:['1m','1h'],metadata:{mintick:.01}};
    chartApi.quotes=async()=>[{id:info.id,price:100}];const provider=new OpenTradingProvider(()=>{});provider.catalog=[info];
    let repaired=0;provider.subscribe(info.id,'1m',()=>repaired++);
    const paper=createWorkspacePaper({workspace:shallowRef({active:{}}),symbols:ref([info]),symbolId:ref(info.id),timeframe:ref('1h'),subscribe:(id,tf,cb)=>provider.subscribeQuotes(id,tf,cb)});
    await paper.place(1,'limit',95);const socket=sockets[0];socket.readyState=1;socket.onopen();const subscription=socket.sent.at(-1);let sequence=0;
    const emit=(price,live,observed_at)=>socket.onmessage({data:JSON.stringify({type:'bar',symbol:info.id,timeframe:'1m',generation:subscription.generation,sequence:++sequence,live,observed_at,bar:{time:Date.now()-120000,closeTime:Date.now()-60000,open:price,high:price,low:price,close:price,volume:1,closed:true}})});
    emit(90,false,Date.now()-60000);const ignoredHistory=!!paper.account.pending;
    emit(94,true,Date.now()+1);emit(80,true,Date.now()-60000);
    const result={ignoredHistory,fill:paper.account.position?.price,latest:paper.account.price,repaired};paper.dispose();provider.destroy();return result;
  `),{ignoredHistory:true,fill:94,latest:94,repaired:3})
})
