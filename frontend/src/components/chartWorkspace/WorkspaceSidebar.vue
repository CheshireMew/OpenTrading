<template>
  <button v-if="compact && visible" class="cw-sidebar-backdrop" type="button" :aria-label="cw('close')" @click="emit('close')" />
  <aside v-show="visible" ref="sidebarHost" class="cw-sidebar" :class="{ 'cw-sidebar-drawer': compact }" :style="{ width: width + 'px' }"
    tabindex="-1" :role="compact ? 'dialog' : undefined" :aria-modal="compact ? true : undefined" :aria-label="cw('sidebar')">
    <header class="cw-sidebar-header">
      <nav role="tablist" :aria-label="cw('sidebar')" @keydown="tabKey">
        <button v-for="item in tabs" :id="tabId(item.id)" :key="item.id" type="button" role="tab" :aria-selected="tab === item.id" :aria-controls="panelId(item.id)" :tabindex="tab === item.id ? 0 : -1" @click="emit('update:tab', item.id)">{{ item.label }}</button>
      </nav>
      <button type="button" class="cw-sidebar-close" :aria-label="cw('close')" :title="cw('close')" @click="emit('close')"><IconX :size="18" aria-hidden="true" /></button>
    </header>
    <div v-show="tab === 'watchlist'" :id="panelId('watchlist')" class="cw-sidebar-pane" role="tabpanel" :aria-labelledby="tabId('watchlist')"><slot /></div>
    <div v-show="tab === 'objects'" :id="panelId('objects')" ref="objectsHost" class="cw-sidebar-pane cw-sidebar-native" role="tabpanel" :aria-labelledby="tabId('objects')" tabindex="0" />
    <div v-show="tab === 'dataWindow'" :id="panelId('dataWindow')" ref="dataHost" class="cw-sidebar-pane cw-sidebar-native" role="tabpanel" :aria-labelledby="tabId('dataWindow')" tabindex="0" />
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { DataWindow, ObjectTree } from '@luxalgo/vela/widget'
import { ensureUIHost } from '@luxalgo/vela/ui'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import IconX from '@tabler/icons-vue/icons/IconX'
import { useModalDialog } from '@/composables/useModalDialog'
import type { ChartSymbol } from '@/modules/chartWorkspace/api'
import { chartTheme } from '@/modules/chartWorkspace/chartPresentation'
import { localizeChart } from '@/modules/chartWorkspace/localize'
import { cw } from '@/modules/chartWorkspace/locale'
import { catalogSymbolIcon } from '@/modules/chartWorkspace/symbolIcons'
import type { WorkspacePanelTab } from '@/modules/chartWorkspace/workspacePanels'

