<template>
  <WorkspaceReplayControls :controller="r" :paper="paper" :host="overlayHost" :geometry="geometry" :time-zone="timeZone" :date-open="dateOpen" :order-error="orderError" :visible="pageActive" @date="showDate" @toggle="togglePlayback" @place="side=>place(side,'market')" @clear-order-error="orderError=''" />
  <WorkspaceReplayDatePicker :open="dateOpen" :value="date" :time-zone="timeZone" :busy="r.loading.value" :error="r.error.value" @select="chooseDate" @random="chooseRandom" @retry="retryDate" @close="closeDate" @pick="dateOpen=false;r.picking.value=true" />
  <Teleport v-if="overlayHost" :to="overlayHost">
    <div class="cw-replay-overlay" @keydown.esc="cancelDrag();menu=undefined;editing=undefined">
      <button v-if="hover && !t.loading.value" class="cw-replay-plus" :style="{top:hover.y+'px',left:geometry.right+'px'}" @pointerdown.stop @click="openAxisMenu">＋</button>
      <div v-if="menu" ref="menuPanel" class="cw-replay-menu" :style="panelStyle(menuSize,menu.y)" @pointerdown.stop>
        <form v-if="order" class="cw-replay-exit-ticket" @submit.prevent="submitExitAt">
          <label>{{ cw('replayPrice') }}<input type="number" min="0.00000001" step="any" v-model.number="menu.price" required /></label>
          <WorkspaceQuantityField v-model="menu.quantity" :max="order.quantity" :step="quantityStep" :unit="baseCurrency" />
          <p v-if="menuError" role="alert">{{ menuError }}</p>
          <button type="submit" :disabled="!t.account.exitKind(menu.price)">{{ cw(t.account.exitKind(menu.price)==='tp'?'replayLimitTP':'replayStopOrder') }}</button>
        </form>
        <button @click="menu=undefined">{{ cw('close') }}</button>
      </div>
      <svg class="cw-replay-connectors" aria-hidden="true"><path v-for="line in visibleLines.filter(row=>row.labelY!==row.y)" :key="line.target" :stroke="line.color" :d="`M ${Math.max(0,geometry.right-4)} ${line.y} V ${line.labelY}`" /></svg>
      <div v-for="line in visibleLines" :key="line.target" class="cw-replay-order" :class="{'cw-replay-draggable':line.draggable || line.target==='entry' && t.account.position}" :style="{top:line.labelY+'px',right:Math.max(4,(overlayHost?.clientWidth??geometry.right)-geometry.right+4)+'px',maxWidth:Math.max(1,geometry.right-8)+'px',borderColor:line.color}" @pointerdown.stop="beginLineDrag($event,line)" @dblclick.stop="line.draggable && openEditor(line.target,line.price)">
        <button class="cw-replay-handle" :style="{color:line.color}" :aria-label="line.label">{{ line.label }} {{ formatNumber(line.price,8) }}</button>
        <template v-if="line.target==='entry'">
          <span>{{ formatQuantity(order?.quantity) }} {{ baseCurrency }} · {{ t.account.position?formatNumber(t.account.unrealized):cw('replayPending') }} {{ t.symbol.value?.currency }}</span>
          <button :aria-label="cw('replayAddExit')" @pointerdown.stop="beginDrag($event,'new')" @dblclick.stop>{{ cw('replayAddExit') }} ↕</button>
        </template>
        <template v-else>
          <span v-if="line.quantity!==undefined">{{ formatQuantity(line.quantity) }}</span>
          <span>{{ formatNumber(estimate(line.price,line.quantity)) }} {{ t.symbol.value?.currency }}</span>
        </template>
        <button class="cw-replay-close" :disabled="line.target==='exit:0'" :aria-label="cw(line.target==='entry' && t.account.position?'replayClose':'replayCancel')" @pointerdown.stop @dblclick.stop @click.stop="remove(line.target)">×</button>
      </div>
      <form v-if="editing" ref="editorPanel" class="cw-replay-price-editor" :style="panelStyle(editorSize,geometry.top+24)" @pointerdown.stop @keydown.esc.stop="editing=undefined" @submit.prevent="applyPrice">
        <label>{{ cw('replayPrice') }}<input type="number" min="0.00000001" step="any" v-model="editPrice" required autofocus /></label>
        <WorkspaceQuantityField v-if="editPartial" v-model="editQuantity" :max="order?.quantity" :step="quantityStep" :unit="baseCurrency" />
        <p v-if="editError" role="alert">{{ editError }}</p>
        <div class="cw-replay-editor-actions"><button type="submit">{{ cw('replayApply') }}</button><button type="button" @click="editing=undefined">{{ cw('close') }}</button></div>
      </form>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, shallowRef, watch, watchEffect } from 'vue'
