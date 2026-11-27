import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import * as vue from 'vue'

function load(name, modules = {}) {
  const exports = {}
  const source = fs.readFileSync(new URL('../src/modules/chartWorkspace/' + name + '.ts', import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  new Function('require', 'exports', code)(id => id === 'vue' ? vue : modules[id], exports)
  return exports
}
const model = load('replayModel')
const sizing = load('replayQuantity')
const { formatQuantity, quantityAtPercent, quantityPercent, quantityForAmount } = sizing
const { ReplayPacer, ReplayAccount, aggregateMinute, periodStart, periodEnd, replayDateTime, replayDateInput } = model
const minute = (time, open = 100, high = 104, low = 98, close = 102) => ({ time, closeTime: time + 60000, open, high, low, close, volume: 2, closed: true })

test('index hour aggregation keeps the half-hour boundary used by native history', () => {
  const start=Date.UTC(2026,10,25,14,30), offset=30*60000
  assert.equal(periodStart(start+10*60000,'1h',offset),start)
  assert.equal(periodEnd(start+10*60000,'1h',offset),start+3600000)
  const current=aggregateMinute(undefined,minute(start+10*60000),'1h',offset)
  assert.equal(current.time,start)
  assert.equal(current.closeTime,start+3600000)
  assert.equal(current.closed,false)
})

test('quantity sizing uses plain decimals and rounds percentages down to the contract step', () => {
  assert.equal(formatQuantity(1e-8), '0.00000001')
  assert.equal(formatQuantity(1.25e-7), '0.000000125')
  assert.equal(formatQuantity(1e21), '1000000000000000000000')
  assert.equal(formatQuantity(NaN), '')
  assert.equal(quantityAtPercent(1, 25, 0.001), 0.25)
  assert.equal(quantityAtPercent(0.03, 50, 0.01), 0.01)
  assert.equal(quantityAtPercent(1.23, 50, 0.25), 0.5)
  assert.equal(quantityAtPercent(3e-8, 50, 1e-8), 1e-8)
  assert.equal(quantityAtPercent(0.03, 100, 0.01), 0.03)
  assert.equal(quantityAtPercent(0.03, 0, 0.01), 0)
  assert.equal(quantityPercent(0.25, 1), 25)
  assert.equal(quantityPercent(NaN, 1), 0)
})

test('quote amounts convert at the requested price without exceeding the budget or losing decimal steps', () => {
  assert.equal(quantityForAmount(1000, 60000, 0.00001), 0.01666)
  assert.equal(quantityForAmount(0.3, 0.1, 0.1), 3)
  assert.equal(quantityForAmount(12.5, 4, 0.25), 3)
  assert.equal(quantityForAmount(1, 60000, 0.0001), 0)
  assert.equal(quantityForAmount(NaN, 100), 0)
  assert.equal(quantityForAmount(100, 0), 0)
  for (const [amount, price, step] of [[1000,67366.11,0.00001],[100,102,0.001],[500,1800.25,0.0001]]) {
    const size=quantityForAmount(amount,price,step)
    assert.ok(size*price<=amount+Number.EPSILON*amount)
    assert.ok((size+step)*price>amount)
  }
})

test('candle pacing schedules one bar per second at 1x and preserves the waiting fraction across pause and speed changes', () => {
  const clock = new ReplayPacer()
  clock.reset(0);clock.play(0)
  assert.equal(clock.delay(0),1000);assert.equal(clock.delay(500),500)
  clock.setSpeed(2,500);assert.equal(clock.delay(500),250)
  clock.pause(625);assert.equal(clock.delay(999999),125)
  clock.play(1000000);assert.equal(clock.delay(1000125),0)
  clock.reset(1000125);assert.equal(clock.delay(1000125),500)
  assert.equal(clock.delay(9000000),0)
  clock.reset(9000000);assert.equal(clock.delay(9000000),500)
})

test('forming five-minute candle uses only consumed minutes and closes on the fifth update', () => {
  let candle
  for (let i = 0; i < 5; i++) {
    candle = aggregateMinute(candle, minute(i * 60000, 100, 104 + i, 98 - i, 102 + i), '5m')
    assert.equal(candle.high, 104 + i)
    assert.equal(candle.low, 98 - i)
    assert.equal(candle.close, 102 + i)
    assert.equal(candle.volume, (i + 1) * 2)
    assert.equal(candle.closed, i === 4)
  }
  const next = aggregateMinute(candle, minute(300000, 110, 111, 109, 110), '5m')
  assert.equal(next.open, 110); assert.equal(next.volume, 2); assert.equal(next.closed, false)
  assert.equal(periodStart(Date.UTC(2024, 1, 19), '1w'), Date.UTC(2024, 1, 19))
  assert.equal(periodEnd(Date.UTC(2024, 1, 15), '1M'), Date.UTC(2024, 2, 1))
})

test('date selection follows the chart timezone rather than the computer timezone', () => {
  assert.equal(replayDateTime('2026-11-20T12:00','Asia/Shanghai'), Date.UTC(2026,10,20,4))
  assert.equal(replayDateTime('2026-11-20T12:00','America/New_York'), Date.UTC(2026,10,20,17))
  assert.equal(replayDateInput(Date.UTC(2026,6,20,16),'America/New_York'),'2026-07-20T12:00')
  assert.ok(Number.isNaN(replayDateTime('2026-03-08T02:30','America/New_York')))
})

test('chart orders can be moved before entry; TP/SL can be repeatedly moved without moving the filled entry', () => {
  const account = new ReplayAccount(); account.reset(100)
  account.prepare(1, 'limit', 95, 2, 0)
  assert.equal(account.move('entry', 96, 0), true)
  const tp=account.addExit(110,0),sl=account.addExit(90,0); account.submit(0)
  account.consume(minute(0, 100, 103, 94, 101))
  assert.equal(account.position.price, 96)
  assert.equal(account.move('entry', 97, 60000), false)
  assert.equal(account.move(sl, 98, 60000), true)
  assert.equal(account.move(sl, 99, 60000), true)
  assert.equal(account.move(tp, 112, 60000), true)
  assert.equal(account.move(tp, 90, 60000), false)
  account.consume(minute(60000, 101, 108, 98, 105))
  assert.equal(account.trades[0].exit, 99)
  assert.equal(account.realized, 6)
  assert.equal(account.position, undefined)
})

test('one-click orders fill at market or enter the pending book without leaving an unsubmitted draft',()=>{
  for(const side of [1,-1]){
    const account=new ReplayAccount();account.reset(100)
    assert.equal(account.place(side,'market',100,2,0),true)
    assert.equal(account.draft,undefined);assert.equal(account.pending,undefined);assert.equal(account.position.quantity,2)
    const position=account.position
    assert.equal(account.place(side,'market',100,3,0),false);assert.equal(account.position,position)
    account.close(1000)
    assert.equal(account.place(side,'limit',100-side*5,3,1000),true)
    assert.equal(account.draft,undefined);assert.equal(account.position,undefined);assert.equal(account.pending.quantity,3)
    assert.equal(account.move('entry',100-side*6,1000),true)
    account.cancel('entry')
    assert.equal(account.place(side,'market',100,0,1000),false)
    account.price=0;assert.equal(account.place(side,'market',100,1,1000),false)
    assert.equal(account.draft,undefined);assert.equal(account.pending,undefined);assert.equal(account.position,undefined)
  }
})

test('long/short P&L, bracket cancellation, gaps and same-minute ambiguity are deterministic', () => {
  const account = new ReplayAccount(); account.reset(100)
  account.prepare(-1, 'market', 100, 3, 0); account.addExit(90,0); account.addExit(105,0); account.submit(0)
  account.consume(minute(0, 100, 106, 89, 95))
  assert.equal(account.trades[0].reason, 'sl'); assert.equal(account.realized, -15)
  assert.equal(account.position, undefined)
  account.prepare(1, 'market', 95, 2, 60000); account.addExit(90,60000); account.submit(60000)
  account.consume(minute(60000, 85, 88, 83, 87))
  assert.equal(account.trades[1].exit, 85); assert.equal(account.realized, -35)
  account.prepare(-1, 'limit', 110, 1, 120000); account.submit(120000); account.cancel('entry')
  account.consume(minute(120000, 120, 125, 115, 122)); assert.equal(account.position, undefined)
})

test('a stop moved in the middle of a minute cannot use that minute’s earlier wick', () => {
  const account = new ReplayAccount(); account.reset(100)
  account.prepare(1, 'market', 100, 1, 0); const sl=account.addExit(90,0); account.submit(0)
  account.move(sl, 99, 30000)
  account.consume(minute(0, 100, 105, 95, 103))
  assert.ok(account.position)
  account.consume(minute(60000, 103, 104, 98, 102))
  assert.equal(account.trades[0].exit, 99)
})

test('a limit created mid-minute cannot reuse the earlier wick to stop a new position', () => {
  const account=new ReplayAccount();account.reset(100)
  account.prepare(1,'limit',95,1,30000);account.addExit(91,30000);account.submit(30000)
  account.consume(minute(0,100,104,89,94))
  assert.equal(account.position.price,94)
  assert.equal(account.trades.length,0)
  account.consume(minute(60000,94,96,90,93))
  assert.equal(account.trades[0].exit,91)
})

test('new exit direction follows current price; profitable long and short stops can cross entry',()=>{
  for(const side of [1,-1]){
    const account=new ReplayAccount();account.reset(100);account.prepare(side,'market',100,2,0);account.submit(0)
    const stop=account.addExit(100-side*10,0)
    account.consume(minute(0,100,side===1?122:101,side===1?99:78,100+side*20))
    assert.equal(account.move(stop,100+side*10,60000),true)
    assert.equal(account.move(stop,100+side*15,60000),true)
    assert.equal(account.position.exits.find(exit=>exit.target===stop).kind,'sl')
    const newStop=account.addExit(100+side*12,60000,0.5),target=account.addExit(100+side*30,60000,1)
    assert.equal(account.position.exits.find(exit=>exit.target===newStop).kind,'sl')
    assert.equal(account.position.exits.find(exit=>exit.target===target).kind,'tp')
    assert.equal(account.move(stop,100+side*21,60000),false)
    assert.equal(account.position.exits.find(exit=>exit.target===stop).price,100+side*15)
    assert.equal(account.addExit(account.price,60000),undefined)
  }
})

test('dragging ordinary protection needs no quantity and updates the existing whole-position level',()=>{
  const account=new ReplayAccount();account.reset(100);account.prepare(1,'market',100,4,0);account.submit(0)
  const stop=account.addExit(95,0),profit=account.addExit(110,0)
  const partial=account.addExit(108,0,1)
  assert.equal(account.addExit(94,1000),stop)
  assert.equal(account.addExit(112,1000),profit)
  assert.equal(account.position.exits.length,3)
  assert.equal(account.position.exits.find(exit=>exit.target===stop).quantity,undefined)
  assert.equal(account.position.exits.find(exit=>exit.target===partial).quantity,1)
  account.consume(minute(60000,100,109,99,108))
  assert.equal(account.position.quantity,3)
  assert.equal(account.position.exits.find(exit=>exit.target===stop).quantity,undefined)
  assert.equal(account.position.exits.find(exit=>exit.target===profit).quantity,undefined)
})

test('multiple partial take profits retain the remaining position and full stop protection',()=>{
  const account=new ReplayAccount();account.reset(100);account.prepare(1,'market',100,10,0)
  account.addExit(120,0,3);account.addExit(110,0,2);const stop=account.addExit(95,0);account.submit(0)
  account.consume(minute(0,101,112,100,111))
  assert.equal(account.position.quantity,8);assert.equal(account.realized,20)
  assert.equal(account.position.exits.length,2);assert.equal(account.position.exits.find(exit=>exit.target===stop).quantity,undefined)
  account.consume(minute(60000,111,121,109,120))
  assert.equal(account.position.quantity,5);assert.equal(account.realized,80)
  assert.equal(account.move(stop,112,120000),true)
  account.consume(minute(120000,120,121,110,113))
  assert.equal(account.position,undefined);assert.equal(account.realized,140)
  assert.deepEqual(account.trades.map(trade=>[trade.quantity,trade.reason]),[[2,'tp'],[3,'tp'],[5,'sl']])
})

test('partial stops preserve other exits; exit quantities never exceed the remaining position',()=>{
  const account=new ReplayAccount();account.reset(100);account.prepare(-1,'market',100,5,0)
  account.addExit(105,0,2);const farther=account.addExit(110,0,5);const target=account.addExit(90,0);account.submit(0)
  account.consume(minute(0,100,106,99,104))
  assert.equal(account.position.quantity,3);assert.equal(account.realized,-10)
  assert.equal(account.position.exits.find(exit=>exit.target===farther).quantity,3)
  assert.equal(account.position.exits.find(exit=>exit.target===target).quantity,undefined)
  account.consume(minute(60000,104,105,89,91))
  assert.equal(account.position,undefined);assert.equal(account.realized,20)
  assert.deepEqual(account.trades.map(trade=>trade.quantity),[2,3])
})

test('same-minute partial fills use nearest levels first, stop first on ambiguity, and gap prices',()=>{
  for(const side of [1,-1]){
    const account=new ReplayAccount();account.reset(100);account.prepare(side,'market',100,4,0)
    account.addExit(100-side*10,0,1);account.addExit(100-side*5,0,1)
    account.addExit(100+side*20,0);account.addExit(100+side*10,0,1);account.submit(0)
    account.consume(minute(0,100,125,75,100))
    assert.deepEqual(account.trades.map(trade=>[trade.exit,trade.quantity,trade.reason]),[[100-side*5,1,'sl'],[100-side*10,1,'sl'],[100+side*10,1,'tp'],[100+side*20,1,'tp']])
    assert.equal(account.realized,15);assert.equal(account.position,undefined)
    account.prepare(side,'market',100,3,60000);account.addExit(100+side*10,60000,1);account.addExit(100+side*20,60000);account.submit(60000)
    const opening=100+side*25
    account.consume(minute(60000,opening,opening+1,opening-1,opening))
    assert.equal(account.trades.at(-1).exit,opening);assert.equal(account.trades.at(-2).exit,opening)
    assert.equal(account.position,undefined)
  }
})

test('partial exit edits are atomic and cannot retrospectively use an earlier wick',()=>{
  const account=new ReplayAccount();account.reset(100);account.prepare(1,'market',100,2,0);account.submit(0)
  const target=account.addExit(110,0,1)
  assert.equal(account.updateExit(target,115,3,1000),false)
  assert.equal(account.updateExit(target,95,1,1000),false)
  assert.deepEqual(account.position.exits[0],{target,kind:'tp',price:110,quantity:1,since:0})
  assert.equal(account.updateExit(target,108,0.5,30000),true)
  account.consume(minute(0,100,112,99,105))
  assert.equal(account.trades.length,0)
  account.consume(minute(60000,105,109,104,108))
  assert.equal(account.trades[0].quantity,0.5);assert.equal(account.position.quantity,1.5)
  const stop=account.addExit(104,120000,1)
  assert.equal(account.updateExit(stop,104,1.5,150000),true)
  account.consume(minute(120000,108,110,103,106));assert.equal(account.trades.length,1)
  account.consume(minute(180000,106,107,103,105));assert.equal(account.position,undefined)
})

function paperFixture(quote){
  const btc={id:'binance:spot:BTCUSDT',symbol:'BTCUSDT',timeframes:['1m','5m'],metadata:{mintick:0.01}},eth={...btc,id:'binance:spot:ETHUSDT',symbol:'ETHUSDT'}
  const symbolId=vue.ref(btc.id),timeframe=vue.ref('5m'),subscriptions=new Map(),unsubscribed=[]
  const cell={},workspace=vue.shallowRef({active:cell})
  const {createWorkspacePaper}=load('workspacePaper',{'./replayModel':model,'./replayQuantity':sizing,'./locale':{cw:key=>key},'./api':{chartApi:{quotes:quote??(async ids=>[{id:ids[0],price:100}])}}})
  const paper=createWorkspacePaper({workspace,symbols:vue.ref([btc,eth]),symbolId,timeframe,subscribe:(id,tf,callback)=>{subscriptions.set(id,{tf,callback});return()=>unsubscribed.push(id)}})
  return{paper,btc,eth,symbolId,timeframe,workspace,subscriptions,unsubscribed}
}

test('live paper orders follow new quotes and never fill using earlier candle wicks',async()=>{
  const {paper,btc,subscriptions}=paperFixture()
  try{
    paper.amount.value=190
    assert.equal(await paper.place(1,'limit',95),true)
    assert.equal(paper.active.value,true);assert.equal(paper.account.price,100);assert.equal(paper.account.draft,undefined);assert.ok(paper.account.pending)
    const update=price=>subscriptions.get(btc.id).callback({price,observedAt:Date.now()})
    update(100);assert.ok(paper.account.pending);assert.equal(paper.account.position,undefined)
    update(94);assert.equal(paper.account.position.price,94);assert.equal(paper.account.position.quantity,2)
    update(105);paper.account.addExit(110,Date.now(),0.5);paper.account.addExit(101,Date.now())
    update(111);assert.equal(paper.account.position.quantity,1.5);assert.equal(paper.account.trades[0].exit,111)
    update(100);assert.equal(paper.account.position,undefined);assert.equal(paper.account.trades[1].quantity,1.5)
    assert.equal(paper.account.realized,17.5)
  }finally{paper.dispose()}
})

test('live paper positions survive period and symbol changes and keep receiving their own market quotes',async()=>{
  const {paper,btc,eth,symbolId,timeframe,subscriptions,unsubscribed}=paperFixture()
  try{
    paper.amount.value=100
    await paper.place(1,'market',100)
    const btcAccount=paper.account,position=paper.account.position
    timeframe.value='1m';assert.equal(paper.account,btcAccount);assert.equal(paper.account.position,position)
    symbolId.value=eth.id;assert.equal(paper.active.value,false);assert.equal(paper.account.position,undefined)
    await paper.place(-1,'market',100)
    subscriptions.get(btc.id).callback({price:104,observedAt:Date.now()})
    subscriptions.get(eth.id).callback({price:98,observedAt:Date.now()})
    assert.equal(paper.account.unrealized,2)
    symbolId.value=btc.id;assert.equal(paper.account,btcAccount);assert.equal(paper.account.position,position);assert.equal(paper.account.unrealized,4)
    assert.equal(subscriptions.size,2);assert.equal(subscriptions.get(btc.id).tf,'1m')
  }finally{paper.dispose()}
  assert.deepEqual(unsubscribed.sort(),[btc.id,eth.id].sort())
})

test('live paper quote failures and late responses do not create orders for a different selected market',async()=>{
  let release
  const fixture=paperFixture(async ids=>{await new Promise(resolve=>{release=resolve});return[{id:ids[0],price:100}]})
  try{
    const preparing=fixture.paper.place(1,'limit',95)
    fixture.symbolId.value=fixture.eth.id;release();assert.equal(await preparing,false)
    assert.equal(fixture.paper.active.value,false);assert.equal(fixture.subscriptions.size,0)
    fixture.symbolId.value=fixture.btc.id;assert.equal(fixture.paper.active.value,false)
  }finally{fixture.paper.dispose()}
  const unavailable=paperFixture(async ids=>[{id:ids[0],error:'offline'}])
  try{assert.equal(await unavailable.paper.place(1,'market',100),false);assert.equal(unavailable.paper.active.value,false);assert.equal(unavailable.paper.error.value,'offline')}
  finally{unavailable.paper.dispose()}
})

test('live paper cannot duplicate an existing order or recreate it after disposal',async()=>{
  let requests=0
  const {paper,subscriptions}=paperFixture(async ids=>{requests++;return[{id:ids[0],price:100}]})
  await paper.place(1,'limit',95)
  const order=paper.account.pending
  assert.equal(await paper.place(-1,'limit',110),false);assert.equal(paper.account.pending,order);assert.equal(requests,1)
  paper.dispose();assert.equal(await paper.place(1,'limit',95),false);assert.equal(subscriptions.size,1)
})

test('one-click live market orders use the current quote and the quantity selected at click time',async()=>{
  let release
  const {paper}=paperFixture(async ids=>{await new Promise(resolve=>{release=resolve});return[{id:ids[0],price:102}]})
  try{
    paper.amount.value=204
    const placing=paper.place(1,'market',0)
    paper.amount.value=918
    assert.equal(await paper.place(1,'market',0),false)
    release();assert.equal(await placing,true)
    assert.equal(paper.account.position.price,102);assert.equal(paper.account.position.quantity,2)
    assert.equal(paper.account.draft,undefined);assert.equal(paper.account.pending,undefined)
  }finally{paper.dispose()}
})

test('live paper keeps the quote amount fixed and uses market or limit price to determine the position size',async()=>{
  let price=200
  const {paper}=paperFixture(async ids=>[{id:ids[0],price}])
  try {
    paper.amount.value=100
    assert.equal(await paper.place(1,'market',0),true)
    assert.equal(paper.account.position.quantity,0.5)
    paper.account.close(Date.now())
    price=100
    assert.equal(await paper.place(1,'market',0),true)
    assert.equal(paper.account.position.quantity,1)
    paper.account.close(Date.now())
    price=200
    assert.equal(await paper.place(1,'limit',100),true)
    assert.equal(paper.account.pending.quantity,1)
    assert.equal(paper.account.pending.price,100)
    assert.equal(paper.amount.value,100)
  } finally {paper.dispose()}
})

test('replay series use verified market identities, paginate and clamp requests to known history', async () => {
  const spot={id:'binance:spot:BTCUSDT',symbol:'BTCUSDT',exchange:'binance',market:'spot'},perp={...spot,id:'binance:usdm:BTCUSDT',market:'usdm'}
  const requests=[]
  const {resolveReplaySymbol,loadReplaySeries}=load('replaySeries',{
    './provider':{fromVela:value=>value.replace(/^(opentrading|replay\d*):/,''),timeframes:{'1':'1m'}},
    './api':{chartApi:{async replayBars(query){requests.push(query);return{bars:Array.from({length:Math.min(query.limit,(query.end-query.start)/60000)},(_,i)=>minute(query.start+i*60000))}}}},
  })
  assert.equal(resolveReplaySymbol('BINANCE:BTCUSDT.P',[spot,perp],spot),perp)
  assert.equal(resolveReplaySymbol('BTCUSDT',[spot,perp],perp),perp)
  const rows=await loadReplaySeries(spot,'1',{from:0,to:3000*60000},1500*60000)
  assert.equal(rows.length,1500)
  assert.equal(requests.length,2)
  assert.ok(requests.every(query=>query.end===1500*60000&&query.limit<=1000))
  assert.equal(rows.at(-1).closeTime,1500*60000)
})

test('replay indicator history walks backward beyond the first page without duplicate or future candles', async () => {
  const symbol = { id: 'binance:spot:BTCUSDT' }, requests = [], source = Array.from({ length: 3000 }, (_, i) => minute(i * 60000))
  const { loadReplaySeries } = load('replaySeries', {
    './provider': { timeframes: { '1': '1m' } },
    './api': { chartApi: { async replayBars(query) {
      requests.push(query)
      return { bars: source.filter(bar => bar.closeTime <= query.end).slice(-query.limit) }
    } } },
  })
  const rows = await loadReplaySeries(symbol, '1', { limit: 2500, to: 4000 * 60000 }, 3000 * 60000)
  assert.equal(rows.length, 2500)
  assert.equal(rows[0].time, 500 * 60000)
  assert.equal(rows.at(-1).closeTime, 3000 * 60000)
  assert.equal(new Set(rows.map(bar => bar.time)).size, 2500)
  assert.deepEqual(requests.map(query => query.limit), [1000, 1000, 500])
})

test('replay provider reveals one minute at a time, emits forming candles, restores live and cancels stale loads', async () => {
  const previous = { document: globalThis.document, setInterval: globalThis.setInterval, clearInterval: globalThis.clearInterval }
  globalThis.document = { hidden: false, addEventListener() {}, removeEventListener() {} }
  globalThis.setInterval = () => 1; globalThis.clearInterval = () => {}
  const start = Date.UTC(2026, 0, 1), symbol = { id: 'binance:spot:BTCUSDT', symbol: 'BTCUSDT', timeframes: ['1m','5m'], metadata: {mintick: 0.01} }
  let provider, unsubscribe
  const emitted = [], switches = []
  const chart = { market: {bars: 1000}, renderer: {setWallClock() {}}, data: {registerProvider(_name, value) {provider=value}, async ready() {}},
    async setMarket(value) { switches.push(value); unsubscribe?.(); if(/^replay\d*:/.test(value.symbol)) unsubscribe=provider.subscribe('', '', bar=>emitted.push(bar)) } }
  const { createWorkspaceReplay } = load('workspaceReplay', {
    './replayModel': model, './replayQuantity': sizing, './locale': {cw: key=>key}, './provider': {fromVela: value=>value.replace(/^(opentrading|replay\d*):/,''),velaSymbol: value=>'opentrading:'+value,timeframes:{'5':'5m'}},
    './api': {chartApi: {async replayBars(query) {
      if (!('start' in query)) return {bars: [{...minute(start-300000), closeTime:start}],symbol}
      return {bars: Array.from({length:10},(_,i)=>minute(query.start+i*60000)),symbol}
    }}},
  })
  const r = createWorkspaceReplay({workspace:vue.shallowRef({active:{id:'c1',symbol:'opentrading:'+symbol.id,timeframe:'5',chart}}),symbols:vue.ref([symbol])})
  try {
    await r.start(start)
    assert.equal(r.active.value, true)
    assert.equal((await provider.getBars(symbol.id, '5', {})).at(-1).time, start-300000)
    await r.step()
    assert.equal(r.now.value,start+60000);assert.equal(emitted[0].closed,false)
    for(let i=1;i<5;i++)await r.step()
    assert.equal(r.now.value, start+300000)
    assert.equal(emitted.length, 5)
    assert.deepEqual(emitted.map(bar=>bar.closed), [false,false,false,false,true])
    assert.equal((await provider.getBars(symbol.id, '5', {})).at(-1).closeTime, start+300000)
    const identity=switches.at(-1).symbol
    await r.start(start)
    assert.notEqual(switches.at(-1).symbol,identity)
    assert.equal((await provider.getBars(symbol.id,'5',{})).at(-1).time,start-300000)
    await r.exit()
    assert.equal(switches.at(-1).symbol, 'opentrading:'+symbol.id)
    assert.equal(r.active.value, false)
  } finally { r.dispose(); Object.assign(globalThis, previous) }
})

async function replayFixture(task, reply, options = {}) {
  const previous={document:globalThis.document,setInterval:globalThis.setInterval,clearInterval:globalThis.clearInterval,setTimeout:globalThis.setTimeout,clearTimeout:globalThis.clearTimeout,performance:globalThis.performance}
  globalThis.document={hidden:false,addEventListener(){},removeEventListener(){}}
  const timers=[]
  globalThis.setInterval=callback=>{timers.push(callback);return timers.length};globalThis.clearInterval=()=>{}
  if(options.performance)globalThis.performance=options.performance
  const timeouts=new Map();let timeoutId=0
  globalThis.setTimeout=(callback,delay)=>{const id=++timeoutId;timeouts.set(id,{callback,due:performance.now()+delay});return id}
  globalThis.clearTimeout=id=>timeouts.delete(id)
  const start=Date.UTC(2026,0,1),symbol={id:'binance:spot:BTCUSDT',symbol:'BTCUSDT',timeframes:['1m','1d'],session:'24x7',metadata:{mintick:.01},...options.symbol}
  const messages=[]
  let provider,unsubscribe,cell
  const chart={market:{bars:1000,symbol:'opentrading:'+symbol.id,timeframe:options.timeframe??'D'},renderer:{setWallClock(){}},data:{registerProvider(_key,value){provider=value},async ready(){}},async setMarket(value){
    Object.assign(chart.market,value)
    if(value.timeframe)cell.timeframe=value.timeframe
    if(value.symbol)cell.symbol=value.symbol
    unsubscribe?.();if(/^replay\d*:/.test(chart.market.symbol))unsubscribe=provider.subscribe('','',bar=>messages.push(bar))
  }}
  const {createWorkspaceReplay}=load('workspaceReplay',{
    './replayModel':model,'./replayQuantity':sizing,'./locale':{cw:key=>key},'./provider':{fromVela:value=>value.replace(/^(opentrading|replay\d*):/,''),velaSymbol:value=>'opentrading:'+value,timeframes:{D:'1d',W:'1w',M:'1M','1':'1m','5':'5m','15':'15m','60':'1h'}},
    './api':{chartApi:{replayBars:query=>reply(query,start,symbol)}},
  })
  cell={id:'c1',symbol:'opentrading:'+symbol.id,timeframe:options.timeframe??'D',chart}
  const replay=createWorkspaceReplay({workspace:vue.shallowRef({active:cell}),symbols:vue.ref([symbol]),settled:options.settled})
  const tick=async()=>{timers.forEach(callback=>callback());for(const [id,task]of [...timeouts])if(task.due<=performance.now()){timeouts.delete(id);task.callback()}for(let i=0;i<12;i++)await Promise.resolve()}
  try { await task(replay,start,messages,{cell,tick,provider:()=>provider}) } finally { replay.dispose();Object.assign(globalThis,previous) }
}

function replayViewReply(query,_start,symbol){
  if(query.start===undefined){
    const time=periodStart(query.end-1,query.timeframe),closeTime=periodEnd(time,query.timeframe)
    return{symbol,bars:[{...minute(time),closeTime,volume:(closeTime-time)/60000*2}]}
  }
  return{symbol,bars:Array.from({length:Math.min(query.limit,Math.floor((query.end-query.start)/60000))},(_,i)=>minute(query.start+i*60000))}
}

test('random replay samples verified history across months and starts playing the current symbol and interval',async()=>{
  const previousRandom=Math.random,requests=[],month=Date.UTC(2020,0,1),day=86400000
  Math.random=()=>0
  try{
    await replayFixture(async(r,start,_messages,{cell})=>{
      await r.start(start);r.account.prepare(1,'market',r.account.price,2,start);r.account.submit(start)
      await r.startRandom()
      assert.equal(r.now.value,month+12*day);assert.equal(r.active.value,true);assert.equal(r.playing.value,true)
      assert.equal(r.account.position,undefined);assert.equal(r.account.trades.length,0);assert.equal(r.timeframe.value,'15m')
      assert.equal(cell.timeframe,'15');assert.equal(r.symbol.value.id,'binance:spot:BTCUSDT')
      assert.ok(requests.some(query=>query.timeframe==='1M'&&query.start===0&&query.limit===1000))
      assert.ok(requests.some(query=>query.timeframe==='1d'&&query.start===month))
    },(query,start,symbol)=>{
      requests.push(query)
      if(query.timeframe==='1M')return{symbol,bars:[{...minute(month),closeTime:Date.UTC(2020,1,1)}]}
      if(query.timeframe==='1d'&&query.start===month)return{symbol,bars:[{...minute(month+11*day),closeTime:month+12*day},{...minute(month+12*day),closeTime:month+13*day}]}
      return replayViewReply(query,start,symbol)
    },{timeframe:'15',symbol:{timeframes:['1m','15m','1d','1M']}})
  }finally{Math.random=previousRandom}
})

test('random VIX replay selects within the minute vendor retention window',async()=>{
  const requests=[], day=86400000, recent=Math.floor(Date.now()/day)*day-10*day
  await replayFixture(async replay=>{
    await replay.startRandom()
    assert.equal(replay.active.value,true)
    const discovery=requests.find(query=>query.timeframe==='1d'&&query.start!==undefined)
    assert.ok(discovery.start>Date.now()-29*day)
    assert.ok(!requests.some(query=>query.timeframe==='1M'&&query.start===0))
  },(query,start,symbol)=>{
    requests.push(query)
    if(query.timeframe==='1d'&&query.start!==undefined)
      return {symbol,bars:[{...minute(recent),closeTime:recent+day},{...minute(recent+day),closeTime:recent+2*day}]}
    return replayViewReply(query,start,symbol)
  },{timeframe:'15',symbol:{id:'index:index:US_VIX',symbol:'US_VIX',timeframes:['1m','15m','1d','1M'],metadata:{intraday_retention_days:{'1m':29}}}})
})

test('random replay replaces dates with no minute source and validates the new candidate before starting',async()=>{
  const random=Math.random,month=Date.UTC(2020,0,1),day=86400000,missing=month+12*day,valid=month+13*day,queries=[]
  Math.random=()=>0
  try{
    await replayFixture(async(r,start)=>{
      await r.start(start);r.account.place(1,'market',r.account.price,2,start)
      await r.startRandom()
      assert.equal(r.now.value,valid);assert.equal(r.error.value,'');assert.equal(r.playing.value,true)
      assert.equal(r.account.position,undefined)
      const starts=queries.filter(q=>q.timeframe==='1m'&&q.start!==undefined)
      assert.ok(starts.some(q=>q.start===missing));assert.ok(starts.some(q=>q.start===valid))
      assert.ok(starts.every(q=>q.end-q.start<=1000*60000&&q.limit<=1000))
    },(query,start,symbol)=>{
      queries.push(query)
      if(query.timeframe==='1M')return{symbol,bars:[{...minute(month),closeTime:month+31*day}]}
      if(query.timeframe==='1d'&&query.start===month)return{symbol,bars:[{...minute(month+11*day),closeTime:missing},{...minute(missing),closeTime:valid}]}
      if(query.timeframe==='1m'&&query.start===missing)return{symbol,bars:[]}
      return replayViewReply(query,start,symbol)
    },{timeframe:'15',symbol:{timeframes:['1m','15m','1d','1M']}})
  }finally{Math.random=random}
})

test('random network failures preserve the position and retry the same candidate with automatic playback',async()=>{
  const random=Math.random,month=Date.UTC(2020,0,1),day=86400000,candidate=month+12*day,queries=[]
  let offline=true
  Math.random=()=>0
  try{
    await replayFixture(async(r,start)=>{
      await r.start(start);r.account.place(1,'market',r.account.price,2,start)
      const position=r.account.position
      await r.startRandom()
      assert.equal(r.error.value,'network offline');assert.equal(r.account.position,position);assert.equal(r.now.value,start)
      const overview=queries.filter(q=>q.timeframe==='1M').length
      offline=false;await r.retry()
      assert.equal(r.now.value,candidate);assert.equal(r.error.value,'');assert.equal(r.playing.value,true)
      assert.equal(queries.filter(q=>q.timeframe==='1M').length,overview)
    },(query,start,symbol)=>{
      queries.push(query)
      if(query.timeframe==='1M')return{symbol,bars:[{...minute(month),closeTime:month+31*day}]}
      if(query.timeframe==='1d'&&query.start===month)return{symbol,bars:[{...minute(month+11*day),closeTime:candidate}]}
      if(query.timeframe==='1m'&&query.start===candidate&&offline)throw new Error('network offline')
      return replayViewReply(query,start,symbol)
    },{timeframe:'15',symbol:{timeframes:['1m','15m','1d','1M']}})
  }finally{Math.random=random}
})

test('random replay falls back to a verified recent minute window rather than requiring full history',async()=>{
  const queries=[]
  await replayFixture(async r=>{
    await r.startRandom()
    assert.equal(r.active.value,true);assert.equal(r.playing.value,true);assert.equal(r.error.value,'')
    assert.ok(queries.some(q=>q.timeframe==='1m'&&q.start===undefined&&q.limit===1000))
    assert.ok(queries.filter(q=>q.timeframe==='1m'&&q.start!==undefined).every(q=>q.end-q.start<=1000*60000))
  },(query,start,symbol)=>{
    queries.push(query)
    if(query.timeframe==='1M'||query.timeframe==='1d')return{symbol,bars:[]}
    return replayViewReply(query,start,symbol)
  },{timeframe:'15',symbol:{timeframes:['1m','15m','1d','1M']}})
})

test('random replay uses a recent verified source window when coarse history predates minute coverage',async()=>{
  const previous=Math.random,month=Date.UTC(2020,0,1),day=86400000,candidate=month+12*day,requests=[]
  Math.random=()=>0
  let fallback
  try{
    await replayFixture(async r=>{
      await r.startRandom()
      assert.equal(r.now.value,fallback);assert.equal(r.active.value,true);assert.equal(r.playing.value,true)
      assert.ok(requests.some(q=>q.timeframe==='1m'&&q.start===undefined&&q.limit===1000))
      assert.ok(requests.filter(q=>q.timeframe==='1m'&&q.start!==undefined).every(q=>q.end-q.start<=1000*60000))
    },(query,start,symbol)=>{
      requests.push(query)
      if(query.timeframe==='1M')return{symbol,bars:[{...minute(month),closeTime:month+31*day}]}
      if(query.timeframe==='1d'&&query.start===month)return{symbol,bars:[{...minute(month+11*day),closeTime:candidate}]}
      if(query.timeframe==='1m'&&query.start===candidate)return{symbol,bars:[]}
      if(query.timeframe==='1m'&&query.start===undefined){fallback=periodStart(query.end-60000,'15m');return{symbol,bars:[minute(query.end-60000)]}}
      return replayViewReply(query,start,symbol)
    },{timeframe:'15',symbol:{timeframes:['1m','15m','1d','1M']}})
  }finally{Math.random=previous}
})

test('random replay supports daily-only instruments using available trading days',async()=>{
  await replayFixture(async r=>{
    await r.startRandom()
    assert.equal(r.active.value,true);assert.equal(r.playing.value,true);assert.equal(r.sourceStep.value,'1d')
    assert.ok(r.now.value<periodStart(Date.now(),'1d'));assert.equal(r.now.value%86400000,0)
  },(query,_start,symbol)=>{
    const day=86400000
    if(query.start===undefined)return{symbol,bars:[{...minute(query.end-2*day),closeTime:query.end-day},{...minute(query.end-day),closeTime:query.end}]}
    return{symbol,bars:[{...minute(query.start),closeTime:query.start+day}]}
  },{timeframe:'D',symbol:{timeframes:['1d'],session:'regular'}})
})

test('leaving during random date discovery discards the result without starting playback',async()=>{
  let release,calls=0
  await replayFixture(async r=>{
    const random=r.startRandom();assert.equal(r.loading.value,true)
    await r.exit();release();await random
    assert.equal(r.active.value,false);assert.equal(r.playing.value,false);assert.equal(r.loading.value,false)
    assert.equal(r.error.value,'');assert.equal(calls,1)
  },async(_query,_start,symbol)=>{calls++;await new Promise(resolve=>{release=resolve});return{symbol,bars:[]}},
  {timeframe:'5',symbol:{timeframes:['1m','5m','1d','1M']}})
})

test('switching replay intervals preserves exact time, position, exits, fills, speed and partial candles',async()=>{
  await replayFixture(async(r,start,messages,{cell})=>{
    await r.start(start);r.account.prepare(1,'market',r.account.price,2,start);r.account.submit(start)
    r.account.addExit(90,start);r.account.addExit(110,start,0.5)
    for(let i=0;i<5;i++)await r.step();r.account.close(r.now.value,'manual',r.account.price,0.5)
    r.setSpeed(30)
    const at=r.now.value,position=r.account.position,snapshot=JSON.stringify(r.account),provider=cell.symbol
    for(const interval of ['15','1','5','15']){
      await r.setTimeframe(interval)
      assert.equal(r.now.value,at);assert.equal(r.account.position,position);assert.equal(JSON.stringify(r.account),snapshot)
      assert.equal(cell.symbol,provider);assert.equal(cell.timeframe,interval)
      assert.equal(r.speed.value,30);assert.equal(r.active.value,true);assert.equal(r.open.value,true);assert.equal(r.playing.value,false)
      const last=r.visibleBars.at(-1)
      assert.equal(last.closed,interval!=='15');assert.equal(last.volume,interval==='1'?2:10)
    }
    for(let i=0;i<10;i++)await r.step()
    assert.equal(r.now.value,start+15*60000);assert.equal(messages.length,15)
    assert.equal(r.visibleBars.at(-1).volume,30);assert.equal(r.account.trades.length,1)
  },replayViewReply,{timeframe:'5'})
})

test('interval changes preserve pending orders and drafts without filling or recreating them',async()=>{
  await replayFixture(async(r,start)=>{
    await r.start(start);r.account.prepare(1,'limit',95,2,start);r.account.addExit(90,start);r.account.addExit(110,start,1);r.account.submit(start)
    const pending=r.account.pending,snapshot=JSON.stringify(pending)
    await r.setTimeframe('15');await r.setTimeframe('1')
    assert.equal(r.account.pending,pending);assert.equal(JSON.stringify(r.account.pending),snapshot);assert.equal(r.account.position,undefined)
    r.account.cancel('entry');r.account.prepare(-1,'limit',110,3,start)
    const draft=r.account.draft
    await r.setTimeframe('5');assert.equal(r.account.draft,draft);assert.equal(r.account.trades.length,0)
  },replayViewReply,{timeframe:'5'})
})

test('a playing replay resumes at the same speed after an interval load without counting load time',async()=>{
  let tick=0,release,hold=false
  await replayFixture(async(r,start,_messages,clock)=>{
    await r.start(start);r.setSpeed(2);r.play();tick=65000;await clock.tick()
    assert.equal(r.now.value,start+60000)
    hold=true;const changing=r.setTimeframe('15');await Promise.resolve()
    const at=r.now.value
    assert.equal(r.loading.value,true);assert.equal(r.playing.value,true)
    tick+=40000;await clock.tick();assert.equal(r.now.value,at)
    release();await changing
    assert.equal(r.playing.value,true);assert.equal(r.speed.value,2);assert.equal(r.now.value,at)
    tick+=500;await clock.tick()
    assert.equal(r.now.value,at+60000)
  },async(...args)=>{if(hold&&args[0].timeframe==='15m'){hold=false;await new Promise(resolve=>{release=resolve})}return replayViewReply(...args)},
  {timeframe:'5',performance:{now:()=>tick}})
})

test('automatic minute playback never interpolates timestamps or catches up while indicators are processing',async()=>{
  let tick=0,hold=false,release
  await replayFixture(async(r,start,messages,timer)=>{
    await r.start(start);r.play()
    tick=999;await timer.tick();assert.equal(r.now.value,start);assert.equal(messages.length,0)
    tick=1000;await timer.tick();assert.equal(r.now.value,start+60000);assert.equal(messages.length,1)
    tick=1500;await timer.tick();assert.equal(r.now.value,start+60000)
    hold=true;tick=2000;await timer.tick()
    assert.equal(r.processing.value,true);assert.equal(r.now.value,start+120000)
    tick=65000;await timer.tick();assert.equal(messages.length,2);assert.equal(r.now.value,start+120000)
    release();for(let i=0;i<12;i++)await Promise.resolve()
    tick=65999;await timer.tick();assert.equal(messages.length,2)
    tick=66000;await timer.tick();assert.equal(messages.length,3);assert.equal(r.now.value,start+180000)
    r.pause();tick=999999;await timer.tick();assert.equal(messages.length,3);assert.equal(r.now.value,start+180000)
  },replayViewReply,{timeframe:'5',performance:{now:()=>tick},settled:async()=>{if(hold){hold=false;await new Promise(resolve=>{release=resolve})}}})
})

test('rapid interval changes keep only the latest selection; leaving discards a late view load',async()=>{
  let hold=false,release
  await replayFixture(async(r,start)=>{
    await r.start(start);await r.step();const at=r.now.value
    hold=true;const first=r.setTimeframe('15');await Promise.resolve()
    await r.setTimeframe('1');release();await first
    assert.equal(r.timeframe.value,'1m');assert.equal(r.now.value,at);assert.equal(r.error.value,'');assert.equal(r.loading.value,false)
    hold=true;const last=r.setTimeframe('15');await Promise.resolve()
    await r.exit();release();await last
    assert.equal(r.active.value,false);assert.equal(r.open.value,false);assert.equal(r.loading.value,false);assert.equal(r.playing.value,false)
  },async(...args)=>{if(hold&&args[0].timeframe==='15m'){hold=false;await new Promise(resolve=>{release=resolve})}return replayViewReply(...args)}, {timeframe:'5'})
})

test('failed interval loading retains the existing view and orders; retry does not restart or advance replay',async()=>{
  let fail=true
  await replayFixture(async(r,start)=>{
    await r.start(start);r.account.prepare(1,'market',r.account.price,1,start);r.account.submit(start);await r.step()
    const position=r.account.position,at=r.now.value,last=r.visibleBars.at(-1)
    await r.setTimeframe('15')
    assert.equal(r.timeframe.value,'5m');assert.equal(r.account.position,position);assert.equal(r.now.value,at);assert.equal(r.visibleBars.at(-1),last);assert.ok(r.error.value)
    fail=false;await r.retry()
    assert.equal(r.timeframe.value,'15m');assert.equal(r.account.position,position);assert.equal(r.now.value,at);assert.equal(r.error.value,'')
  },(...args)=>{if(fail&&args[0].timeframe==='15m')throw new Error('offline');return replayViewReply(...args)}, {timeframe:'5'})
})

test('changing interval during indicator processing finishes the current minute only and never consumes it twice',async()=>{
  let hold=true,release
  await replayFixture(async(r,start,messages)=>{
    await r.start(start)
    const step=r.step();const changing=r.setTimeframe('15')
    assert.equal(r.now.value,start+60000);release();await step;await changing
    assert.equal(r.now.value,start+60000);assert.equal(r.visibleBars.at(-1).volume,2)
    await r.step();assert.equal(messages.length,2);assert.equal(r.now.value,start+120000)
    for(let i=2;i<15;i++)await r.step()
    assert.equal(messages.length,15);assert.equal(r.visibleBars.at(-1).volume,30)
  },replayViewReply,{timeframe:'5',settled:async()=>{if(hold){hold=false;await new Promise(resolve=>{release=resolve})}}})
})

test('minute stepping across history pages consumes every minute of a daily candle exactly once',async()=>{
  await replayFixture(async(r,start,messages)=>{
    await r.start(start);for(let i=0;i<1440;i++)await r.step()
    assert.equal(r.now.value,start+1440*60000)
    assert.equal(messages.length,1440)
    assert.equal(messages.at(-1).closed,true)
    assert.equal(messages.at(-1).volume,1440*2)
  },(query,start,symbol)=>({symbol,bars:query.start===undefined?[{...minute(start-86400000),closeTime:start}]:Array.from({length:query.limit},(_,i)=>minute(query.start+i*60000))}))
})

test('replay shows its first history page before older candles finish and never exposes its prefetched future', async () => {
  let release
  const older = new Promise(resolve => { release = resolve })
  await replayFixture(async (r, start, _messages, context) => {
    await r.start(start)
    const batches = [], provider = context.provider()
    const pending = provider.getBarsProgressive(r.symbol.value.id, '5', { limit: 1000 }, bars => batches.push(bars))
    for (let i = 0; i < 6; i++) await Promise.resolve()
    assert.equal(batches[0].length, 200)
    assert.ok(batches[0].every(bar => bar.closeTime <= r.now.value))
    release()
    const full = await pending
    assert.equal(full.length, 1000)
    assert.equal(new Set(full.map(bar => bar.time)).size, 1000)
    assert.ok(full.every(bar => bar.closeTime <= r.now.value))
  }, async (query, _start, symbol) => {
    if (query.start !== undefined) return replayViewReply(query, _start, symbol)
    if (query.limit > 200) await older
    return { symbol, bars: Array.from({ length: query.limit }, (_, i) => {
      const time = query.end - (query.limit - i) * 300000
      return { ...minute(time), closeTime: time + 300000 }
    }) }
  }, { timeframe: '5', symbol: { timeframes: ['1m','5m'] } })
})

test('failed ahead-of-time fetching keeps verified playback running and retries at the buffer boundary', async () => {
  let failing = true, calls = 0
  await replayFixture(async (r, start) => {
    await r.start(start)
    for (let i = 0; i < 12; i++) await Promise.resolve()
    assert.equal(r.error.value, '')
    for (let i = 0; i < 200; i++) await r.step()
    assert.equal(r.now.value, start + 200 * 60000)
    assert.equal(calls, 1, 'a failed prefetch must not spin while verified candles remain')
    await r.step()
    assert.ok(r.error.value)
    assert.equal(r.now.value, start + 200 * 60000)
    failing = false; await r.retry()
    assert.equal(r.now.value, start + 201 * 60000)
    assert.equal(r.error.value, '')
  }, (query, start, symbol) => {
    if (query.start >= start + 200 * 60000) { calls++; if (failing) throw new Error('temporary network failure') }
    return replayViewReply(query, start, symbol)
  }, { timeframe: '5' })
})

test('a monthly replay view uses closed days and hours plus only its final minutes without advancing the account', async () => {
  const requests = [], day = 86400000
  await replayFixture(async (r, start) => {
    await r.start(start + 20 * day + 17 * 3600000)
    for (let i = 0; i < 13; i++) await r.step()
    const at = r.now.value, before = requests.length
    r.account.prepare(1,'market',r.account.price,2,at); r.account.submit(at)
    const position = JSON.stringify(r.account.position)
    await r.setTimeframe('M')
    const view = requests.slice(before), monthStart = periodStart(at, '1M')
    assert.equal(r.now.value, at)
    assert.equal(JSON.stringify(r.account.position), position)
    assert.equal(r.visibleBars.at(-1).volume, (at - monthStart) / 60000 * 2)
    assert.equal(r.visibleBars.at(-1).closed, false)
    assert.ok(view.some(query => query.timeframe === '1d'))
    assert.ok(view.some(query => query.timeframe === '4h'))
    assert.ok(view.filter(query => query.timeframe === '1m').every(query => query.limit < 60))
    assert.ok(view.every(query => query.end <= at), 'no partial candle may read after the replay clock')
    assert.ok(view.length <= 6, 'rebuilding a month should not walk thousands of individual minutes')
  }, (query, start, symbol) => {
    requests.push(query)
    const size = query.timeframe === '1M' ? 31 * day : periodEnd(query.start ?? query.end - 1, query.timeframe) - periodStart(query.start ?? query.end - 1, query.timeframe)
    if (query.start === undefined) return { symbol, bars: [{ ...minute(query.end - size), closeTime: query.end, volume: size / 60000 * 2 }] }
    return { symbol, bars: Array.from({ length: Math.min(query.limit, Math.floor((query.end-query.start)/size)) }, (_, i) => {
      const time = query.start + i * size; return { ...minute(time), closeTime: time + size, volume: size / 60000 * 2 }
    }) }
  }, { timeframe: '15', symbol: { timeframes: ['1m','5m','15m','30m','1h','4h','1d','1w','1M'] } })
})

test('leaving while a date is loading discards the late history response',async()=>{
  let release
  const waiting=new Promise(resolve=>{release=resolve})
  await replayFixture(async(r,start)=>{
    const pending=r.start(start)
    assert.equal(r.loading.value,true)
    await r.exit();release();await pending
    assert.equal(r.active.value,false);assert.equal(r.loading.value,false)
    assert.equal(r.visibleBars.length,0)
  },async(query,start,symbol)=>{await waiting;return{symbol,bars:query.start===undefined?[{...minute(start-86400000),closeTime:start}]:[minute(start)]}})
})

test('a failed initial load can retry the same selected date',async()=>{
  let failing=true
  await replayFixture(async(r,start)=>{
    await r.start(start);assert.equal(r.active.value,false);assert.ok(r.error.value)
    failing=false;await r.retry()
    assert.equal(r.active.value,true);assert.equal(r.now.value,start);assert.equal(r.error.value,'')
  },(query,start,symbol)=>{
    if(failing)throw new Error('offline')
    return{symbol,bars:query.start===undefined?[{...minute(start-86400000),closeTime:start}]:[minute(start)]}
  })
})

test('chart order coordinates stay accurate with pane offsets and a logarithmic scale',()=>{
  let definition,geometry
  load('replayOrderLayer',{'@luxalgo/vela/plugin':{registerRendererLayer(value){definition=value}}})
  const source={host:{getBoundingClientRect:()=>({left:10,top:20,right:1010})},lines:[{target:'exit:1',price:256,label:'SL',color:'red',draggable:true}],geometry:value=>{geometry=value}}
  const layer=definition.create(),context=new Proxy({}, {get:()=>()=>{},set:()=>true})
  layer.mount({width:1000,height:800,getContext:()=>context,getBoundingClientRect:()=>({left:50,top:80})})
  const coords={dpr:1,width:900,priceToY:price=>500-Math.log2(price)*25,yToPrice:y=>2**((500-y)/25),xToLogical:x=>x/10,logicalToTime:index=>index*60000}
  layer.render({data:source,coords,bounds:{top:40,height:500},scale:{},theme:{}})
  assert.equal(geometry.lines[0].y,360)
  assert.equal(source.pointAt(150,380).price,256)
  assert.equal(source.hitAt(150,380),'exit:1')
  assert.equal(source.pointAt(150,85),undefined)
})
