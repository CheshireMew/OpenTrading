<template>
  <Teleport v-if="host" :to="host">
    <section v-show="visible" ref="panel" class="cw-trading-controls cw-replay-floating" :class="{'cw-replay-moving':!!moving}" :style="floatingStyle" :aria-label="cw(r.open.value?'replay':'paperTrading')" @pointerdown.stop @pointermove.stop @click.stop @dblclick.stop @contextmenu.stop @wheel.stop @keydown.esc="endMove(true)">
      <div v-if="r.open.value" class="cw-replay-bar">
        <button type="button" class="cw-replay-grip" :aria-label="cw('replayMovePanel')" :title="cw('replayMovePanel')" @pointerdown="startMove" @keydown="moveKey"><IconGripVertical aria-hidden="true" /></button>
        <button type="button" :aria-label="cw('replayDate')" :title="cw('replayDate')" :aria-expanded="dateOpen" @click="emit('date')"><IconCalendar aria-hidden="true" /></button>
        <button type="button" :class="{active:r.picking.value}" :aria-label="cw('replayPick')" :title="cw('replayPick')" :aria-pressed="r.picking.value" @click="r.picking.value=!r.picking.value"><IconCrosshair aria-hidden="true" /></button>
        <span class="cw-replay-divider" aria-hidden="true" />
        <button type="button" class="cw-replay-play" :disabled="!r.active.value || r.loading.value && !r.playing.value || r.ended.value" :aria-label="cw(r.playing.value?'replayPause':'replayPlay')" aria-keyshortcuts="Space" :title="cw('replayPlaybackShortcut')" @click="emit('toggle')"><component :is="r.playing.value?IconPlayerPause:IconPlayerPlay" aria-hidden="true" /></button>
        <button type="button" :disabled="!r.active.value || r.loading.value || r.processing.value || r.ended.value" :aria-label="cw('replayNext',{period:r.sourceStep.value})" :title="cw('replayNext',{period:r.sourceStep.value})" @click="r.step()"><IconPlayerSkipForward aria-hidden="true" /></button>
        <select :value="r.speed.value" :aria-label="cw('replaySpeed')" :title="cw('replaySpeed')" @change="r.setSpeed(Number(($event.target as HTMLSelectElement).value))"><option v-for="rate in [1,2,5,10,30,60,120]" :key="rate" :value="rate">{{ rate }}×</option></select>
        <time v-if="r.active.value" :datetime="new Date(r.now.value).toISOString()" :title="timeZone">{{ formatDate(r.now.value,false,timeZone) }}</time>
        <span v-if="r.loading.value" class="cw-replay-status" role="status" :aria-label="cw('replayPreparing')" :title="cw('replayPreparing')"><IconLoader2 aria-hidden="true" /></span>
        <span v-else-if="r.ended.value" class="cw-replay-status" role="status">{{ cw('replayEnd') }}</span>
        <span v-else-if="r.active.value" class="cw-replay-granularity" :title="cw('replayResolution',{period:r.sourceStep.value,speed:r.speed.value})">{{ r.sourceStep.value }}</span>
        <button type="button" class="cw-replay-exit" :aria-label="cw('replayExit')" :title="cw('replayExit')" @click="r.exit()"><IconX aria-hidden="true" /></button>
      </div>
      <div class="cw-replay-trading-row">
        <button v-if="!r.open.value" type="button" class="cw-replay-grip" :aria-label="cw('replayMovePanel')" :title="cw('replayMovePanel')" @pointerdown="startMove" @keydown="moveKey"><IconGripVertical aria-hidden="true" /></button>
        <div class="cw-replay-quick">
          <button type="button" class="cw-replay-sell" :disabled="!t.symbol.value || t.hasOrder.value || t.loading.value" :aria-label="cw('replayShort')" :title="cw('replayShort')" @click="emit('place',-1)"><IconArrowDownRight aria-hidden="true" />{{ cw('replaySell') }}</button>
          <WorkspaceQuantityField v-model="t.amount.value" :label="cw('replayAmount')" :unit="t.symbol.value?.currency" compact />
          <button type="button" class="cw-replay-buy" :disabled="!t.symbol.value || t.hasOrder.value || t.loading.value" :aria-label="cw('replayLong')" :title="cw('replayLong')" @click="emit('place',1)"><IconArrowUpRight aria-hidden="true" />{{ cw('replayBuy') }}</button>
        </div>
        <div v-if="tradingVisible" class="cw-replay-results">
          <span v-if="!r.open.value" class="cw-paper-label">{{ cw('paperTrading') }}</span>
          <span class="cw-replay-metric" :class="profitClass(t.account.realized)" :aria-label="cw('replayRealized')+' '+formatNumber(t.account.realized)+' '+t.symbol.value?.currency" :title="cw('replayRealized')"><IconWallet aria-hidden="true" /><b>{{ formatNumber(t.account.realized) }}</b><small>{{ t.symbol.value?.currency }}</small></span>
          <span v-if="t.account.position" class="cw-replay-metric" :class="profitClass(t.account.unrealized)" :aria-label="cw('replayUnrealized')+' '+formatNumber(t.account.unrealized)+' '+t.symbol.value?.currency" :title="cw('replayUnrealized')"><IconChartLine aria-hidden="true" /><b>{{ formatNumber(t.account.unrealized) }}</b></span>
          <button v-if="t.account.trades.length" type="button" class="cw-replay-trades-toggle" :aria-expanded="tradesOpen" :aria-label="cw('replayTrades',{count:t.account.trades.length})" :title="cw('replayTrades',{count:t.account.trades.length})" @click="tradesOpen=!tradesOpen"><IconListDetails aria-hidden="true" /><span>{{ t.account.trades.length }}</span></button>
        </div>
      </div>
      <div v-if="tradesOpen && t.account.trades.length" class="cw-replay-trades"><table><thead><tr><th>{{ cw('replaySide') }}</th><th>{{ cw('replayQuantity') }}</th><th>{{ cw('replayEntry') }}</th><th>{{ cw('replayClose') }}</th><th>{{ cw('replayRealized') }}</th><th>{{ cw('replayTime') }}</th></tr></thead><tbody><tr v-for="(trade,i) in t.account.trades" :key="i"><td>{{ cw(trade.side===1?'replayLong':'replayShort') }}</td><td>{{ formatQuantity(trade.quantity) }}</td><td>{{ formatNumber(trade.entry,8) }}</td><td>{{ formatNumber(trade.exit,8) }} · {{ cw(trade.reason==='tp'?'replayTP':trade.reason==='sl'?'replaySL':'replayClose') }}</td><td>{{ formatNumber(trade.profit) }}</td><td>{{ formatDate(trade.exitedAt,false,timeZone) }}</td></tr></tbody></table></div>
      <div v-if="orderError" class="cw-replay-order-error" role="alert"><span>{{ orderError }}</span><button type="button" :aria-label="cw('close')" @click="emit('clearOrderError')"><IconX aria-hidden="true" /></button></div>
      <div v-if="r.open.value && !dateOpen && r.error.value" class="cw-replay-error" role="alert"><span>{{ r.error.value }}</span><button type="button" :disabled="r.loading.value" @click="r.retry()">{{ cw('replayRetry') }}</button></div>
      <div v-if="r.open.value && r.picking.value" class="cw-replay-hint" role="status">{{ cw('replayPickHint') }}</div>
    </section>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import IconCalendar from '@tabler/icons-vue/icons/IconCalendar'
