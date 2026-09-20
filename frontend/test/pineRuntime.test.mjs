import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import crypto from 'node:crypto'
import { PineTS } from 'pinets'
import { PineEngine } from '@luxalgo/vela-pinets'
import { installPineRuntimeCompat,setPineSymbolCatalog } from '../src/modules/chartWorkspace/pineRuntimeCompat.mjs'
installPineRuntimeCompat()

const symbolInfo={mintick:.01,ticker:'TEST',tickerid:'TEST',timezone:'Etc/UTC',type:'crypto',session:'24x7',currency:'USDT',minmove:1,pricescale:100,pointvalue:1}
const candles=n=>Array.from({length:n},(_,i)=>({time:1600000000000+i*3600000,openTime:1600000000000+i*3600000,closeTime:1600000000000+(i+1)*3600000,open:100,high:103,low:98,close:101,volume:10}))

test('original v7.2 contract: 240 bars, 38 events, tolerance 1e-7',async()=>{
  const root=new URL('../../',import.meta.url)
  const fixture=JSON.parse(fs.readFileSync(new URL('docs/verification/pine-v7-2-contract/runtime-fixture-20260920.json',root)))
  const original=fs.readFileSync(new URL('strategies/pine/eth_ema55_manual_chart_v7_2.pine',root),'utf8').replace(/\r\n/g,'\n')
  assert.equal(crypto.createHash('sha256').update(original).digest('hex'),fixture.source_sha256)
  const source=fs.readFileSync(new URL('docs/verification/pine-v7-2-contract/runtime-harness-20260920.pine',root),'utf8')
  const logs=[],originalLog=console.log
  try{
    console.log=(...args)=>logs.push(args.join(' '))
    await new PineTS({getMarketData:async()=>candles(891),getSymbolInfo:async()=>symbolInfo},'TEST','60',891).run(source)
  }finally{console.log=originalLog}
  assert.ok(logs.some(line=>line.includes('PASS | bars=240 | events=38/38 | mismatches=0')),logs.join('\n'))
})

test('chart adapter renders v5/v6 plots, fill, labels, boxes, lines and table',async()=>{
  for(const version of [5,6]){
    const engine=new PineEngine()
    const prepared=await engine.prepare(`//@version=${version}
indicator("Visual", overlay=true)
a=plot(ta.ema(close, 3), color=color.green)
b=plot(ta.sma(close, 5), color=color.red)
fill(a,b,color=color.new(color.green,80))
plotshape(bar_index==6)
if bar_index==6
    label.new(bar_index,high,"L")
    line.new(bar_index-2,low,bar_index,high)
    box.new(bar_index-2,high,bar_index,low)
var t=table.new(position.top_right,1,1)
if barstate.islast
    table.cell(t,0,0,"ok")`,'visual')
    let session
    const model=await new Promise((resolve,reject)=>{
      session=engine.execute({prepared,bars:candles(10),market:{symbol:'TEST',timeframe:'60',symbolInfo},mode:'static'}, {onModel:resolve,onError:reject})
    })
    session.stop()
    assert.ok(model.series.length>=2)
    assert.ok(model.fills.length>=1)
    assert.ok(model.labels.length>=1)
    assert.ok(model.lines.length>=1)
    assert.ok(model.boxes.length>=1)
    assert.ok(model.tables.length>=1)
  }
})

test('live updates roll back var, retain scalar varip, confirm bars and avoid duplicate labels',async(t)=>{
  const engine=new PineEngine()
  const prepared=await engine.prepare(`//@version=6
indicator("Live")
var int v=0
varip int ip=0
v+=1
ip+=1
plot(v,"var")
plot(ip,"varip")
plot(barstate.isconfirmed?1:0,"confirmed")
label.new(bar_index,high,"x")`,'live')
  const now=Math.floor(Date.now()/60000)*60000
  let clock=now+30000
  t.mock.method(Date,'now',()=>clock)
  const bars=Array.from({length:5},(_,i)=>({time:now-(4-i)*60000,open:100,high:103,low:98,close:101,volume:1}))
  let session,deliver,fail
  const next=()=>new Promise((resolve,reject)=>{deliver=resolve;fail=reject})
  let pending=next()
  const timeout=setTimeout(()=>fail(new Error('No live update after 5 seconds')),5000)
  try{
    session=engine.execute({prepared,bars,getBars:()=>bars,market:{symbol:'TEST',timeframe:'1',symbolInfo},mode:'live'},{onModel:m=>deliver(m),onError:e=>fail(e)})
    const initial=await pending
    const value=(m,title)=>m.series.find(s=>s.title===title).points.at(-1).value
    assert.equal(value(initial,'var'),5)
    assert.equal(value(initial,'confirmed'),0)
    // Let the initial stream finish publishing its fingerprint before the next tick.
    await new Promise(resolve=>setTimeout(resolve,10))
    pending=next();bars[4]={...bars[4],close:102};session.notifyBars()
    const update=await pending
    assert.equal(value(update,'var'),5)
    assert.equal(value(update,'varip'),6)
    assert.equal(update.labels.length,5)
    await new Promise(resolve=>setTimeout(resolve,10))
    clock=now+60001
    pending=next();bars.push({...bars[4],time:now+60000,close:102.5});session.notifyBars()
    const appended=await pending
    assert.equal(value(appended,'var'),6)
    assert.equal(appended.labels.length,6)
    assert.equal(appended.series.find(s=>s.title==='confirmed').points.at(-2).value,1)
  }finally{clearTimeout(timeout);session?.stop()}
})


test('secondary Pine contexts use the verified market metadata',async()=>{
  setPineSymbolCatalog([{id:'binance:usdm:ETHUSDT',symbol:'ETHUSDT',exchange:'binance',market:'usdm',currency:'USDT',timezone:'Etc/UTC',session:'24x7',name:'ETH/USDT',metadata:{mintick:.001,pointvalue:1}}])
  try{
    const pine=new PineTS({getMarketData:async()=>candles(5),getSymbolInfo:async()=>({...symbolInfo,currency:'USD',mintick:.01})},'BINANCE:ETHUSDT.P','60',5)
    const context=await pine.run('//@version=6\nindicator("Metadata")\nplot(syminfo.mintick,"tick")')
    assert.equal(context.pine.syminfo.currency,'USDT')
    assert.equal(context.pine.syminfo.type,'futures')
    assert.equal(context.plots.tick.data.at(-1).value,.001)
  }finally{setPineSymbolCatalog([])}
})
