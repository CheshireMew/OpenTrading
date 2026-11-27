import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import { registerWidgetAction, type WidgetContext } from '@luxalgo/vela/plugin'
import type { Vela } from '@luxalgo/vela'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { WorkspaceReplay } from './workspaceReplay'
import type { WorkspaceTradingTarget, WorkspaceTradingOrders } from './workspaceTradingOrders'
import { createWorkspaceTradeProjection, type TradingDrag } from './workspaceTradeProjection'
import { WorkspaceRenderer } from './chartPresentation'
import { fromVela } from './provider'
import type { OrderTarget } from './replayModel'
import type { ReplayLine } from './replayOrderLayer'
import { cw, formatNumber } from './locale'

export function createWorkspaceTradingInteraction(deps: {
  workspace: () => VelaWorkspace | undefined; replay: Pick<WorkspaceReplay, 'active' | 'open' | 'picking' | 'start' | 'error'>
  target: Readonly<Ref<WorkspaceTradingTarget>>
  orders: Pick<WorkspaceTradingOrders, 'order' | 'menu' | 'move' | 'addExit' | 'place' | 'openMenu'>; picked: () => void
}) {
const r=deps.replay,t=deps.target,order=deps.orders.order
const tradingVisible = computed(() => r.active.value || t.value.active.value)
const overlayHost=shallowRef<HTMLElement>(),timeZone=ref('Asia/Shanghai')
const drag=ref<TradingDrag>()
const menu=deps.orders.menu
let renderer: WorkspaceRenderer | undefined, attached: HTMLElement | undefined, offCell: (()=>void) | undefined
let menuHost: HTMLElement | undefined, offMenu: (()=>void)[] = []
let pendingContext: { chart: Vela; symbol: string; price: number; y: number } | undefined
const projection=createWorkspaceTradeProjection({target:t,order,preview:()=>drag.value,visible:()=>tradingVisible.value,renderer:()=>renderer})
const {geometry,visibleLines,project}=projection
function cancelDrag() { drag.value=undefined; window.removeEventListener('pointermove',dragMove);window.removeEventListener('pointerup',dragEnd);window.removeEventListener('pointercancel',cancelDrag);window.removeEventListener('keydown',dragKey) }
function beginLineDrag(event:PointerEvent,line:ReplayLine) {
  if(line.target==='entry' && t.value.account.position) beginDrag(event,'new')
  else if(line.draggable) beginDrag(event,line.target)
}
function beginDrag(event:PointerEvent,target:OrderTarget|'new') {
  if (event.button!==0 || !order.value) return
  event.preventDefault();event.stopPropagation();cancelDrag()
  const price=target==='entry'||target==='new'?order.value.price:order.value.exits.find(exit=>exit.target===target)?.price
  if(price===undefined)return
  drag.value={target,price,owner:order.value,moved:false}
  window.addEventListener('pointermove',dragMove);window.addEventListener('pointerup',dragEnd);window.addEventListener('pointercancel',cancelDrag);window.addEventListener('keydown',dragKey)
}
function dragMove(event:PointerEvent) { const point=renderer?.replayOrders.pointAt?.(event.clientX,event.clientY);if(point&&drag.value){drag.value.price=t.value.roundedPrice(point.price);drag.value.moved=true} }
function dragEnd() {
  const value=drag.value;cancelDrag()
  if(!value?.moved || value.owner!==order.value)return
  if(value.target==='new'){deps.orders.addExit(value.price);return}
  if(value.target!=='entry'&&!order.value?.exits.some(exit=>exit.target===value.target))return
  deps.orders.move(value.target,value.price)
}
function dragKey(event:KeyboardEvent) { if(event.key==='Escape'){event.preventDefault();cancelDrag()} }
function lineDown(event:PointerEvent) {
  if(!tradingVisible.value || (event.target as HTMLElement).closest('button,input,select,.cw-trading-controls,.cw-replay-order,.cw-replay-menu,.cw-replay-price-editor'))return
  const target=renderer?.replayOrders.hitAt?.(event.clientX,event.clientY)
  if(target){event.preventDefault();event.stopImmediatePropagation();beginDrag(event,target)}
}
function captureContext(event:MouseEvent) {
  if((event.target as HTMLElement).closest('.cw-trading-controls'))return
  pendingContext=undefined;menu.value=undefined
  for(const cell of deps.workspace()?.cells()??[]){
    if(!cell.host.contains(event.target as Node))continue
    const view=WorkspaceRenderer.forHost(cell.host),point=view?.replayOrders.pointAt?.(event.clientX,event.clientY),rect=view?.replayOrders.host?.getBoundingClientRect()
    if(!point||!rect)continue
    deps.workspace()?.setActiveCell(cell.id)
    pendingContext={chart:cell.chart,symbol:fromVela(cell.symbol),price:t.value.roundedPrice(point.price),y:event.clientY-rect.top}
    break
  }
}
function detachMenus(){menuHost?.removeEventListener('contextmenu',captureContext,{ capture: true });offMenu.forEach(off=>off());offMenu=[];menuHost=undefined;pendingContext=undefined}
function attachMenus(){
  menuHost=deps.workspace()?.context().host
  if(!menuHost)return
  menuHost.addEventListener('contextmenu',captureContext,{ capture: true })
  const available=(ctx:WidgetContext)=>!!pendingContext&&ctx.host===menuHost&&ctx.chart===pendingContext.chart&&fromVela(ctx.symbol)===pendingContext.symbol&&!t.value.loading.value
  for(const target of ['context:body','context:price-axis'] as const){
    for(const side of [1,-1] as const)offMenu.push(registerWidgetAction({
      id:`opentrading-trading-${target}-${side}`,target,order:side===1?-20:-19,
      get label(){return cw(side===1?'replayBuyAt':'replaySellAt',{price:formatNumber(pendingContext?.price??0,8)})},
      when:ctx=>available(ctx)&&!order.value,
      run:()=>{if(pendingContext)void deps.orders.place(side,'limit',pendingContext.price)},
    }))
    offMenu.push(registerWidgetAction({
      id:`opentrading-trading-${target}-exit`,target,order:-18,
      get label(){return cw('paperExitAt',{price:formatNumber(pendingContext?.price??0,8),kind:cw(t.value.account.exitKind(pendingContext?.price??0)==='tp'?'replayLimitTP':'replayStopOrder')})},
      when:ctx=>available(ctx)&&!!order.value&&!!t.value.account.exitKind(pendingContext!.price),
      run:()=>{if(pendingContext)deps.orders.openMenu(pendingContext.price,pendingContext.y)},
    }))
  }
}
function pick(event:MouseEvent) {
  if(!r.open.value||!r.picking.value||(event.target as HTMLElement).closest('button,input,select,.cw-trading-controls'))return
  const point=renderer?.replayOrders.pointAt?.(event.clientX,event.clientY)
  if(point){event.preventDefault();event.stopImmediatePropagation();void r.start(point.time).then(()=>{if(r.active.value&&!r.error.value)deps.picked()})}
}
function detach() { cancelDrag();attached?.removeEventListener('pointerdown',lineDown,{ capture: true });attached?.removeEventListener('click',pick,{ capture: true });renderer?.setReplayOrders({lines:[],geometry:undefined});attached=undefined;overlayHost.value=undefined }
function attach() { detach();const cell=deps.workspace()?.active;if(!cell)return;renderer=WorkspaceRenderer.forHost(cell.host);timeZone.value=renderer?.getConfig().timeScale.timezone??'Asia/Shanghai';attached=cell.host;overlayHost.value=renderer?.replayOrders.host;attached.addEventListener('pointerdown',lineDown,{ capture: true });attached.addEventListener('click',pick,{ capture: true });project() }
const stopWorkspace=watch(deps.workspace,value=>{offCell?.();detachMenus();attach();attachMenus();offCell=value?.on('cell:active',attach)},{flush:'post',immediate:true})
const stopActive=watch(r.active,()=>{menu.value=undefined;attach()})
const stopSymbol=watch(()=>t.value.symbol.value?.id,()=>{menu.value=undefined;attach()})
return {overlayHost,timeZone,geometry,visibleLines,beginLineDrag,beginDrag,cancelDrag,attach,
  dispose(){stopWorkspace();stopActive();stopSymbol();offCell?.();detachMenus();detach();projection.dispose()} }
}