import IconCrosshair from '@tabler/icons-vue/icons/IconCrosshair'
import IconPlayerPlay from '@tabler/icons-vue/icons/IconPlayerPlay'
import IconPlayerPause from '@tabler/icons-vue/icons/IconPlayerPause'
import IconPlayerSkipForward from '@tabler/icons-vue/icons/IconPlayerSkipForward'
import IconGripVertical from '@tabler/icons-vue/icons/IconGripVertical'
import IconX from '@tabler/icons-vue/icons/IconX'
import IconWallet from '@tabler/icons-vue/icons/IconWallet'
import IconChartLine from '@tabler/icons-vue/icons/IconChartLine'
import IconListDetails from '@tabler/icons-vue/icons/IconListDetails'
import IconArrowDownRight from '@tabler/icons-vue/icons/IconArrowDownRight'
import IconArrowUpRight from '@tabler/icons-vue/icons/IconArrowUpRight'
import IconLoader2 from '@tabler/icons-vue/icons/IconLoader2'
import type { WorkspaceReplay } from '@/modules/chartWorkspace/workspaceReplay'
import type { WorkspacePaper } from '@/modules/chartWorkspace/workspacePaper'
import type { ReplayGeometry } from '@/modules/chartWorkspace/replayOrderLayer'
import type { Side } from '@/modules/chartWorkspace/replayModel'
import { cw, formatDate, formatNumber } from '@/modules/chartWorkspace/locale'
import { formatQuantity } from '@/modules/chartWorkspace/replayQuantity'
import WorkspaceQuantityField from './WorkspaceQuantityField.vue'

