import { computed, shallowRef, watchEffect, type Ref } from 'vue'
import type { WorkspaceTradingTarget, WorkspaceTradingOrders } from './workspaceTradingOrders'
import type { WorkspaceRenderer } from './chartPresentation'
import type { OrderTarget } from './replayModel'
import { periodStart } from './replayModel'
import type { ReplayGeometry, ReplayLine, ReplayLayerSource } from './replayOrderLayer'
import { cw, formatNumber } from './locale'

export type TradingDrag = { target: OrderTarget | 'new'; price: number; owner: object; moved: boolean }
export function createWorkspaceTradeProjection(deps: {
  target: Readonly<Ref<WorkspaceTradingTarget>>; order: WorkspaceTradingOrders['order']; preview: () => TradingDrag | undefined
  visible: () => boolean; renderer: () => WorkspaceRenderer | undefined
}) {
const t = deps.target, order = deps.order
const geometry = shallowRef<ReplayGeometry>({right:0,top:0,bottom:0,lines:[]})
let signature = ''
const visibleLines = computed(() => {
  const bounds=geometry.value
  const lines=bounds.lines.filter(line=>line.y>=bounds.top&&line.y<=bounds.bottom).map(line=>({...line,labelY:line.y})).sort((a,b)=>a.y-b.y)
  for(let i=0;i<lines.length;i++)lines[i]!.labelY=Math.max(lines[i]!.y,i?lines[i-1]!.labelY+30:bounds.top+15)
  for(let i=lines.length-1;i>=0;i--)lines[i]!.labelY=Math.min(lines[i]!.labelY,i===lines.length-1?bounds.bottom-15:lines[i+1]!.labelY-30)
  return lines
})
function project() {
  const value=order.value, drag=deps.preview(), preview=drag?.owner===value?drag:undefined, lines:ReplayLine[]=[]
  if(deps.visible()&&value){
    const price=(target:OrderTarget)=>preview?.target===target?preview.price:target==='entry'?value.price:value.exits.find(exit=>exit.target===target)?.price
    lines.push({target:'entry',price:price('entry')!,label:cw(value.side===1?'replayLong':'replayShort'),color:'#5086f5',draggable:!t.value.account.position&&('kind' in value)&&value.kind==='limit'})
    for(const exit of value.exits)lines.push({target:exit.target,price:price(exit.target)!,quantity:exit.quantity,label:cw(exit.kind==='tp'?'replayTP':'replaySL'),color:exit.kind==='tp'?'#089981':'#f23645',draggable:true})
    if(preview?.target==='new'&&preview.moved){const kind=t.value.account.exitKind(preview.price);if(kind)lines.push({target:'exit:0',price:preview.price,label:cw(kind==='tp'?'replayTP':'replaySL'),color:kind==='tp'?'#089981':'#f23645',draggable:false})}
  }
  const markers: NonNullable<ReplayLayerSource['markers']> = []
  if(deps.visible()){
    for(const trade of t.value.account.trades){
      markers.push({time:periodStart(trade.enteredAt-1,t.value.timeframe.value),price:trade.entry,side:trade.side,color:'#5086f5'})
      markers.push({time:periodStart(trade.exitedAt-1,t.value.timeframe.value),price:trade.exit,side:trade.side===1?-1:1,color:trade.profit>=0?'#089981':'#f23645'})
    }
    const p=t.value.account.position
    if(p)markers.push({time:periodStart(p.enteredAt-1,t.value.timeframe.value),price:p.price,side:p.side,color:'#5086f5'})
  }
  deps.renderer()?.setReplayOrders({lines,markers,geometry:value=>{const next=JSON.stringify(value);if(next!==signature){signature=next;geometry.value=value}}})
}
const stopProjection = watchEffect(project)
const stopMarks = watchEffect(cleanup => {
  const chart=t.value.chart
  if(!chart)return
  const next=new Set<string>()
  const mark=(id:string,time:number,price:number,label:string,color:string,letter:string)=>{
    next.add(id);chart.marks.add({id,time:Math.max(0,time-1),group:'replay-trades',glyph:{color,letter},title:label,
      tooltip:label+' · '+formatNumber(price,8),content:{text:label+' · '+formatNumber(price,8)}})
  }
  t.value.account.trades.forEach((trade,index)=>{
    mark('replay-entry-'+index,trade.enteredAt,trade.entry,cw(trade.side===1?'replayLong':'replayShort'),'#5086f5',trade.side===1?'▲':'▼')
    mark('replay-exit-'+index,trade.exitedAt,trade.exit,cw(trade.reason==='tp'?'replayTP':trade.reason==='sl'?'replaySL':'replayClose'),trade.profit>=0?'#089981':'#f23645','×')
  })
  const p=t.value.account.position
  if(p)mark('replay-open',p.enteredAt,p.price,cw(p.side===1?'replayLong':'replayShort'),'#5086f5',p.side===1?'▲':'▼')
  cleanup(() => { for (const id of next) chart.marks.remove(id) })
})
return { geometry, visibleLines, project,
  clear() { deps.renderer()?.setReplayOrders({ lines: [], geometry: undefined }) },
  dispose() { stopProjection(); stopMarks(); deps.renderer()?.setReplayOrders({ lines: [], geometry: undefined }) } }
}
