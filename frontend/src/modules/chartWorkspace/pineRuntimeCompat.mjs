// Host compatibility extension for the pinned PineTS 0.9.34 runtime.
// The upstream transpiler maps both var and varip to Context.var. Preserve only
// global scalar varip values across its existing rollback; history and drawings
// still use the upstream rollback. The Pine source is never rewritten.
import { PineTS, Indicator } from 'pinets'
import { codeOnly } from './pineCompatibility.mjs'
export const PINE_ADAPTER_VERSION='opentrading-2'
let primaryIdentity='',primaryBars=new Map()
let symbolCatalog=[]
export function setPineSymbolCatalog(catalog){symbolCatalog=catalog}
export function setPinePrimaryBars(symbol,timeframe,bars){primaryIdentity=`${symbol}|${timeframe}`;primaryBars=new Map(bars.map(b=>[b.time,b]))}
function closingTime(bar,timeframe){
  if(Number.isFinite(bar?.closeTime))return bar.closeTime
  const open=bar?.openTime??bar?.time
  if(!Number.isFinite(open))return NaN
  if(/^(?:1)?M$/.test(timeframe)){const date=new Date(open);date.setUTCMonth(date.getUTCMonth()+1,1);return date.getTime()}
  const match=String(timeframe).match(/^(\d+)?([mhdwDWH]?)$/)
  return match?open+Number(match[1]||1)*({m:60000,h:3600000,H:3600000,d:86400000,D:86400000,w:604800000,W:604800000,'':60000}[match[2]]):NaN
}
const installed=Symbol.for('opentrading.pinets.0.9.34.compat')
export function installPineRuntimeCompat(){
  if(Indicator.prototype[installed])return
  const prepare=Indicator.prototype.prepare,restore=PineTS.prototype._restoreVarState,initialize=PineTS.prototype._initializeContext
  if(typeof restore!=='function')throw new Error('Pine 引擎回滚接口改变，需要重新验证兼容层')
  const preparedObjects=new WeakSet(),keysByContext=new WeakMap(),states=new WeakMap()
  // The Vela adapter invents generic USD metadata for request.security symbols.
  // Use the same verified catalog as the primary feed for every Pine context.
  PineTS.prototype._initializeContext=function(...args){
    const context=initialize.apply(this,args)
    if(symbolCatalog.length){
      const ticker=String(context.tickerId).split(';')[0].replace(/^(?:opentrading|heimdall):/i,'')
      const parts=ticker.split(':'),code=parts.at(-1).replace(/\.P$/,'')
      const info=symbolCatalog.find(s=>s.id===ticker)||symbolCatalog.find(s=>s.symbol===code&&s.exchange===(parts.length>1?parts[0].toLowerCase():'binance')&&s.market===(ticker.endsWith('.P')?'usdm':'spot'))
      if(!info)throw new Error(`没有 ${ticker} 的真实品种元数据`)
      context.pine.syminfo={...info.metadata,ticker:info.symbol,tickerid:context.tickerId,prefix:info.exchange,currency:info.currency,timezone:info.timezone,session:info.session,type:info.market==='usdm'?'futures':info.market==='index'?'index':'crypto',description:info.name}
    }
    return context
  }
  Indicator.prototype.prepare=function(...args){
    const prepared=prepare.apply(this,args)
    if(preparedObjects.has(prepared)||typeof this.source!=='string')return prepared
    preparedObjects.add(prepared)
    const names=[...codeOnly(this.source).matchAll(/^varip\s+(?:(?:int|float|bool|string|color)\s+)?([A-Za-z_]\w*)\s*=/gm)].map(m=>m[1])
    const original=prepared.fn,generated=original.toString(),keys=[]
    for(const name of names){
      const matches=[...generated.matchAll(new RegExp('\\.var\\.(glb\\d+_'+name+')\\b','g'))]
      const unique=[...new Set(matches.map(m=>m[1]))]
      if(unique.length!==1)throw new Error(`无法明确识别 varip ${name} 的作用域`)
      keys.push(unique[0])
    }
    prepared.fn=function(context){
      keysByContext.set(context,keys)
      let state=states.get(context)
      if(!state){
        state={seen:new Set(),live:new Set(),time:0,confirmed:false,isnew:false}
        states.set(context,state)
        const originalBarstate=context.pine.barstate
        context.pine.barstate={setLive:()=>originalBarstate.setLive(),
          get isfirst(){return context.idx===0},get islast(){return context.idx===context.length-1},
          get isnew(){return state.isnew},get isconfirmed(){return state.confirmed},
          get isrealtime(){return state.live.has(state.time)},get ishistory(){return !state.live.has(state.time)},
          get islastconfirmedhistory(){const last=context.marketData[context.length-1];const lastClosed=closingTime(last,context.timeframe)<=Date.now();return context.idx===context.length-(lastClosed?1:2)&&!state.live.has(state.time)},
        }
      }
      const raw=context.marketData[context.idx]
      const bar=primaryIdentity===`${context.tickerId}|${context.timeframe}`?(primaryBars.get(raw?.openTime)??raw):raw
      state.time=bar?.openTime??bar?.time
      state.confirmed=typeof bar?.closed==='boolean'?bar.closed:closingTime(bar,context.timeframe)<=Date.now()
      state.isnew=!state.seen.has(state.time)
      if(!state.confirmed)state.live.add(state.time)
      state.seen.add(state.time)
      return original(context)
    }
    return prepared
  }
  PineTS.prototype._restoreVarState=function(context,snapshot){
    const retained=(keysByContext.get(context)??[]).map(key=>{
      const series=context.var[key],value=series?.data?.at(-1)
      if(value!==null&&typeof value==='object')throw new Error(`varip ${key} 暂只支持标量，不支持数组或对象`)
      return {key,value}
    })
    restore.call(this,context,snapshot)
    for(const {key,value} of retained){
      const series=context.var[key],length=snapshot?.main?.var?.[key]?.len
      if(series?.data&&length>0)series.data[length-1]=value
    }
  }
  Object.defineProperty(Indicator.prototype,installed,{value:true})
}