const props = defineProps<{
  workspace?: VelaWorkspace; symbols: ChartSymbol[]; theme: 'light' | 'dark'
  visible: boolean; compact: boolean; width: number; tab: WorkspacePanelTab
}>()
const emit = defineEmits<{ close: []; 'update:tab': [tab: WorkspacePanelTab] }>()
const { dialogRef: sidebarHost } = useModalDialog(computed(() => props.compact && props.visible), () => emit('close'))
const objectsHost = ref<HTMLElement>(), dataHost = ref<HTMLElement>(), id = useId()
const tabId = (tab: WorkspacePanelTab) => `${id}-tab-${tab}`
const panelId = (tab: WorkspacePanelTab) => `${id}-panel-${tab}`
const tabs = computed(() => [
  { id: 'watchlist' as const, label: cw('watchlist') }, { id: 'objects' as const, label: cw('objectsTab') },
  { id: 'dataWindow' as const, label: cw('dataTab') },
])
function tabKey(event: KeyboardEvent) {
  const current = tabs.value.findIndex(item => item.id === props.tab)
  const index = event.key === 'ArrowRight' ? (current + 1) % 3 : event.key === 'ArrowLeft' ? (current + 2) % 3 : event.key === 'Home' ? 0 : event.key === 'End' ? 2 : -1
  if (index < 0) return
  event.preventDefault()
  emit('update:tab', tabs.value[index]!.id)
  ;(event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]')[index]?.focus()
}
watch([sidebarHost, () => props.theme], ([host]) => { if (host) ensureUIHost(host, chartTheme(props.theme)) }, { flush: 'post' })
watch([() => props.workspace, objectsHost, dataHost], ([workspace, objects, data], _old, cleanup) => {
  if (!workspace || !objects || !data || !sidebarHost.value) return
  const tree = new ObjectTree(objects, symbol => catalogSymbolIcon(props.symbols, symbol)), readout = new DataWindow(data)
  const stopLocale = localizeChart(sidebarHost.value, () => props.symbols)
  let boundChart: typeof workspace.active.chart | undefined, boundSymbol: string | undefined
  let offMarket: (() => void) | undefined
  const bind = () => {
    const cell = workspace.active
    const symbol = cell.chart.market.symbol ?? cell.symbol
    if (boundChart === cell.chart && boundSymbol === symbol) return
    if (boundChart !== cell.chart) { offMarket?.(); offMarket = cell.chart.on('market:changed', bind) }
    tree.setSymbol(symbol); tree.onChart(cell.chart); readout.onChart(cell.chart)
    boundChart = cell.chart; boundSymbol = symbol
  }
  const show = () => { tree.toggle(props.visible && props.tab === 'objects'); readout.toggle(props.visible && props.tab === 'dataWindow') }
  bind(); show()
  const off = [workspace.on('cell:active', bind), workspace.on('layout:changed', bind), workspace.on('state:changed', bind)]
  const stopVisibility = watch([() => props.visible, () => props.tab], show, { flush: 'post' })
  cleanup(() => { stopVisibility(); offMarket?.(); off.forEach(dispose => dispose()); stopLocale(); tree.destroy(); readout.destroy() })
}, { flush: 'post' })
</script>

<style>
.cw-sidebar { display: flex; flex: 0 0 auto; flex-direction: column; min-width: 320px; max-width: 520px; min-height: 0; background: var(--ui-panel); color: var(--ui-text); outline: none; }
.cw-sidebar-header { display: flex; align-items: center; gap: 6px; min-height: 42px; padding: 0 6px 0 12px; border-bottom: 1px solid var(--ui-border); }
.cw-sidebar-header nav { display: flex; flex: 1; align-self: stretch; gap: 14px; }
.cw-sidebar-header button { border: 0; background: transparent; color: var(--ui-muted); font: inherit; cursor: pointer; }
.cw-sidebar-header [role='tab'] { position: relative; padding: 9px 2px; white-space: nowrap; }
.cw-sidebar-header [role='tab'][aria-selected='true'] { color: var(--ui-title); font-weight: 600; }
.cw-sidebar-header [role='tab'][aria-selected='true']::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 2px; background: currentColor; }
.cw-sidebar-header button:focus-visible, .cw-sidebar-pane:focus-visible { outline: 2px solid var(--ui-blue, #5086f5); outline-offset: -2px; }
.cw-sidebar-close { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 4px; }
.cw-sidebar-header button:hover { color: var(--ui-title); background: var(--ui-hover); }
.cw-sidebar-pane { display: flex; flex: 1; min-width: 0; min-height: 0; overflow: hidden; }
.cw-sidebar-native > .vela-panel { flex: 1; width: 100%; min-width: 0; max-width: none; min-height: 0; border: 0; }
.cw-sidebar-native > .vela-panel > .vela-panel-header { display: none; }
.cw-sidebar-native .vela-panel-body { min-height: 0; padding: 12px; }
.cw-sidebar-backdrop { position: absolute; inset: 0; z-index: 29; border: 0; border-radius: 0; background: #0005; }
.cw-sidebar-drawer { position: absolute; inset-block: 0; right: 0; z-index: 30; min-width: 0; max-width: calc(100% - 32px); box-shadow: -8px 0 24px #0003; }
@media(pointer:coarse) { .cw-sidebar-header { min-height: 48px; }.cw-sidebar-close { width: 44px; height: 44px; } }
</style>
