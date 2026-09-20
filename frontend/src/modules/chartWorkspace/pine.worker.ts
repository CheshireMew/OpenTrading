import { PineEngine } from '@luxalgo/vela-pinets'
import type { ExecutionSession, PreparedScript, ExecutionRequest } from '@luxalgo/vela/plugin'
import { PINE_ENGINE_VERSION } from './pineCompatibility.mjs'
import { Indicator } from 'pinets'
import { installPineRuntimeCompat,setPinePrimaryBars,setPineSymbolCatalog } from './pineRuntimeCompat.mjs'
installPineRuntimeCompat()

// This worker imports the same pinned PineTS as the Node worker. The addon ships
// a prebuilt worker with a separately embedded runtime; do not use that bundle.
const engine=new PineEngine()
let prepared:PreparedScript,session:ExecutionSession|undefined,bars:ExecutionRequest['bars']=[]
let market:ExecutionRequest['market']|undefined
let fetchId=0
const fetches=new Map<number,{resolve:(bars:any)=>void;reject:(e:Error)=>void}>()
const send=(value:unknown)=>postMessage(value)
self.onmessage=async({data})=>{
  try{
    if(data.type==='metadata'){
      const indicator=new Indicator(data.source)
      indicator.prepare()
      send({type:'metadata',kind:indicator.getDeclarationType(),inputs:indicator.getInputsMeta(),props:Object.fromEntries(indicator.getPropsMeta().map(p=>[p.name,indicator.prop[p.name]]))})
    }else if(data.type==='prepare'){
      prepared=await engine.prepare(data.source,data.instanceId)
      send({type:'prepared',prepared,version:PINE_ENGINE_VERSION})
    }else if(data.type==='execute'){
      setPineSymbolCatalog(data.catalog??[])
      bars=data.request.bars
      market=data.request.market;setPinePrimaryBars(market!.symbol,market!.timeframe,bars)
      session=engine.execute({...data.request,prepared,getBars:()=>bars,fetchSeries:(...args:any[])=>new Promise((resolve,reject)=>{
        const id=++fetchId;fetches.set(id,{resolve,reject});send({type:'fetch',id,args})
      })},{onModel:model=>send({type:'model',model}),onError:error=>send({type:'error',message:error.message}),
        onWarning:warning=>send({type:'warning',warning}),onAlert:alert=>send({type:'alert',alert}),onDone:()=>send({type:'done'})})
    }else if(data.type==='bars'){
      if(data.full)bars=data.bars
      else for(const bar of data.bars){const last=bars[bars.length-1];if(last&&last.time===bar.time)bars[bars.length-1]=bar;else if(!last||bar.time>last.time)bars.push(bar)}
      if(market)setPinePrimaryBars(market.symbol,market.timeframe,bars)
      session?.notifyBars(data.reason)
    }else if(data.type==='update')session?.update(data.inputs,data.props)
    else if(data.type==='range')session?.setVisibleRange(data.range)
    else if(data.type==='context')send({type:'context',id:data.id,value:await session?.getContext?.(data.select)??null})
    else if(data.type==='fetchResult'){
      const promise=fetches.get(data.id);fetches.delete(data.id)
      if(data.error)promise?.reject(new Error(data.error));else promise?.resolve(data.bars)
    }else if(data.type==='stop'){session?.stop();close()}
  }catch(error){send({type:'error',message:error instanceof Error?error.message:String(error)})}
}
