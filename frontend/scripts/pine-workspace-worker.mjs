import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { PineTS, Indicator } from 'pinets'
import { checkPine, PINE_ENGINE_VERSION } from '../src/modules/chartWorkspace/pineCompatibility.mjs'
import { installPineRuntimeCompat,PINE_ADAPTER_VERSION } from '../src/modules/chartWorkspace/pineRuntimeCompat.mjs'
installPineRuntimeCompat()

const folder = process.argv[2]
if (process.argv.includes('--managed')) {
  const bytes = []
  for await (const chunk of process.stdin) bytes.push(chunk)
  if (Buffer.concat(bytes).toString() !== '1') process.exit(2)
}
const write = (name, value) => {
  const target = path.join(folder, name)
  fs.writeFileSync(target + '.tmp', JSON.stringify(value))
  fs.renameSync(target + '.tmp', target)
}
const hash = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex')
try {
  const input = JSON.parse(fs.readFileSync(path.join(folder, 'input.json'), 'utf8'))
  checkPine(input.source)
  const indicator = new Indicator(input.source, input.request.inputs)
  indicator.prepare()
  for (const [key, value] of Object.entries(input.request.props ?? {})) indicator.prop[key] = value
  const declaration = indicator.getDeclarationType()
  const meta = {kind:declaration, inputs:indicator.getInputsMeta(), props:indicator.getPropsMeta().map(p => ({...p, value:indicator.prop[p.name]}))}
  write('metadata.json', meta)
  if (input.prepareOnly) process.exit(0)
  if (declaration !== 'strategy') throw new Error('策略测试器仅运行 strategy()；指标请添加到图表')
  if (input.symbol.close_only) throw new Error('只有收盘价的数据不能用于成交模拟')
  const currency = indicator.prop.currency
  if (currency && currency !== 'NONE' && currency !== input.symbol.currency) {
    // USD accounting is accepted for USDT-quoted crypto as the engine's nominal unit,
    // but no FX conversion is performed; this is recorded in the effective config.
    if (!(currency === 'USD' && input.symbol.currency === 'USDT')) throw new Error('暂不支持跨报价币种换算')
  }
  const allSeries = input.series ?? {}
  const primaryKey = `${input.request.symbol}|${input.request.timeframe}`
  allSeries[primaryKey] = {symbol:input.symbol, bars:input.bars}
  const mapping = {'1':'1m','5':'5m','15':'15m','30':'30m','60':'1h','240':'4h','D':'1d','1D':'1d','W':'1w','1W':'1w','M':'1M','1M':'1M'}
  const boundary=(time,tf)=>{
    if(tf==='1M'){const date=new Date(time);date.setUTCMonth(date.getUTCMonth()+1,1);date.setUTCHours(0,0,0,0);return date.getTime()}
    const match=/^(\d+)([mhdw])$/.exec(tf)
    if(!match)throw new Error(`不支持的周期 ${tf}`)
    return time+Number(match[1])*({m:60000,h:3600000,d:86400000,w:604800000}[match[2]])
  }
  let catalog
  const resolve = async ticker => {
    if (ticker.replace(/^(?:opentrading|heimdall):/i,'') === input.request.symbol || ticker === input.symbol.symbol) return input.request.symbol
    if(input.frozen){
      const plain=ticker.replace(/^(?:opentrading|heimdall):/i,'')
      const candidates=Object.values(allSeries).map(item=>item.symbol)
      const found=candidates.find(s=>s.id===plain)||candidates.find(s=>`${s.exchange.toUpperCase()}:${s.symbol}${s.market==='usdm'?'.P':''}`===plain)
      if(found)return found.id
      throw new Error(`原快照没有品种 ${ticker}`)
    }
    catalog ??= await fetch(input.api + '/symbols').then(r => r.json())
    const normalized = ticker.replace(/^(?:opentrading|heimdall):/i,'')
    let found = catalog.find(s => s.id === normalized)
    if (!found) {
      const parts = normalized.split(':')
      found = catalog.find(s => s.symbol === parts.at(-1).replace(/\.P$/, '') &&
        s.exchange === (parts.length > 1 ? parts[0].toLowerCase() : input.symbol.exchange) &&
        s.market === (normalized.endsWith('.P') ? 'usdm' : input.symbol.market))
    }
    if (!found) throw new Error(`数据源不支持 ${ticker}`)
    return found.id
  }
  const series = async (ticker, timeframe) => {
    const symbol = await resolve(ticker), tf = mapping[timeframe] ?? timeframe
    const key = `${symbol}|${tf}`
    if (!allSeries[key]) {
      if (input.frozen) throw new Error(`原快照没有 ${key} 数据，无法使用原快照重跑`)
      const bars = []
      let cursor = input.request.start, info
      while (cursor <= input.request.end) {
        const query = new URLSearchParams({symbol,timeframe:tf,start:String(cursor),end:String(input.request.end),limit:'1000'})
        const response = await fetch(input.api + '/bars?' + query)
        if (!response.ok) throw new Error(`无法加载 ${key}: ${response.status}`)
        const data = await response.json()
        info = data.symbol
        const next = data.bars.filter(b => b.closed && b.closeTime <= input.request.end)
        if(next.length&&next.at(-1).closeTime<=cursor)throw new Error(`${key} 行情分页没有前进`)
        if(info.market!=='index')for(let i=1;i<next.length;i++)if(next[i-1].closeTime!==next[i].time)throw new Error(`${key} 行情存在缺口`)
        if(info.market!=='index'&&bars.length&&next.length&&bars.at(-1).closeTime!==next[0].time)throw new Error(`${key} 行情分页之间存在缺口`)
        bars.push(...next)
        if (!next.length || next.at(-1).closeTime > input.request.end) break
        cursor = next.at(-1).closeTime
      }
      if (!bars.length) throw new Error(`没有 ${key} 的历史数据`)
      if(info.market!=='index'){
        if(bars[0].time>boundary(input.request.start,tf))throw new Error(`${key} 开始区间数据不完整`)
        if(boundary(bars.at(-1).closeTime,tf)<=input.request.end)throw new Error(`${key} 结束区间数据不完整`)
        if(bars.some(b=>b.low>Math.min(b.open,b.close)||Math.max(b.open,b.close)>b.high||b.volume<0))throw new Error(`${key} OHLCV 数据无效`)
      }
      allSeries[key] = {symbol:info,bars}
      write('series.json',allSeries)
    }
    return allSeries[key]
  }
  const provider = {
    configure() {},
    async getMarketData(ticker,tf,limit,start,end) {
      const data = await series(ticker,tf)
      let bars = data.bars.filter(b => (start == null || b.time>=start) && (end == null || b.time<=end))
      if (limit && start == null) bars = bars.slice(-limit)
      return bars.map(b => ({...b,openTime:b.time,quoteAssetVolume:0,numberOfTrades:0,takerBuyBaseAssetVolume:0,takerBuyQuoteAssetVolume:0,ignore:0}))
    },
    async getSymbolInfo(ticker) {
      const key = await resolve(ticker)
      const info = key === input.request.symbol ? input.symbol : (await series(ticker,input.request.timeframe)).symbol
      return {...info.metadata,ticker:info.symbol,tickerid:key,prefix:info.exchange,currency:info.currency,
        timezone:info.timezone,session:info.session,type:info.market === 'usdm' ? 'futures':'crypto',description:info.name}
    }
  }
  const pine = new PineTS(provider,input.request.symbol,input.request.timeframe,input.bars.length,input.request.start,input.request.end)
  pine.setMaxLoops(500000)
  const orders = new Set(), equity = [], observed = new WeakSet(),cancelled=new WeakSet()
  const remember = context => {if(context.strategy)for(const order of context.strategy.pending_orders)orders.add(order)}
  const prepared = indicator.prepare(), original = prepared.fn
  prepared.fn = async context => {
    if(!observed.has(context)){
      observed.add(context)
      // Capture at the public strategy calls as well as bar boundaries: an order
      // can be placed and cancelled within one execution of the same candle.
      for(const method of ['entry','order','exit','close','close_all','cancel','cancel_all']){
        const call=context.pine.strategy[method]
        context.pine.strategy[method]=function(...args){
          remember(context)
          const before=method.startsWith('cancel')?[...(context.strategy?.pending_orders??[])]:[]
          const value=call.apply(this,args)
          for(const order of before)if(!(context.strategy?.pending_orders??[]).includes(order)&&order.status==='pending')cancelled.add(order)
          remember(context);return value
        }
      }
    }
    remember(context)
    const value = await original(context)
    if (context.strategy) {
      for (const order of context.strategy.pending_orders) orders.add(order)
      const state = context.strategy
      equity.push({time:context.marketData[context.idx]?.openTime, equity:state.equity, netprofit:state.netprofit, openprofit:state.openprofit})
    }
    return value
  }
  let context
  for await (const page of pine.run(indicator,undefined,2000)) {
    context = page.fullContext ?? page
    write('progress.json',{progress:Math.min(99,(page.idx+1)/input.bars.length*100)})
  }
  const state = context.strategy
  if (!state) throw new Error('脚本没有生成策略状态')
  const unsupported=context.warnings.filter(w=>/not (implemented|supported)|unsupported/i.test(w.message))
  if(unsupported.length)throw new Error('脚本使用了引擎尚未支持的功能：'+unsupported.map(w=>w.message).join('; '))
  const rawOrders = [...orders].map(o => ({...o,...cancelled.has(o)?{status:'cancelled'}:{}}))
  const trades = state.closedtrades
  const ledger=[...trades,...state.opentrades]
  const fills=rawOrders.filter(o=>o.status==='filled').map(order=>{
    const entries=ledger.filter(t=>t.entry_id===order.id&&t.entry_time===order.fill_time)
    const exits=trades.filter(t=>t.exit_id===order.id&&t.exit_time===order.fill_time)
    const quantity=[...entries,...exits].reduce((sum,t)=>sum+Math.abs(t.size),0)
    const direction=order.direction||(exits.length?-Math.sign(exits[0].size):0)
    return {...order,requested_qty:order.qty,qty:quantity||order.qty,direction}
  })
  const summary = Object.fromEntries(Object.entries(state).filter(([k,v]) => !k.startsWith('_') && (typeof v === 'number' || typeof v === 'string')))
  summary.config = state.config
  summary.win_rate = trades.length ? state.wintrades/trades.length*100 : 0
  summary.profit_factor = state.grossloss ? state.grossprofit/Math.abs(state.grossloss) : null
  summary.commission = [...trades,...state.opentrades].reduce((n,t) => n+(t.commission??0),0)
  write('series.json',allSeries)
  write('result.json',{summary,equity,trades,open_trades:state.opentrades,orders:rawOrders,
    fills,warnings:context.warnings,
    provenance:{engine:'PineTS',version:PINE_ENGINE_VERSION,adapter:PINE_ADAPTER_VERSION,engine_snapshot:input.engine_snapshot??null,node_version:process.version,source_hash:hash(input.source),data_hash:hash(allSeries),
      quote_currency:input.symbol.currency,account_currency:state.account_currency,bars:input.bars.length,
      first_bar:input.bars[0].time,last_bar:input.bars.at(-1).time}})
} catch (error) {
  write('error.json',{error:error.message,stack:error.stack})
  process.exitCode = 1
}