import { registerWidgetAction, type WidgetContext } from '@luxalgo/vela/plugin'
import type { Vela } from '@luxalgo/vela'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { WorkspaceReplay } from '@/modules/chartWorkspace/workspaceReplay'
import type { WorkspacePaper } from '@/modules/chartWorkspace/workspacePaper'
import { fromVela } from '@/modules/chartWorkspace/provider'
import type { OrderKind, OrderTarget, Side } from '@/modules/chartWorkspace/replayModel'
import { replayDateInput, replayDateTime, periodStart } from '@/modules/chartWorkspace/replayModel'
import { WorkspaceRenderer } from '@/modules/chartWorkspace/chartPresentation'
import type { ReplayGeometry, ReplayLine, ReplayLayerSource } from '@/modules/chartWorkspace/replayOrderLayer'
import { cw, formatDate, formatNumber } from '@/modules/chartWorkspace/locale'
import WorkspaceReplayDatePicker from './WorkspaceReplayDatePicker.vue'
import WorkspaceReplayControls from './WorkspaceReplayControls.vue'
import WorkspaceQuantityField from './WorkspaceQuantityField.vue'
import { formatQuantity } from '@/modules/chartWorkspace/replayQuantity'

const props = defineProps<{ controller: WorkspaceReplay; paper: WorkspacePaper; workspace?: VelaWorkspace }>()
const r = props.controller
const pageActive = ref(true)
const t = computed(() => r.active.value ? r : props.paper)
const tradingVisible = computed(() => r.active.value || props.paper.active.value)
const overlayHost = shallowRef<HTMLElement>(), dateOpen = ref(false), timeZone = ref('Asia/Shanghai'), date = ref(defaultDate())
const geometry = shallowRef<ReplayGeometry>({right:0,top:0,bottom:0,lines:[]})
const hover = ref<{price:number;y:number}>(), menu = ref<{price:number;y:number;quantity:number}>(),menuError=ref('')
const drag = ref<{target:OrderTarget|'new';price:number;owner:object;moved:boolean}>(), editing = ref<OrderTarget>(), editPrice = ref('')
const editQuantity=ref(0),editError=ref('')
const orderError=ref('')
const menuPanel=ref<HTMLElement>(),editorPanel=ref<HTMLElement>()
const menuSize=ref({width:236,height:300}),editorSize=ref({width:280,height:220})
function panelStyle(size:{width:number;height:number},preferredTop:number) {
  const bounds=geometry.value,bottom=Math.max(bounds.bottom,(overlayHost.value?.clientHeight??0)-8),width=Math.max(1,bounds.right-16),height=Math.max(1,bottom-bounds.top-16)
  return {left:Math.max(8,bounds.right-Math.min(size.width,width)-8)+'px',
    top:Math.max(bounds.top+8,Math.min(preferredTop,bottom-Math.min(size.height,height)-8))+'px',
    maxWidth:width+'px',maxHeight:height+'px'}
}
watch([menuPanel,editorPanel],([menu,editor],_previous,cleanup)=>{
  const observer=new ResizeObserver(()=>{
    if(menu)menuSize.value={width:menu.offsetWidth,height:menu.offsetHeight}
    if(editor)editorSize.value={width:editor.offsetWidth,height:editor.offsetHeight}
  })
  if(menu)observer.observe(menu)
  if(editor)observer.observe(editor)
  cleanup(()=>observer.disconnect())
},{flush:'post'})
const order = computed(() => t.value.account.position ?? t.value.account.pending ?? t.value.account.draft)
const quantityStep = computed(() => Number(t.value.symbol.value?.metadata?.mincontract) || 0.00000001)
const baseCurrency = computed(() => String(t.value.symbol.value?.metadata?.basecurrency ?? ''))
const estimate = (price:number,quantity?:number) => order.value ? (price-order.value.price)*order.value.side*(quantity??order.value.quantity) : 0
const editPartial=computed(()=>editing.value!=='entry'&&order.value?.exits.find(exit=>exit.target===editing.value)?.quantity!==undefined)
const visibleLines = computed(() => {
  const bounds=geometry.value
  const lines=bounds.lines.filter(line=>line.y>=bounds.top&&line.y<=bounds.bottom).map(line=>({...line,labelY:line.y})).sort((a,b)=>a.y-b.y)
  for(let i=0;i<lines.length;i++)lines[i]!.labelY=Math.max(lines[i]!.y,i?lines[i-1]!.labelY+30:bounds.top+15)
  for(let i=lines.length-1;i>=0;i--)lines[i]!.labelY=Math.min(lines[i]!.labelY,i===lines.length-1?bounds.bottom-15:lines[i+1]!.labelY-30)
  return lines
})
let renderer: WorkspaceRenderer | undefined, attached: HTMLElement | undefined, offCell: (()=>void) | undefined, signature = ''
let menuHost: HTMLElement | undefined, offMenu: (()=>void)[] = []
let pendingContext: { chart: Vela; symbol: string; price: number; y: number } | undefined
const marked = new Set<string>()
function defaultDate() { return replayDateInput(Date.now()-86400000,'Asia/Shanghai').slice(0,10)+'T00:00' }
function stamp() { return r.active.value?r.now.value:Date.now() }
function togglePlayback() { if(r.playing.value)r.pause();else r.play() }
function playbackKey(event:KeyboardEvent) {
  if ((event.code!=='Space' && event.key!==' ') || event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  if (!pageActive.value || document.hidden || !r.open.value || !r.active.value || r.ended.value || r.loading.value && !r.playing.value || dateOpen.value) return
  if (!props.workspace?.context().host.getClientRects().length) return
  const target=event.target instanceof Element?event.target:undefined
  if (target?.closest('input,textarea,select,form,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="menu"],[role="listbox"],summary,[popover]:popover-open,.pine-editor,.cw-replay-menu,.cw-replay-price-editor')) return
  const modal=Array.from(document.querySelectorAll<HTMLElement>('[aria-modal="true"],[role="dialog"],[role="alertdialog"]'))
    .some(element=>element.getClientRects().length>0 && getComputedStyle(element).visibility!=='hidden')
  if (modal) return
  event.preventDefault();event.stopImmediatePropagation()
  if (!event.repeat) togglePlayback()
}
function showDate() {
  r.pause();r.picking.value=false;attach()
  date.value=r.active.value?replayDateInput(r.now.value,timeZone.value):replayDateInput(Date.now()-86400000,timeZone.value).slice(0,10)+'T00:00'
  dateOpen.value=true
}
function closeDate(){dateOpen.value=false;if(!r.active.value)void r.exit()}
async function chooseDate(value:string) {
  date.value=value
  const time=replayDateTime(value,timeZone.value)
  if(!Number.isFinite(time)){r.error.value=cw('replayPastDate');return}
  await r.start(time); if (r.active.value && !r.error.value) dateOpen.value=false
}
async function chooseRandom(){
  await r.startRandom()
  if(r.active.value&&!r.error.value){date.value=replayDateInput(r.now.value,timeZone.value);dateOpen.value=false}
}
async function retryDate(){await r.retry();if(r.active.value&&!r.error.value){date.value=replayDateInput(r.now.value,timeZone.value);dateOpen.value=false}}
async function place(side:Side,kind:OrderKind,price=t.value.account.price) {
  menu.value=undefined;orderError.value=''
  if(r.active.value){if(!r.place(side,kind,price))orderError.value=cw('replayInvalidOrder')}
  else if(!await props.paper.place(side,kind,price))orderError.value=props.paper.error.value||cw('replayInvalidOrder')
}
function remove(target:OrderTarget) { cancelDrag();orderError.value='';if (target==='entry' && t.value.account.position) t.value.account.close(stamp()); else t.value.account.cancel(target) }
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
  if(value.target==='new'){addExit(value.price);return}
  if(value.target!=='entry'&&!order.value?.exits.some(exit=>exit.target===value.target))return
  if(!t.value.account.move(value.target,value.price,stamp()))orderError.value=invalidPrice(value.target)
  else orderError.value=''
}
function dragKey(event:KeyboardEvent) { if(event.key==='Escape'){event.preventDefault();cancelDrag()} }
function addExit(price:number) {
  menu.value=undefined
  const target=t.value.account.addExit(price,stamp())
  if(!target){orderError.value=cw('replayInvalidPrice');return}
  orderError.value=''
}
function openMenu(price:number,y:number){menu.value={price,y,quantity:order.value?.quantity??0};menuError.value=''}
function submitExitAt(){
  const value=menu.value
  if(!value)return
  if(!Number.isFinite(value.quantity)||value.quantity<=0||value.quantity>(order.value?.quantity??0)){menuError.value=cw('replayInvalidSize');return}
  if(!t.value.account.addExit(t.value.roundedPrice(value.price),stamp(),value.quantity)){menuError.value=cw('replayInvalidPrice');return}
  menu.value=undefined;orderError.value=''
}
function invalidPrice(target:OrderTarget) {
  const exit=order.value?.exits.find(exit=>exit.target===target)
  if(!exit || !order.value)return cw('replayInvalidPrice')
  const above=(order.value.side===1)===(exit.kind==='tp')
  return cw(above?'replayExitAbove':'replayExitBelow',{kind:cw(exit.kind==='tp'?'replayTP':'replaySL'),price:formatNumber(t.value.account.position?t.value.account.price:order.value.price,8)})
}
function openEditor(target:OrderTarget,price:number) {
  editing.value=target;editPrice.value=String(price);editError.value=''
  const exit=order.value?.exits.find(exit=>exit.target===target)
  editQuantity.value=exit?.quantity??0
}
function applyPrice() {
  const target=editing.value,price=t.value.roundedPrice(Number(editPrice.value))
  if(!target)return
  if(target==='entry'){if(!t.value.account.move(target,price,stamp())){editError.value=invalidPrice(target);return}}
  else {
    const quantity=editPartial.value?editQuantity.value:undefined
    if(quantity!==undefined&&(!Number.isFinite(quantity)||quantity<=0||quantity>order.value!.quantity)){editError.value=cw('replayInvalidSize');return}
    if(!t.value.account.updateExit(target,price,quantity,stamp())){editError.value=invalidPrice(target);return}
  }
  orderError.value='';editing.value=undefined
}
function onMove(event:PointerEvent) {
  if (drag.value) return
  const point=renderer?.replayOrders.pointAt?.(event.clientX,event.clientY)
  const rect=overlayHost.value?.getBoundingClientRect()
  hover.value=point&&rect?{price:t.value.roundedPrice(point.price),y:event.clientY-rect.top}:undefined
}
function lineDown(event:PointerEvent) {
  if(!tradingVisible.value || (event.target as HTMLElement).closest('button,input,select,.cw-trading-controls,.cw-replay-order,.cw-replay-menu,.cw-replay-price-editor'))return
  const target=renderer?.replayOrders.hitAt?.(event.clientX,event.clientY)
  if(target){event.preventDefault();event.stopImmediatePropagation();beginDrag(event,target)}
}
function leave() { hover.value=undefined }
function captureContext(event:MouseEvent) {
  if((event.target as HTMLElement).closest('.cw-trading-controls'))return
  pendingContext=undefined;menu.value=undefined
  for(const cell of props.workspace?.cells()??[]){
    if(!cell.host.contains(event.target as Node))continue
    const view=WorkspaceRenderer.forHost(cell.host),point=view?.replayOrders.pointAt?.(event.clientX,event.clientY),rect=view?.replayOrders.host?.getBoundingClientRect()
    if(!point||!rect)continue
    props.workspace?.setActiveCell(cell.id)
    pendingContext={chart:cell.chart,symbol:fromVela(cell.symbol),price:t.value.roundedPrice(point.price),y:event.clientY-rect.top}
    break
  }
}
function openAxisMenu(){
  const rect=overlayHost.value?.getBoundingClientRect(),point=hover.value
  if(rect&&point)attached?.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:rect.left+geometry.value.right+10,clientY:rect.top+point.y,button:2}))
}
function detachMenus(){menuHost?.removeEventListener('contextmenu',captureContext,true);offMenu.forEach(off=>off());offMenu=[];menuHost=undefined;pendingContext=undefined}
function attachMenus(){
  menuHost=props.workspace?.context().host
  if(!menuHost)return
  menuHost.addEventListener('contextmenu',captureContext,true)
  const available=(ctx:WidgetContext)=>!!pendingContext&&ctx.host===menuHost&&ctx.chart===pendingContext.chart&&fromVela(ctx.symbol)===pendingContext.symbol&&!t.value.loading.value
  for(const target of ['context:body','context:price-axis'] as const){
    for(const side of [1,-1] as const)offMenu.push(registerWidgetAction({
      id:`opentrading-trading-${target}-${side}`,target,order:side===1?-20:-19,
      get label(){return cw(side===1?'replayBuyAt':'replaySellAt',{price:formatNumber(pendingContext?.price??0,8)})},
      when:ctx=>available(ctx)&&!order.value,
      run:()=>{if(pendingContext)void place(side,'limit',pendingContext.price)},
    }))
    offMenu.push(registerWidgetAction({
      id:`opentrading-trading-${target}-exit`,target,order:-18,
      get label(){return cw('paperExitAt',{price:formatNumber(pendingContext?.price??0,8),kind:cw(t.value.account.exitKind(pendingContext?.price??0)==='tp'?'replayLimitTP':'replayStopOrder')})},
      when:ctx=>available(ctx)&&!!order.value&&!!t.value.account.exitKind(pendingContext!.price),
      run:()=>{if(pendingContext)openMenu(pendingContext.price,pendingContext.y)},
    }))
  }
}
function pick(event:MouseEvent) {
  if(!r.open.value||!r.picking.value||(event.target as HTMLElement).closest('button,input,select,.cw-trading-controls'))return
  const point=renderer?.replayOrders.pointAt?.(event.clientX,event.clientY)
  if(point){event.preventDefault();event.stopImmediatePropagation();void r.start(point.time).then(()=>{if(r.active.value&&!r.error.value)dateOpen.value=false})}
}
function detach() { cancelDrag();attached?.removeEventListener('pointermove',onMove);attached?.removeEventListener('pointerleave',leave);attached?.removeEventListener('pointerdown',lineDown,true);attached?.removeEventListener('click',pick,true);renderer?.setReplayOrders({lines:[],geometry:undefined});attached=undefined;overlayHost.value=undefined }
function attach() { detach();const cell=props.workspace?.active;if(!cell)return;renderer=WorkspaceRenderer.forHost(cell.host);timeZone.value=renderer?.getConfig().timeScale.timezone??'Asia/Shanghai';attached=cell.host;overlayHost.value=renderer?.replayOrders.host;attached.addEventListener('pointermove',onMove);attached.addEventListener('pointerleave',leave);attached.addEventListener('pointerdown',lineDown,true);attached.addEventListener('click',pick,true);project() }
function project() {
  const value=order.value, preview=drag.value?.owner===value?drag.value:undefined, lines:ReplayLine[]=[]
  if(tradingVisible.value&&value){
    const price=(target:OrderTarget)=>preview?.target===target?preview.price:target==='entry'?value.price:value.exits.find(exit=>exit.target===target)?.price
    lines.push({target:'entry',price:price('entry')!,label:cw(value.side===1?'replayLong':'replayShort'),color:'#5086f5',draggable:!t.value.account.position&&('kind' in value)&&value.kind==='limit'})
    for(const exit of value.exits)lines.push({target:exit.target,price:price(exit.target)!,quantity:exit.quantity,label:cw(exit.kind==='tp'?'replayTP':'replaySL'),color:exit.kind==='tp'?'#089981':'#f23645',draggable:true})
    if(preview?.target==='new'&&preview.moved){const kind=t.value.account.exitKind(preview.price);if(kind)lines.push({target:'exit:0',price:preview.price,label:cw(kind==='tp'?'replayTP':'replaySL'),color:kind==='tp'?'#089981':'#f23645',draggable:false})}
  }
  const markers: NonNullable<ReplayLayerSource['markers']> = []
  if(tradingVisible.value){
    for(const trade of t.value.account.trades){
      markers.push({time:periodStart(trade.enteredAt-1,t.value.timeframe.value),price:trade.entry,side:trade.side,color:'#5086f5'})
      markers.push({time:periodStart(trade.exitedAt-1,t.value.timeframe.value),price:trade.exit,side:trade.side===1?-1:1,color:trade.profit>=0?'#089981':'#f23645'})
    }
    const p=t.value.account.position
    if(p)markers.push({time:periodStart(p.enteredAt-1,t.value.timeframe.value),price:p.price,side:p.side,color:'#5086f5'})
  }
  renderer?.setReplayOrders({lines,markers,geometry:value=>{const next=JSON.stringify(value);if(next!==signature){signature=next;geometry.value=value}}})
}
watchEffect(project)
watchEffect(() => {
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
  for(const id of marked)if(!next.has(id))chart.marks.remove(id)
  marked.clear();next.forEach(id=>marked.add(id))
})
watch(()=>props.workspace,value=>{offCell?.();detachMenus();attach();attachMenus();offCell=value?.on('cell:active',attach)},{flush:'post',immediate:true})
watch(r.open,value=>{if(value&&!r.active.value)showDate();else if(!value)dateOpen.value=false})
watch(r.active,()=>{menu.value=undefined;attach()})
watch(()=>props.paper.symbol.value?.id,()=>{menu.value=undefined;attach()})
watch(order,(value,previous)=>{if(value!==previous){cancelDrag();editing.value=undefined;menu.value=undefined;orderError.value=''}})
watchEffect(()=>{if(editing.value&&editing.value!=='entry'&&!order.value?.exits.some(exit=>exit.target===editing.value))editing.value=undefined})
onMounted(()=>window.addEventListener('keydown',playbackKey,true))
onActivated(()=>{pageActive.value=true})
onDeactivated(()=>{pageActive.value=false})
onBeforeUnmount(()=>{window.removeEventListener('keydown',playbackKey,true);offCell?.();detachMenus();detach()})
</script>

