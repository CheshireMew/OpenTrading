<template>
  <Teleport v-for="overlay in positioned" :key="overlay.cellId" :to="overlay.host">
    <div class="cw-price-alert-overlays">
      <svg class="cw-price-alert-connectors" aria-hidden="true"><path v-for="line in overlay.lines.filter(line => Math.abs(line.labelY-line.y)>1)" :key="line.id" :d="`M${overlay.right-212},${line.y} H${overlay.right-204} L${overlay.right-194},${line.labelY}`" /></svg>
      <div v-for="line in overlay.lines" :key="line.id" class="cw-price-alert-label" :class="{ selected: selectedId===line.id, dragging: draggingId===line.id }"
        :data-price-alert-id="line.id" :style="{left: `${overlay.right-4}px`, top: `${line.labelY}px`}">
        <button type="button" data-price-alert-action="move" class="cw-price-alert-value" :title="cw('alertDragHint')" :aria-label="cw('alertEditAt', {price:formatNumber(line.price,10)})" :disabled="saving" @click="editId(line.id)">
          <BellIcon aria-hidden="true" />{{ formatNumber(line.price,10) }}
        </button>
        <button type="button" data-price-alert-action="edit" :title="cw('alertEdit')" :aria-label="cw('alertEditAt', {price:formatNumber(line.price,10)})" :disabled="saving" @pointerdown.stop @mousedown.stop @click.stop="editId(line.id)"><PencilSquareIcon aria-hidden="true" /></button>
        <button type="button" data-price-alert-action="delete" :title="cw('alertDelete')" :aria-label="cw('alertDeleteAt', {price:formatNumber(line.price,10)})" :disabled="saving" @pointerdown.stop @mousedown.stop @click.stop="removeId(line.id)"><XMarkIcon aria-hidden="true" /></button>
      </div>
    </div>
  </Teleport>
  <div v-if="error && !open" class="cw-price-alert-error" role="alert">{{ error }}<button type="button" :aria-label="cw('close')" @click="error=''">×</button></div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { BellIcon, PencilSquareIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import type { createWorkspaceAlerts } from '@/modules/chartWorkspace/workspaceAlerts'
import { cw, formatNumber } from '@/modules/chartWorkspace/locale'
const props = defineProps<{controller: ReturnType<typeof createWorkspaceAlerts>}>()
const { overlays, selectedId, draggingId, saving, error, open, editId, removeId } = props.controller
const positioned = computed(() => overlays.value.map(overlay => {
  const gap = 30, edge = 15, lines = overlay.lines.map(line => ({...line, labelY:line.y})).sort((a,b) => a.y-b.y)
  for (let i=0;i<lines.length;i++) lines[i]!.labelY = Math.max(lines[i]!.y, i ? lines[i-1]!.labelY+gap : overlay.top+edge)
  for (let i=lines.length-1;i>=0;i--) lines[i]!.labelY = Math.min(lines[i]!.labelY, i===lines.length-1 ? overlay.bottom-edge : lines[i+1]!.labelY-gap)
  return {...overlay, lines}
}))
</script>
<style scoped>
.cw-price-alert-overlays{position:absolute;inset:0;pointer-events:none;overflow:hidden}
.cw-price-alert-connectors{z-index:12;position:absolute;inset:0;width:100%;height:100%;overflow:visible}.cw-price-alert-connectors path{stroke:#d99a24;stroke-width:1;fill:none}
.cw-price-alert-label{z-index:13;position:absolute;transform:translate(-100%,-50%);display:flex;align-items:center;width:190px;background:var(--vela-surface-elev,var(--ui-panel));color:#b77909;border:1px solid #d99a24;border-radius:4px;box-shadow:0 1px 4px #0002;pointer-events:auto;white-space:nowrap}
.cw-price-alert-label.selected,.cw-price-alert-label:focus-within{outline:2px solid #d99a2477;outline-offset:1px}.cw-price-alert-label.dragging{box-shadow:0 3px 12px #0004}
.cw-price-alert-label button{display:flex;align-items:center;justify-content:center;gap:5px;border:0;background:transparent;color:inherit;min-height:28px;min-width:28px;padding:3px;cursor:pointer}
.cw-price-alert-label button:hover{background:#d99a2422}.cw-price-alert-label button:focus-visible{outline:2px solid currentColor;outline-offset:-2px}.cw-price-alert-label .cw-price-alert-value{flex:1;min-width:0;padding:3px 6px;cursor:ns-resize;font-size:12px;font-variant-numeric:tabular-nums;touch-action:none}.cw-price-alert-value svg{width:13px;height:13px}.cw-price-alert-label svg{width:15px;height:15px;flex-shrink:0}.cw-price-alert-label button:disabled{opacity:.5;cursor:wait}
.cw-price-alert-error{position:relative;flex-shrink:0;min-width:0;display:flex;flex-wrap:wrap;overflow-wrap:anywhere;justify-content:space-between;gap:12px;padding:10px 12px;background:var(--ui-panel);border:1px solid var(--app-border);color:var(--app-text);font-size:13px}.cw-price-alert-error button{background:transparent;border:0;color:inherit}
</style>
