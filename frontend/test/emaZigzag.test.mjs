import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import crypto from 'node:crypto'
import { Indicator, PineTS } from 'pinets'
import { PineEngine } from '@luxalgo/vela-pinets'
import { checkPine, linkPine } from '../src/modules/chartWorkspace/pineCompatibility.mjs'
import { pineLibraries } from '../src/modules/chartWorkspace/pineLibraries.mjs'
import { installPineRuntimeCompat } from '../src/modules/chartWorkspace/pineRuntimeCompat.mjs'
installPineRuntimeCompat()

const source=fs.readFileSync(new URL('../../strategies/pine/ema_zigzag_glow.pine',import.meta.url),'utf8')
const bars=Array.from({length:600},(_,i)=>{const price=60000+Math.sin(i/9)*1600+Math.sin(i/30)*3000;return {time:1700000000000+i*900000,openTime:1700000000000+i*900000,closeTime:1700000000000+(i+1)*900000,open:price,high:price+150+Math.sin(i)*100,low:price-150-Math.cos(i)*100,close:price+Math.sin(i)*100,volume:100}})
const symbolInfo={mintick:0.1,tickerid:'TEST',ticker:'TEST',currency:'USDT',timezone:'Etc/UTC',session:'24x7',type:'crypto',pricescale:10,minmove:1,pointvalue:1}

// Independent, direct evaluation of the published ZigLib v1 formulas.
function reference(depth,deviation,backstep){
  let priorHighDeviation,priorLowDeviation,hr=NaN,lr=NaN,directionAge=NaN,priorDirection
  let z,z1,z2
  return bars.map((bar,index)=>{
    const window=bars.slice(Math.max(0,index-depth+1),index+1)
    const highest=Math.max(...window.map(row=>row.high)),lowest=Math.min(...window.map(row=>row.low))
    const highDeviation=highest-bar.high>deviation*symbolInfo.mintick
    const lowDeviation=bar.low-lowest>deviation*symbolInfo.mintick
    hr=priorHighDeviation===false?0:hr+1
    lr=priorLowDeviation===false?0:lr+1
    const nonFalling=Number.isFinite(hr)&&Number.isFinite(lr)?!(hr>lr):undefined
    directionAge=nonFalling===true?0:directionAge+1
    const direction=directionAge>=backstep?-1:1
    z??={time:bar.time,price:bar.low};z1??={time:bar.time,price:bar.low};z2??={time:bar.time,price:bar.high}
    if(priorDirection!=null&&direction!==priorDirection){z1={...z2};z2={...z}}
    if(direction>0){
      if(bar.high>z2.price){z2={time:bar.time,price:bar.high};z={time:bar.time,price:bar.low}}
      if(bar.low<z.price)z={time:bar.time,price:bar.low}
    }
    if(direction<0){
      if(bar.low<z2.price){z2={time:bar.time,price:bar.low};z={time:bar.time,price:bar.high}}
      if(bar.high>z.price)z={time:bar.time,price:bar.high}
    }
    priorHighDeviation=highDeviation;priorLowDeviation=lowDeviation;priorDirection=direction
    return {direction,z1:{...z1},z2:{...z2}}
  })
}

test('the exact ZigLib version is pinned; user imports, comments and source remain intact',()=>{
  const library=pineLibraries[0]
  assert.equal(crypto.createHash('sha256').update(library.source).digest('hex'),library.sourceSha256)
  checkPine(source)
  const prepared=linkPine(source)
  assert.ok(!prepared.source.includes('request.security('))
  assert.ok(prepared.source.includes('chart.point.now'))
  assert.throws(()=>checkPine(source.replace('ZigLib/1','ZigLib/2')),/ZigLib\/2/)
  assert.throws(()=>checkPine(source.replace('ZigZag.zigzag(','ZigZag.missing(')),/没有导出/)
  const indicator=new Indicator(source)
  assert.equal(indicator.getDeclarationType(),'indicator')
  assert.equal(indicator.getInputsMeta().length,8)
  indicator.prepare()
  assert.equal(indicator.source,source)
  const broken=source+'\nbroken = )',invalid=new Indicator(broken)
  assert.throws(()=>invalid.prepare(),error=>error.line===broken.split('\n').length)
  assert.equal(invalid.source,broken)
})