const props=defineProps<{controller:WorkspaceReplay;paper:WorkspacePaper;host?:HTMLElement;geometry:ReplayGeometry;timeZone:string;dateOpen:boolean;orderError:string;visible:boolean}>()
const emit=defineEmits<{date:[];toggle:[];place:[side:Side];clearOrderError:[]}>()
const r=props.controller,t=computed(()=>r.active.value?r:props.paper)
const tradingVisible=computed(()=>r.active.value || props.paper.active.value)
const tradesOpen=ref(false),panel=ref<HTMLElement>()
const size=ref({width:560,height:84}),hostSize=ref({width:0,height:0,gutter:40})
const position=ref<{x:number;y:number}>()
const moving=ref<{pointer:number;x:number;y:number;left:number;top:number;previous?:{x:number;y:number}}>()
const profitClass=(value:number)=>value>0?'cw-profit':value<0?'cw-loss':''
const limits=computed(()=>{
  const host=hostSize.value,bounds=props.geometry
  const left=host.gutter+8,right=Math.min(bounds.right || host.width,host.width)-8
  const top=Math.max(0,bounds.top)+8,bottom=Math.min(bounds.bottom || host.height,host.height)-8
  return {left,top,width:Math.max(1,right-left),height:Math.max(1,bottom-top)}
})
function clamp(x:number,y:number){
  const bounds=limits.value
  return {x:Math.max(bounds.left,Math.min(x,bounds.left+bounds.width-Math.min(size.value.width,bounds.width))),
    y:Math.max(bounds.top,Math.min(y,bounds.top+bounds.height-Math.min(size.value.height,bounds.height)))}
}
const currentPosition=computed(()=>{
  const bounds=limits.value
  return clamp(position.value?.x ?? bounds.left+(bounds.width-size.value.width)/2,
    position.value?.y ?? bounds.top+32)
})
const floatingStyle=computed(()=>({left:currentPosition.value.x+'px',top:currentPosition.value.y+'px',maxWidth:Math.min(560,limits.value.width)+'px',maxHeight:limits.value.height+'px'}))
watch([()=>props.host,panel],([host,element],_old,cleanup)=>{
  const measure=()=>{
    if(host)hostSize.value={width:host.clientWidth,height:host.clientHeight,gutter:Number.parseFloat(getComputedStyle(host).getPropertyValue('--vela-toolbar-gutter')) || 40}
    if(element)size.value={width:element.offsetWidth,height:element.offsetHeight}
  }
  const observer=new ResizeObserver(measure)
  if(host)observer.observe(host)
  if(element)observer.observe(element)
  measure();cleanup(()=>observer.disconnect())
},{flush:'post'})
function move(event:PointerEvent){
  const drag=moving.value
  if(!drag || event.pointerId!==drag.pointer)return
  event.preventDefault()
  position.value=clamp(drag.left+event.clientX-drag.x,drag.top+event.clientY-drag.y)
}
function startMove(event:PointerEvent){
  if(event.button!==0 || !props.host)return
  event.preventDefault();endMove()
  moving.value={pointer:event.pointerId,x:event.clientX,y:event.clientY,left:currentPosition.value.x,top:currentPosition.value.y,previous:position.value}
  window.addEventListener('pointermove',move,{passive:false,capture:true});window.addEventListener('pointerup',finishMove);window.addEventListener('pointercancel',cancelMove);window.addEventListener('keydown',dragKey,true)
}
function endMove(cancel=false){
  if(cancel && moving.value)position.value=moving.value.previous
  moving.value=undefined
  window.removeEventListener('pointermove',move,true);window.removeEventListener('pointerup',finishMove);window.removeEventListener('pointercancel',cancelMove);window.removeEventListener('keydown',dragKey,true)
}
function finishMove(event:PointerEvent){if(event.pointerId===moving.value?.pointer)endMove()}
function cancelMove(){endMove(true)}
function dragKey(event:KeyboardEvent){if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();endMove(true)}}
function moveKey(event:KeyboardEvent){
  const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key]
  if(!delta || !props.host)return
  event.preventDefault();event.stopPropagation()
  const distance=event.shiftKey?50:10
  position.value=clamp(currentPosition.value.x+delta[0]!*distance,currentPosition.value.y+delta[1]!*distance)
}
watch(r.open,()=>{endMove();tradesOpen.value=false})
watch(()=>props.host,()=>endMove())
watch(()=>props.visible,value=>{if(!value)endMove()})
onDeactivated(()=>endMove())
onBeforeUnmount(()=>endMove())
</script>

