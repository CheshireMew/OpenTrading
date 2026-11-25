<template>
  <Teleport v-if="host" :to="host">
    <div class="cw-indicator-shortcuts" role="group" :aria-label="cw('indicators')">
      <button v-for="item in WORKSPACE_INDICATORS" :key="item.type" type="button"
        :class="{ active: selected.has(item.type) }" :aria-pressed="selected.has(item.type)"
        :title="cw(item.name)" :aria-haspopup="selected.has(item.type) ? 'dialog' : undefined"
        @click="toggle(item.type)" @contextmenu="openSettings($event,item.type)">{{ item.label }}</button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount } from 'vue'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import { cw } from '@/modules/chartWorkspace/locale'
import { createWorkspaceIndicators, WORKSPACE_INDICATORS } from '@/modules/chartWorkspace/workspaceIndicators'

const props = defineProps<{ workspace?: VelaWorkspace }>()
const emit = defineEmits<{ error: [unknown] }>()
const workspace = computed(() => props.workspace)
// Vela owns the range chips and clock; its flexible middle slot holds our Vue controls.
const host = computed(() => workspace.value?.context().host.querySelector<HTMLElement>('.vela-bb-spacer'))
const { selected, toggle, dispose } = createWorkspaceIndicators({ workspace, onError: error => emit('error', error) })
function openSettings(event: MouseEvent, type: string) {
  const chart = workspace.value?.active.chart
  const handle = chart?.indicators().find(handle => handle.nativeType === type && handle.visible)
  if (!chart || !handle) return
  event.preventDefault(); event.stopPropagation()
  chart.renderer.openIndicatorSettings(handle.id)
}
onBeforeUnmount(dispose)
</script>

<style>
.cw-chart .vela-bb-spacer{display:flex;align-items:center;min-width:0;overflow:hidden}
.cw-indicator-shortcuts{display:flex;align-items:center;gap:3px;min-width:0;margin-inline:12px;padding-block:3px;overflow-x:auto;scrollbar-width:thin;overscroll-behavior-x:contain}
.cw-indicator-shortcuts button{flex-shrink:0;min-height:26px;padding:3px 8px;border:1px solid transparent;border-radius:4px;background:transparent;color:var(--cw-muted);font:inherit;font-size:12px;font-weight:600;line-height:18px;cursor:pointer}
.cw-indicator-shortcuts button:hover{color:var(--cw-text);background:var(--cw-hover)}
.cw-indicator-shortcuts button.active{color:var(--cw-accent);background:color-mix(in srgb,var(--cw-accent) 12%,transparent);border-color:color-mix(in srgb,var(--cw-accent) 30%,transparent)}
.cw-indicator-shortcuts button:focus-visible{outline:2px solid var(--cw-accent);outline-offset:-2px}
.cw-indicator-help{min-height:0;overflow:auto;align-content:start;gap:10px;padding:18px 20px;line-height:1.75;font-size:13px;scrollbar-gutter:stable}
.cw-indicator-help h3{margin:8px 0 0;font-size:13px;font-weight:600;color:var(--ui-text)}
.cw-indicator-help p{margin:0;color:var(--ui-muted)}
.cw-indicator-help a{margin-top:6px;color:var(--ui-accent);text-decoration:underline}
.cw-indicator-help-swatch{display:inline-block;width:18px;height:3px;margin-right:8px;vertical-align:middle}
</style>
