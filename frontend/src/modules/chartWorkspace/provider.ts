import type { DataProvider, BarRange, SymbolDescriptor, SymbolInfo } from '@luxalgo/vela'
import type { OHLCV } from '@luxalgo/vela'
import { chartApi, type ChartSymbol, BASE } from './api'
import { cw, exchangeLabel } from './locale'
import { catalogSymbolIcon } from './symbolIcons'
import { marketLabelKey, marketSymbolType } from './symbolSearch'

export const timeframes:Record<string,string> = {'1':'1m','5':'5m','15':'15m','30':'30m','60':'1h','240':'4h','D':'1d','1D':'1d','W':'1w','1W':'1w','M':'1M','1M':'1M'}
export const velaSymbol = (id:string) => 'opentrading:' + id
export const fromVela = (id:string) => id.replace(/^(?:opentrading|heimdall|replay\d*):/,'')
export type LiveQuote = { price: number; observedAt: number }
type HistoryRepair = { abort: AbortController; bars: Map<number, OHLCV>; failures: number; timer?: ReturnType<typeof setTimeout> }

export class OpenTradingProvider implements DataProvider {
  catalog:ChartSymbol[] = []
  statuses = new Map<string,{status:string;error?:string}>()
  private socket?:WebSocket
  private retry?:ReturnType<typeof setTimeout>
  private generation=0
  private subscriptions=new Map<string,{generation:number;sequence:number}>()
  private closed = false
  private paused = false
  private callbacks = new Map<string,Set<(bar:OHLCV)=>void>>()
  private quoteCallbacks = new Map<string,Set<(quote:LiveQuote)=>void>>()
  private requests = new Set<AbortController>()
  private inFlight = new Map<string,Promise<OHLCV[]>>()
  private catalogRequests = new Map<string, Promise<void>>()
  private lastBars = new Map<string, number>()
  private repairs = new Map<string, HistoryRepair>()
  constructor(private status:(symbol:string,status:string,error?:string)=>void) {}
  async resolve(ticker:string):Promise<ChartSymbol> {
    if (!this.catalog.length) this.catalog = await chartApi.symbols()
    const normalized = fromVela(ticker)
    const parts = normalized.split(':')
    const symbol = parts[parts.length-1]!.replace(/\.P$/, '')
    const exchange = parts.length > 1 ? parts[0]!.toLowerCase() : 'binance'
    const market = parts.length > 2 ? parts[1]!.toLowerCase() : normalized.endsWith('.P') ? 'usdm' : 'spot'
    const find = () => this.catalog.find(s => s.id === normalized)
      ?? this.catalog.find(s => s.symbol === symbol && s.exchange === exchange && s.market === market)
    let result = find()
    if (!result) {
      // Catalogs publish independently. A saved layout may refer to a venue
      // that is still loading; never substitute another market with that symbol.
      const key = `${exchange}:${market}:${symbol}`
      let request = this.catalogRequests.get(key)
      if (!request) {
        request = chartApi.symbols(key).then(catalog => {
          if (!this.closed) this.catalog.splice(0, this.catalog.length, ...catalog)
        }).finally(() => { this.catalogRequests.delete(key) })
        this.catalogRequests.set(key, request)
      }
      await request
      result = find()
    }
    if (!result) throw new Error(cw('symbolUnavailable',{symbol:ticker}))
    return result
  }
  async listSymbols():Promise<SymbolDescriptor[]> {
    if (!this.catalog.length) this.catalog = await chartApi.symbols()
    return this.catalog.map(s=>({ticker:s.id,description:`${s.name} · ${exchangeLabel(s.exchange)} · ${cw(marketLabelKey(s.market))}`,type:marketSymbolType(s.market),market:s.market}))
  }
  resolveSymbolIcon(symbol: SymbolDescriptor) { return catalogSymbolIcon(this.catalog, symbol.ticker) }
  async getSymbolInfo(ticker:string):Promise<SymbolInfo> {
    const s = await this.resolve(ticker)
    return { ...s.metadata,ticker:s.symbol,tickerid:velaSymbol(s.id),prefix:s.exchange,currency:s.currency,
      timezone:s.timezone,session:s.session,type:marketSymbolType(s.market),description:s.name}
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
      const result = [...new Map(collected.map(b=>[b.time,b])).values()].sort((a,b)=>a.time-b.time)
      const key = JSON.stringify([info.id, tf])
      if (result.length && !this.repairs.has(key)) this.lastBars.set(key, Math.max(this.lastBars.get(key) ?? 0, result[result.length - 1]!.time))
      return result
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
    if (!listeners) { listeners=new Set();this.callbacks.set(key,listeners) }
    listeners.add(onBar)
    this.syncSubscription(key)
    return ()=>{
      listeners!.delete(onBar)
      if (!listeners!.size) { this.callbacks.delete(key);this.cancelRepair(key) }
      this.syncSubscription(key)
    }
  }
  subscribeQuotes(ticker:string,timeframe:string,onQuote:(quote:LiveQuote)=>void) {
    const key=JSON.stringify([fromVela(ticker),timeframes[timeframe]??timeframe])
    let listeners=this.quoteCallbacks.get(key)
    if(!listeners){listeners=new Set();this.quoteCallbacks.set(key,listeners)}
    listeners.add(onQuote)
    this.syncSubscription(key)
    return ()=>{listeners!.delete(onQuote);if(!listeners!.size)this.quoteCallbacks.delete(key);this.syncSubscription(key)}
  }
  private syncSubscription(key: string) {
    const wanted = this.quoteCallbacks.has(key) || !this.paused && this.callbacks.has(key)
    const [symbol, tf] = JSON.parse(key)
    if (wanted && !this.subscriptions.has(key)) {
      this.subscriptions.set(key, { generation: ++this.generation, sequence: 0 })
      this.send('subscribe', symbol, tf)
    } else if (!wanted && this.subscriptions.has(key)) {
      this.send('unsubscribe', symbol, tf)
      this.subscriptions.delete(key)
    }
    if (this.subscriptions.size) this.connect()
    else {
      clearTimeout(this.retry);this.retry=undefined
      const socket = this.socket;this.socket=undefined;socket?.close()
    }
  }
  private cancelRepair(key: string) {
    const repair = this.repairs.get(key)
    if (repair) { clearTimeout(repair.timer);repair.abort.abort();this.repairs.delete(key) }
  }
  private publish(key: string, bar: OHLCV) {
    this.lastBars.set(key, Math.max(this.lastBars.get(key) ?? 0, bar.time))
    for (const callback of this.callbacks.get(key) ?? []) callback(bar)
  }
  private async repairHistory(key: string, repair: HistoryRepair) {
    const current = () => !this.closed && !this.paused && this.repairs.get(key) === repair && this.callbacks.has(key)
    const [symbol, tf] = JSON.parse(key)
    try {
      const info = await this.resolve(symbol)
      const bars = await this.load(info, tf, { from: this.lastBars.get(key)!, to: Date.now() }, repair.abort.signal)
      if (!current()) return
      // Include the last displayed candle again: it may have closed while the
      // page was hidden. Buffer live plot updates until all intervening bars
      // have landed; trading quotes continue independently throughout the repair.
      const merged = new Map(bars.map(bar => [bar.time, bar]))
      for (const [time, bar] of repair.bars) merged.set(time, bar)
      for (const bar of [...merged.values()].sort((left, right) => left.time - right.time)) {
        if (!current()) return
        this.publish(key, bar)
      }
      this.repairs.delete(key)
    } catch (cause) {
      if (!current()) return
      this.status(symbol, 'error', String(cause))
      repair.failures++
      repair.timer = setTimeout(() => void this.repairHistory(key, repair), Math.min(30_000, 1500 * 2 ** Math.min(repair.failures, 4)))
    }
  }
  setPaused(paused: boolean) {
    if (this.closed || this.paused === paused) return
    this.paused = paused
    if (paused) for (const key of this.repairs.keys()) this.cancelRepair(key)
    for (const key of new Set([...this.callbacks.keys(), ...this.quoteCallbacks.keys()])) {
      if (!paused && this.callbacks.has(key) && this.lastBars.has(key)) {
        const repair = { abort: new AbortController(), bars: new Map<number, OHLCV>(), failures: 0 }
        this.repairs.set(key, repair)
        void this.repairHistory(key, repair)
      }
      this.syncSubscription(key)
    }
  }
  private send(type:string,symbol:string,timeframe:string) {
    if (this.socket?.readyState===WebSocket.OPEN) this.socket.send(JSON.stringify({type,symbol,timeframe,generation:this.subscriptions.get(JSON.stringify([symbol,timeframe]))?.generation}))
  }
  private connect() {
    if (this.closed || !this.subscriptions.size || this.socket && this.socket.readyState<2) return
    clearTimeout(this.retry);this.retry=undefined
    const socket = new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}${BASE}/stream`)
    this.socket=socket
    socket.onopen=()=>{if(this.socket!==socket||this.closed)return;for(const key of this.subscriptions.keys()){this.subscriptions.set(key,{generation:++this.generation,sequence:0});const [symbol,tf]=JSON.parse(key);this.send('subscribe',symbol,tf)}}
    socket.onmessage=e=>{
      if(this.socket!==socket||this.closed)return
      const data=JSON.parse(e.data),key=JSON.stringify([data.symbol,data.timeframe]),subscription=this.subscriptions.get(key)
      if(!subscription||data.generation!==subscription.generation)return
      if(data.sequence!=null){if(data.sequence<=subscription.sequence)return;subscription.sequence=data.sequence}
      if(data.type==='bar') {
        if (!this.paused) {
          const repair = this.repairs.get(key)
          if (repair) {
            repair.bars.set(data.bar.time, data.bar)
            if (repair.bars.size > 2000) repair.bars.delete(Math.min(...repair.bars.keys()))
          } else this.publish(key, data.bar)
        }
        // Historical repair bars must update charts, never execute live orders.
        if(data.live===true && Number.isFinite(data.observed_at))
          for(const cb of this.quoteCallbacks.get(key)??[]) cb({price:data.bar.close,observedAt:data.observed_at})
      }
      if(data.type==='status'){this.statuses.set(data.symbol,{status:data.status,error:data.error});this.status(data.symbol,data.status,data.error)}
    }
    socket.onclose=()=>{
      if(this.socket!==socket||this.closed)return
      this.socket=undefined
      if(this.subscriptions.size) { for(const key of this.subscriptions.keys()){const id=JSON.parse(key)[0];this.statuses.set(id,{status:'offline'});this.status(id,'offline')}this.retry=setTimeout(()=>this.connect(),2000) }
    }
  }
  destroy() {
    this.closed=true;clearTimeout(this.retry);const socket=this.socket;this.socket=undefined;socket?.close()
    for (const key of this.repairs.keys()) this.cancelRepair(key)
    for(const request of this.requests) request.abort()
    this.callbacks.clear();this.subscriptions.clear()
    this.quoteCallbacks.clear()
    this.lastBars.clear()
  }
}