<style scoped>
.cw-trading-controls{--cw-text:var(--ui-text);--cw-panel:var(--ui-panel);--cw-border:var(--ui-border);--cw-muted:var(--ui-muted);--cw-accent:var(--ui-accent);position:relative;flex-shrink:0;min-width:0;color:var(--cw-text);background:var(--cw-panel);border-top:1px solid var(--cw-border);font:12px/1.35 Arial,"Microsoft YaHei",sans-serif}
.cw-trading-controls button,.cw-trading-controls select{font:inherit;color:inherit;background:transparent;border:1px solid var(--cw-border);border-radius:5px;min-height:28px;box-sizing:border-box;cursor:pointer}
.cw-trading-controls button{display:inline-flex;align-items:center;justify-content:center;gap:4px;padding:3px 7px;white-space:nowrap}.cw-trading-controls button:hover{background:var(--ui-hover)}.cw-trading-controls button:disabled{opacity:.4;cursor:default}.cw-trading-controls button:focus-visible,.cw-trading-controls select:focus-visible{outline:2px solid var(--cw-accent);outline-offset:1px}
.cw-trading-controls svg{width:16px;height:16px;stroke-width:1.7;flex-shrink:0}.cw-replay-bar{display:flex;flex-wrap:wrap;align-items:center;gap:4px;padding:5px 7px;border-bottom:1px solid var(--cw-border)}.cw-replay-bar button{width:28px;flex-shrink:0;border-color:transparent;padding:4px}.cw-replay-bar .active{background:var(--ui-hover);color:var(--cw-accent)}.cw-replay-bar .cw-replay-play{background:var(--cw-accent);color:var(--ui-onAccent)}.cw-replay-bar select{width:59px;padding:3px;background:var(--ui-toolbar)}.cw-replay-bar time{font-size:11px;font-variant-numeric:tabular-nums;white-space:nowrap;margin-inline:5px}.cw-replay-bar .cw-replay-exit{margin-left:auto}.cw-replay-divider{height:18px;border-left:1px solid var(--cw-border);margin-inline:2px}.cw-replay-granularity{font-size:10px;color:var(--cw-muted)}.cw-replay-status{display:inline-flex;align-items:center;color:var(--cw-muted);font-size:11px}.cw-replay-status svg{animation:cw-replay-loading 1s linear infinite}.cw-replay-bar .cw-replay-grip{width:19px;padding:0;cursor:grab;touch-action:none;color:var(--cw-muted)}.cw-replay-moving .cw-replay-grip{cursor:grabbing}
.cw-replay-trading-row{display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:5px 8px}.cw-replay-quick{display:flex;align-items:center;flex-wrap:wrap;gap:5px;min-width:0}.cw-replay-quick button{min-width:55px}.cw-replay-quick .cw-replay-sell{color:var(--ui-negative);border-color:color-mix(in srgb,var(--ui-negative) 45%,transparent)}.cw-replay-quick .cw-replay-buy{color:var(--ui-positive);border-color:color-mix(in srgb,var(--ui-positive) 45%,transparent)}.cw-replay-quick :deep(.cw-quantity-field){width:210px;max-width:100%}.cw-replay-quick :deep(label){display:flex;align-items:center;gap:7px}.cw-replay-quick :deep(.cw-quantity-label){white-space:nowrap}.cw-replay-quick :deep(input){width:130px;flex:1;min-width:0;min-height:28px;box-sizing:border-box;border:1px solid var(--cw-border);border-radius:5px;background:var(--ui-toolbar);color:inherit;font:inherit;padding:4px 7px}
.cw-replay-results{display:flex;align-items:center;gap:10px;min-width:0;flex-wrap:wrap}.cw-replay-results:not(:first-child){border-left:1px solid var(--cw-border);padding-left:10px}.cw-paper-label{color:var(--cw-muted);font-size:11px}.cw-replay-metric{display:inline-flex;align-items:center;gap:4px;white-space:nowrap;font-variant-numeric:tabular-nums}.cw-replay-metric svg{color:var(--cw-muted);width:14px;height:14px}.cw-replay-metric b{font-weight:500}.cw-replay-metric small{font-size:10px;color:var(--cw-muted)}.cw-profit{color:var(--ui-positive)}.cw-loss{color:var(--ui-negative)}.cw-replay-results .cw-replay-trades-toggle{border-color:transparent;padding-inline:4px;min-width:28px}.cw-replay-trades-toggle span{font-size:10px}.cw-replay-trades{overflow:auto;max-height:180px;border-top:1px solid var(--cw-border)}.cw-replay-trades table{width:100%;border-collapse:collapse;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.cw-replay-trades th,.cw-replay-trades td{padding:5px 7px;border-bottom:1px solid var(--cw-border)}.cw-replay-trades th{font-weight:500;color:var(--cw-muted)}
.cw-replay-order-error,.cw-replay-error,.cw-replay-hint{display:flex;align-items:center;gap:7px;padding:5px 8px;border-top:1px solid var(--cw-border);overflow-wrap:anywhere}.cw-replay-order-error,.cw-replay-error{color:var(--ui-negative)}.cw-replay-hint{color:var(--cw-accent)}.cw-replay-order-error span,.cw-replay-error span{flex:1;min-width:0}.cw-replay-order-error button{border:0;padding:2px;min-width:24px}
.cw-replay-floating{position:absolute;z-index:18;width:max-content;box-sizing:border-box;overflow:auto;border:1px solid var(--cw-border);border-radius:9px;box-shadow:0 5px 24px #0003;pointer-events:auto;max-width:560px;scrollbar-width:thin}.cw-replay-floating .cw-replay-trading-row{column-gap:8px}.cw-replay-floating .cw-replay-quick :deep(.cw-quantity-field){width:132px}.cw-replay-floating .cw-replay-quick :deep(input){width:100%}.cw-replay-floating .cw-replay-quick{flex-wrap:nowrap}.cw-replay-floating .cw-replay-results{gap:8px}.cw-replay-moving{user-select:none}
.cw-trading-controls .cw-replay-grip{width:19px;min-width:19px;flex-shrink:0;padding:0;border-color:transparent;cursor:grab;touch-action:none;color:var(--cw-muted)}
.cw-replay-moving .cw-replay-grip{cursor:grabbing}
@keyframes cw-replay-loading{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.cw-replay-status svg{animation:none}}
</style>