for(const [depth,deviation,backstep] of [[12,5,2],[4,1800,3]])test(`ZigLib matches all 600 directions and both endpoint histories (${depth},${deviation},${backstep})`,async()=>{
  const indicator=new Indicator(source+'\nplot(z1.time,"z1time")\nplot(z1.price,"z1price")\nplot(z2.time,"z2time")\nplot(z2.price,"z2price")',{Depth:depth,Deviation:deviation,Backstep:backstep})
  const pine=new PineTS({getMarketData:async()=>bars,getSymbolInfo:async()=>symbolInfo},'TEST','15',bars.length)
  const context=await pine.run(indicator),expected=reference(depth,deviation,backstep)
  for(let i=0;i<bars.length;i++){
    assert.equal(context.plots['ZigZag方向'].data[i].value,expected[i].direction,'direction at '+i)
    for(const point of ['z1','z2'])for(const field of ['time','price']){
      assert.ok(Math.abs(context.plots[point+field].data[i].value-expected[i][point][field])<1e-7,`${point}.${field} at ${i}`)
    }
  }
  assert.ok(new Set(context.plots['ZigZag方向'].data.map(row=>row.value)).size===2)
})

test('the chart adapter renders five EMAs and paired glow lines in both repaint modes',async()=>{
  const counts=[]
  for(const repaint of [true,false]){
    const engine=new PineEngine(),prepared=await engine.prepare(source,'zigzag')
    assert.equal(prepared.inputs.length,8)
    let session
    try{
      const model=await new Promise((resolve,reject)=>{session=engine.execute({prepared,bars,market:{symbol:'TEST',timeframe:'15',symbolInfo},mode:'static',inputs:{repaint}},{onModel:resolve,onError:reject})})
      assert.equal(model.series.filter(series=>series.title?.startsWith('EMA ')).length,5)
      assert.ok(model.lines.length>10)
      const widths=model.lines.map(line=>line.width)
      assert.ok(widths.includes(2)&&widths.includes(5))
      assert.equal(model.lines.length%2,0)
      counts.push(model.lines.length)
      for(const line of model.lines){assert.equal(line.xloc,'bar_time');assert.ok(line.x1>=bars[0].time&&line.x2>=bars[0].time)}
    }finally{session?.stop()}
  }
  assert.equal(counts[0],counts[1]+2)
})

test('ZigZag live ticks match a fresh calculation without accumulating temporary lines',async()=>{
  const now=Math.floor(Date.now()/900000)*900000
  const liveBars=bars.map((bar,index)=>({...bar,time:now-(bars.length-index-1)*900000,openTime:now-(bars.length-index-1)*900000,closeTime:now-(bars.length-index-2)*900000}))
  const engine=new PineEngine(),prepared=await engine.prepare(source,'live-zigzag')
  let session,resolveModel,rejectModel
  const next=()=>new Promise((resolve,reject)=>{resolveModel=resolve;rejectModel=reject})
  const timeout=setTimeout(()=>rejectModel(new Error('No live ZigZag update within 8 seconds')),8000)
  const shape=model=>model.lines.map(({x1,y1,x2,y2,xloc,width,color})=>({x1,y1,x2,y2,xloc,width,color}))
  async function fresh(){
    let staticSession
    try{return await new Promise((resolve,reject)=>{staticSession=engine.execute({prepared,bars:liveBars,market:{symbol:'TEST',timeframe:'15',symbolInfo},mode:'static'},{onModel:resolve,onError:reject})})}
    finally{staticSession?.stop()}
  }
  try{
    let pending=next()
    session=engine.execute({prepared,bars:liveBars,getBars:()=>liveBars,market:{symbol:'TEST',timeframe:'15',symbolInfo},mode:'live'}, {onModel:model=>resolveModel(model),onError:error=>rejectModel(error)})
    await pending
    for(const high of [65000,66000]){
      await new Promise(resolve=>setTimeout(resolve,10))
      pending=next();liveBars[liveBars.length-1]={...liveBars.at(-1),high,close:high-100};session.notifyBars()
      const live=await pending,expected=await fresh()
      assert.deepEqual(shape(live),shape(expected))
    }
  }finally{clearTimeout(timeout);session?.stop()}
})
