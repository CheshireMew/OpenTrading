import type { Vela,VisibleRange } from '@luxalgo/vela'
import { registerStatePersistence, type ExternalIndicatorEntry } from '@luxalgo/vela/plugin'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import { checkPine } from './pineCompatibility.mjs'

const sources = new WeakMap<Vela,Map<string,{scriptId?:string;version?:number}>>()
// Vela's cell snapshot reads its initial bars budget, while setMarket changes the
// live budget. Preserve the requested depth when a cell is pooled by a layout.
registerStatePersistence({key:'heimdall.historyDepth',scope:'cell',serialize:ctx=>ctx.chart.market.bars,restore:(payload,ctx)=>{
  if(typeof payload==='number'&&Number.isFinite(payload)&&payload>0&&payload!==ctx.chart.market.bars)
    queueMicrotask(()=>{void ctx.chart.setMarket({bars:payload})})
}})
registerStatePersistence({key:'heimdall.viewport',scope:'cell',serialize:ctx=>ctx.chart.getVisibleRange(),restore:(payload,ctx)=>{
  const range=payload as VisibleRange|null
  if(!range||!Number.isFinite(range.from)||!Number.isFinite(range.to)||range.to<=range.from)return
  ctx.chart.setVisibleRange(range)
  const off=ctx.chart.on('load:end',()=>{off();ctx.chart.setVisibleRange(range)})
}})
export function markScript(chart:Vela,id:string,scriptId:string,version:number) {
  let map=sources.get(chart)
  if(!map){map=new Map();sources.set(chart,map)}
  map.set(id,{scriptId,version})
}
registerStatePersistence({key:'heimdall.pine',scope:'cell',serialize:ctx=>ctx.chart.indicators().filter(h=>h.source).map(h=>({
  id:h.id,name:h.title,script:h.source,language:'pine',inputs:h.inputValues(),props:h.propValues(),hidden:!h.visible,...sources.get(ctx.chart)?.get(h.id),
})),restore:(payload,ctx)=>{
  if(!Array.isArray(payload))return
  for(const item of payload){
    if(!item||typeof item.script!=='string'||typeof item.id!=='string')continue
    try{checkPine(item.script);ctx.addIndicator(item as ExternalIndicatorEntry);markScript(ctx.chart,item.id,item.scriptId,item.version)}
    catch(error){console.error('Pine 恢复失败',error)}
  }
}})

// Vela stores one drawings document per cell. Keep an explicit market dictionary
// so changing a cell's instrument never carries the previous instrument's lines.
export function installMarketDrawings(workspace:VelaWorkspace,onChange:()=>void) {
  const attached=new WeakSet<Vela>()
  const maps=new Map<string,Record<string,unknown>>()
  const owners=new WeakMap<Vela,string>()
  const restoring=new WeakSet<Vela>()
  const dispose=registerStatePersistence({key:'heimdall.marketDrawings',scope:'cell',
    serialize:ctx=>{
      const market=owners.get(ctx.chart)??ctx.chart.market.symbol??'',map=maps.get(ctx.cellId)??{}
      map[market]=ctx.chart.drawings.toJSON();maps.set(ctx.cellId,map)
      return {version:2,activeSymbol:market,markets:map}
    },restore:(payload,ctx)=>{
      if(payload&&typeof payload==='object'&&!Array.isArray(payload)){
        const value=payload as {version?:number;activeSymbol?:string;markets?:Record<string,unknown>}
        maps.set(ctx.cellId,value.version===2?value.markets??{}:payload as Record<string,unknown>)
        if(value.activeSymbol)owners.set(ctx.chart,value.activeSymbol)
        // applyState restores drawings before it switches the cell's market.
        // Those drawings already belong to the incoming document, not the old cell.
        restoring.add(ctx.chart)
        queueMicrotask(()=>restoring.delete(ctx.chart))
      }
    }})
  const setup=()=>{
    for(const cell of workspace.cells()){
      if(attached.has(cell.chart))continue
      attached.add(cell.chart)
      const chart=cell.chart
      chart.on('viewport:changed',onChange)
      if(!owners.has(chart))owners.set(chart,cell.symbol)
      chart.on('load:start',event=>{
        if(restoring.has(chart)){owners.set(chart,event.symbol);restoring.delete(chart);return}
        const current=owners.get(chart)!
        if(event.symbol===current)return
        const map=maps.get(cell.id)??{}
        map[current]=chart.drawings.toJSON()
        maps.set(cell.id,map)
        owners.set(chart,event.symbol)
        chart.drawings.fromJSON(map[event.symbol]??{version:1,drawings:[]})
      })
      chart.on('load:end',event=>{
        restoring.delete(chart);owners.set(chart,event.symbol)
        onChange()
      })
      // Vela updates the object panel's market label on this event but does not
      // repaint its rows. Clearing the old selection uses its public refresh path.
      chart.on('market:changed',()=>chart.drawings.select(null))
    }
  }
  setup()
  const off=workspace.on('cell:created',setup)
  return ()=>{off();dispose()}
}