<style>
.cw-replay-overlay{--cw-text:var(--ui-text);--cw-panel:var(--ui-panel);--cw-border:var(--ui-border);position:absolute;inset:0;pointer-events:none;font:12px Arial,"Microsoft YaHei",sans-serif;color:var(--cw-text)}.cw-replay-overlay button,.cw-replay-overlay input{font:inherit;color:inherit;min-height:26px;border:1px solid var(--cw-border);border-radius:3px;background:var(--cw-panel);pointer-events:auto}.cw-replay-overlay button{padding:3px 6px;cursor:pointer}.cw-replay-overlay input{width:72px;padding:3px}.cw-replay-overlay button:disabled{opacity:.45;cursor:default}.cw-replay-connectors{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.cw-replay-connectors path{fill:none;stroke-width:1}.cw-replay-order{position:absolute;transform:translateY(-50%);display:flex;gap:3px;align-items:center;background:var(--cw-panel);border:1px solid;border-radius:3px;pointer-events:auto;white-space:nowrap;max-width:calc(100% - 8px)}.cw-replay-order button{border:0;background:transparent;touch-action:none;cursor:inherit}.cw-replay-handle{font-variant-numeric:tabular-nums}.cw-replay-plus{position:absolute;transform:translateY(-50%);font-size:18px!important}.cw-replay-menu{position:absolute;box-sizing:border-box;overflow:auto;display:flex;flex-direction:column;gap:4px;pointer-events:auto;background:var(--cw-panel);padding:7px;border:1px solid var(--cw-border);box-shadow:0 4px 15px #0003}.cw-replay-exit-ticket{display:grid;gap:8px;width:220px;max-width:100%;min-width:0}.cw-replay-exit-ticket label{display:grid;gap:5px}.cw-replay-exit-ticket input{width:100%;box-sizing:border-box}.cw-replay-exit-ticket p{margin:0;color:var(--ui-negative);line-height:1.5}.cw-replay-price-editor{position:absolute;overflow:auto;display:grid;gap:10px;width:280px;max-width:calc(100% - 32px);box-sizing:border-box;pointer-events:auto;background:var(--cw-panel);padding:14px;border:1px solid var(--cw-border);border-radius:5px;box-shadow:0 6px 20px #0003}.cw-replay-price-editor input{width:100%;min-width:0;box-sizing:border-box}.cw-replay-price-editor label{display:grid;gap:6px}.cw-replay-editor-actions{display:flex;gap:6px}.cw-replay-editor-actions{justify-content:flex-end}.cw-replay-price-editor p{color:var(--ui-negative);margin:0;line-height:1.5}

/* Trading forms and alert labels share the chart's stacking context. */
.cw-replay-connectors{z-index:12}
.cw-replay-order{z-index:13;overflow-x:auto;scrollbar-width:thin;user-select:none}.cw-replay-draggable{cursor:ns-resize;touch-action:none}.cw-replay-order .cw-replay-close{cursor:pointer;flex-shrink:0}
.cw-replay-plus{z-index:14}
.cw-replay-menu,.cw-replay-price-editor{z-index:20}

</style>
