import type { DataProvider, BarRange, SymbolDescriptor, SymbolInfo } from '@luxalgo/vela'
import type { OHLCV } from '@luxalgo/vela'
import { chartApi, type ChartSymbol, BASE } from './api'
import { cw } from './locale'

export const timeframes:Record<string,string> = {'1':'1m','5':'5m','15':'15m','30':'30m','60':'1h','240':'4h','D':'1d','1D':'1d','W':'1w','1W':'1w','M':'1M','1M':'1M'}
export const velaSymbol = (id:string) => 'opentrading:' + id
export const fromVela = (id:string) => id.replace(/^(?:opentrading|heimdall):/,'')

export class OpenTradingProvider implements DataProvider {
  catalog:ChartSymbol[] = []
  statuses = new Map<string,{status:string;error?:string}>()
  private socket?:WebSocket
  private retry?:ReturnType<typeof setTimeout>
  private generation=0
  private subscriptions=new Map<string,{generation:number;sequence:number}>()
  private closed = false
  private callbacks = new Map<string,Set<(bar:OHLCV)=>void>>()
  private requests = new Set<AbortController>()
  private inFlight = new Map<string,Promise<OHLCV[]>>()
  constructor(private status:(symbol:string,status:string,error?:string)=>void) {}
  async resolve(ticker:string):Promise<ChartSymbol> {
    if (!this.catalog.length) this.catalog = await chartApi.symbols()
    const normalized = fromVela(ticker)
    const exact = this.catalog.find(s=>s.id===normalized)
    if (exact) return exact
    const parts = normalized.split(':')
    const symbol = parts[parts.length-1]!.replace(/\.P$/, '')
    const result = this.catalog.find(s=>s.symbol===symbol && s.exchange===(parts.length>1?parts[0]!.toLowerCase():'binance') && s.market===(normalized.endsWith('.P')?'usdm':'spot'))
    if (!result) throw new Error(cw('symbolUnavailable',{symbol:ticker}))
    return result
  }
  async listSymbols():Promise<SymbolDescriptor[]> {
    if (!this.catalog.length) this.catalog = await chartApi.symbols()
    return this.catalog.map(s=>({ticker:s.id,description:`${s.name} · ${s.exchange.toUpperCase()} · ${cw(s.market==='usdm'?'perpetual':s.market==='spot'?'spot':'index')}`,type:s.market==='index'?'index':'crypto',market:s.market}))
  }
  async getSymbolInfo(ticker:string):Promise<SymbolInfo> {
    const s = await this.resolve(ticker)
    return { ...s.metadata,ticker:s.symbol,tickerid:velaSymbol(s.id),prefix:s.exchange,currency:s.currency,
      timezone:s.timezone,session:s.session,type:s.market==='usdm'?'futures':s.market==='index'?'index':'crypto',description:s.name}
  }
  async getBars(ticker:string,timeframe:string,range:BarRange):Promise<OHLCV[]> {
    const info = await this.resolve(ticker)
    const tf = timeframes[timeframe] ?? timeframe
    if (!info.timeframes.includes(tf)) throw new Error(cw('onlyTimeframes',{symbol:info.name,timeframes:info.timeframes.join(', ')}))
    const key = JSON.stringify([info.id,tf,range])
    if (this.inFlight.has(key)) return this.inFlight.get(key)!
    const run = this.load(info,tf,range)
    this.inFlight.set(key,run)
    try { return await run } finally { this.inFlight.delete(key) }
  }
  async getBarsProgressive(ticker:string,timeframe:string,range:BarRange,onBatch:(bars:OHLCV[])=>void,opts?:{signal?:AbortSignal}) {
    const info=await this.resolve(ticker),tf=timeframes[timeframe]??timeframe
    if(!info.timeframes.includes(tf))throw new Error(cw('unsupportedTimeframe',{symbol:info.name,timeframe:tf}))
    return this.load(info,tf,range,opts?.signal,onBatch)
  }
  private async load(info:ChartSymbol,tf:string,range:BarRange,signal?:AbortSignal,onBatch?:(bars:OHLCV[])=>void):Promise<OHLCV[]> {
    const abort = new AbortController()
    const stop=()=>abort.abort()
    signal?.addEventListener('abort',stop,{once:true})
    if(signal?.aborted)abort.abort()
    this.requests.add(abort)
    const forward = range.from !== undefined
    const target = range.limit ?? (forward ? Infinity : 1000)
    let end = range.to ?? Date.now()
    let start = range.from
    const collected:OHLCV[] = []
    try {
      while (collected.length<target && !this.closed) {
        const query:Record<string,string|number> = {symbol:info.id,timeframe:tf,end,limit:Math.min(target-collected.length,1000)}
        if (start!==undefined) query.start = start
        const result = await chartApi.bars(query,abort.signal)
        Object.assign(info,result.symbol)
        if (!result.bars.length) break
        collected.push(...result.bars)
        if(!forward)onBatch?.([...collected].sort((a,b)=>a.time-b.time))
        if (forward) {
          const next = result.bars[result.bars.length-1]!.closeTime
          if (next <= start! || next > end) break
          start = next
          continue
        }
        const next = result.bars[0]!.time - 1
        if (next>=end || (range.from!==undefined && next<range.from)) break
        end=next
      }
      return [...new Map(collected.map(b=>[b.time,b])).values()].sort((a,b)=>a.time-b.time)
    } catch(error) {
      if(abort.signal.aborted)return collected.sort((a,b)=>a.time-b.time)
      this.status(info.id,'error',String(error))
      throw error
    } finally { this.requests.delete(abort);signal?.removeEventListener('abort',stop) }
  }
  subscribe(ticker:string,timeframe:string,onBar:(bar:OHLCV)=>void) {
    const symbol = fromVela(ticker), tf=timeframes[timeframe]??timeframe
    const key=JSON.stringify([symbol,tf])
    let listeners=this.callbacks.get(key)
    if (!listeners) { this.subscriptions.set(key,{generation:++this.generation,sequence:0});listeners=new Set();this.callbacks.set(key,listeners);this.send('subscribe',symbol,tf) }
    listeners.add(onBar)
    this.connect()
    return ()=>{
      listeners!.delete(onBar)
      if (!listeners!.size) { this.callbacks.delete(key);this.send('unsubscribe',symbol,tf);this.subscriptions.delete(key) }
    }
  }
  private send(type:string,symbol:string,timeframe:string) {
    if (this.socket?.readyState===WebSocket.OPEN) this.socket.send(JSON.stringify({type,symbol,timeframe,generation:this.subscriptions.get(JSON.stringify([symbol,timeframe]))?.generation}))
  }
  private connect() {
    if (this.closed || this.socket && this.socket.readyState<2) return
    const socket = new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}${BASE}/stream`)
    this.socket=socket
    socket.onopen=()=>{for(const key of this.callbacks.keys()){this.subscriptions.set(key,{generation:++this.generation,sequence:0});const [symbol,tf]=JSON.parse(key);this.send('subscribe',symbol,tf)}}
    socket.onmessage=e=>{
      if(this.socket!==socket||this.closed)return
      const data=JSON.parse(e.data),key=JSON.stringify([data.symbol,data.timeframe]),subscription=this.subscriptions.get(key)
      if(!subscription||data.generation!==subscription.generation)return
      if(data.sequence!=null){if(data.sequence<=subscription.sequence)return;subscription.sequence=data.sequence}
      if(data.type==='bar') for(const cb of this.callbacks.get(JSON.stringify([data.symbol,data.timeframe]))??[]) cb(data.bar)
      if(data.type==='status'){this.statuses.set(data.symbol,{status:data.status,error:data.error});this.status(data.symbol,data.status,data.error)}
    }
    socket.onclose=()=>{
      if(!this.closed) { for(const key of this.callbacks.keys()){const id=JSON.parse(key)[0];this.statuses.set(id,{status:'offline'});this.status(id,'offline')}this.retry=setTimeout(()=>this.connect(),2000) }
    }
  }
  destroy() {
    this.closed=true;clearTimeout(this.retry);this.socket?.close()
    for(const request of this.requests) request.abort()
    this.callbacks.clear();this.subscriptions.clear()
  }
}
