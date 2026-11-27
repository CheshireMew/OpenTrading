<template>
  <WorkspaceReplayControls :controller="r" :paper="paper" :host="overlayHost" :geometry="geometry" :time-zone="timeZone" :date-open="dateOpen" :order-error="orderError" :visible="pageActive" @date="showDate" @toggle="togglePlayback" @place="side=>place(side,'market')" @clear-order-error="orderError=''" />
  <WorkspaceReplayDatePicker :open="dateOpen" :value="date" :time-zone="timeZone" :busy="r.loading.value" :error="r.error.value" @select="chooseDate" @random="chooseRandom" @retry="retryDate" @close="closeDate" @pick="dateOpen=false;r.picking.value=true" />
  <Teleport v-if="overlayHost" :to="overlayHost">
    <div class="cw-replay-overlay" @keydown.esc="cancelDrag();menu=undefined;editing=undefined">
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
          <span>{{ t.account.position?formatNumber(t.account.unrealized):cw('replayPending') }} {{ symbolUnit(t.symbol.value) }}</span>
          <button :aria-label="cw('replayAddExit')" @pointerdown.stop="beginDrag($event,'new')" @dblclick.stop>{{ cw('replayAddExit') }} ↕</button>
        </template>
        <template v-else>
          <span>{{ formatNumber(estimate(line.price,line.quantity)) }} {{ symbolUnit(t.symbol.value) }}</span>
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
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { WorkspaceReplay } from '@/modules/chartWorkspace/workspaceReplay'
import type { WorkspacePaper } from '@/modules/chartWorkspace/workspacePaper'
import { createWorkspaceTradingOrders } from '@/modules/chartWorkspace/workspaceTradingOrders'
import { createWorkspaceTradingInteraction } from '@/modules/chartWorkspace/workspaceTradingInteraction'
import { useWorkspaceReplayNavigation } from '@/modules/chartWorkspace/workspaceReplayNavigation'
import { cw, symbolUnit, formatNumber } from '@/modules/chartWorkspace/locale'
import WorkspaceReplayDatePicker from './WorkspaceReplayDatePicker.vue'
import WorkspaceReplayControls from './WorkspaceReplayControls.vue'
import WorkspaceQuantityField from './WorkspaceQuantityField.vue'

const props=defineProps<{controller:WorkspaceReplay;paper:WorkspacePaper;workspace?:VelaWorkspace}>()
const r=props.controller,t=computed(()=>r.active.value?r:props.paper)
let interaction:ReturnType<typeof createWorkspaceTradingInteraction>
const orders=createWorkspaceTradingOrders({target:t,replay:r,paper:()=>props.paper,beforeChange:()=>interaction?.cancelDrag()})
interaction=createWorkspaceTradingInteraction({workspace:()=>props.workspace,replay:r,target:t,orders,picked:()=>navigation.picked()})
const navigation=useWorkspaceReplayNavigation({replay:r,workspace:()=>props.workspace,timeZone:interaction.timeZone,prepare:interaction.attach})
const {pageActive,dateOpen,date,showDate,closeDate,chooseDate,chooseRandom,retryDate,togglePlayback}=navigation
const {overlayHost,timeZone,geometry,visibleLines,beginLineDrag,beginDrag,cancelDrag}=interaction
const {order,menu,menuError,editing,editPrice,editQuantity,editError,orderError,quantityStep,baseCurrency,estimate,editPartial,
  place,remove,submitExitAt,openEditor,applyPrice}=orders
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
onBeforeUnmount(()=>{interaction.dispose();orders.dispose()})
</script>

<style>
.cw-replay-overlay{--cw-text:var(--vela-fg,var(--ui-text));--cw-panel:var(--vela-surface-elev,var(--ui-panel));--cw-border:var(--vela-border,var(--ui-border));--cw-muted:var(--vela-fg-muted,var(--ui-muted));--cw-accent:var(--vela-selected-bg,var(--ui-accent));position:absolute;inset:0;pointer-events:none;font:12px Arial,"Microsoft YaHei",sans-serif;color:var(--cw-text)}.cw-replay-overlay button,.cw-replay-overlay input{font:inherit;color:inherit;min-height:26px;border:1px solid var(--cw-border);border-radius:3px;background:var(--cw-panel);pointer-events:auto}.cw-replay-overlay button{padding:3px 6px;cursor:pointer}.cw-replay-overlay input{width:72px;padding:3px}.cw-replay-overlay button:disabled{opacity:.45;cursor:default}.cw-replay-connectors{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.cw-replay-connectors path{fill:none;stroke-width:1}.cw-replay-order{position:absolute;transform:translateY(-50%);display:flex;gap:3px;align-items:center;background:var(--cw-panel);border:1px solid;border-radius:3px;pointer-events:auto;white-space:nowrap;max-width:calc(100% - 8px)}.cw-replay-order button{border:0;background:transparent;touch-action:none;cursor:inherit}.cw-replay-handle{font-variant-numeric:tabular-nums}.cw-replay-menu{position:absolute;box-sizing:border-box;overflow:auto;display:flex;flex-direction:column;gap:4px;pointer-events:auto;background:var(--cw-panel);padding:7px;border:1px solid var(--cw-border);box-shadow:0 4px 15px #0003}.cw-replay-exit-ticket{display:grid;gap:8px;width:220px;max-width:100%;min-width:0}.cw-replay-exit-ticket label{display:grid;gap:5px}.cw-replay-exit-ticket input{width:100%;box-sizing:border-box}.cw-replay-exit-ticket p{margin:0;color:var(--ui-negative);line-height:1.5}.cw-replay-price-editor{position:absolute;overflow:auto;display:grid;gap:10px;width:280px;max-width:calc(100% - 32px);box-sizing:border-box;pointer-events:auto;background:var(--cw-panel);padding:14px;border:1px solid var(--cw-border);border-radius:5px;box-shadow:0 6px 20px #0003}.cw-replay-price-editor input{width:100%;min-width:0;box-sizing:border-box}.cw-replay-price-editor label{display:grid;gap:6px}.cw-replay-editor-actions{display:flex;gap:6px}.cw-replay-editor-actions{justify-content:flex-end}.cw-replay-price-editor p{color:var(--ui-negative);margin:0;line-height:1.5}

/* Trading forms and alert labels share the chart's stacking context. */
.cw-replay-connectors{z-index:12}
.cw-replay-order{z-index:13;overflow-x:auto;scrollbar-width:thin;user-select:none}.cw-replay-draggable{cursor:ns-resize;touch-action:none}.cw-replay-order .cw-replay-close{cursor:pointer;flex-shrink:0}
.cw-replay-menu,.cw-replay-price-editor{z-index:20}

</style>
