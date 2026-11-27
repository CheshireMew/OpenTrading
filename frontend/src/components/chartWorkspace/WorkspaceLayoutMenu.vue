<template>
  <WorkspacePopover class="cw-layout" :label="cw('layout')">
    <template #trigger><span>{{ selectedLabel }}</span><IconChevronDown :size="14" aria-hidden="true" /></template>
    <div class="cw-layout-menu">
      <fieldset class="cw-layout-choices">
        <legend class="sr-only">{{ cw('layout') }}</legend>
        <label v-for="choice in choices" :key="choice.value" :class="{ selected: layout === choice.value }">
          <input class="sr-only" type="radio" :name="groupId" :value="choice.value" :checked="layout === choice.value" @change="emit('layout', choice.value)" />
          <span class="cw-layout-preview" :data-layout="choice.value" aria-hidden="true"><i v-for="cell in choice.cells" :key="cell" /></span>
          <span>{{ choice.label }}</span>
        </label>
      </fieldset>
      <fieldset v-if="layout !== '1'" class="cw-layout-sync">
        <legend>{{ cw('sync') }}</legend>
        <label v-for="link in links" :key="link.key"><input type="checkbox" :data-sync="link.key" :checked="sync[link.key]" @change="emit('sync', link.key, ($event.target as HTMLInputElement).checked)" />{{ link.label }}</label>
      </fieldset>
    </div>
  </WorkspacePopover>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'
import IconChevronDown from '@tabler/icons-vue/icons/IconChevronDown'
import { cw } from '@/modules/chartWorkspace/locale'
import WorkspacePopover from './WorkspacePopover.vue'

const props = defineProps<{ layout: string; sync: Record<string, boolean> }>()
const emit = defineEmits<{ layout: [value: string]; sync: [key: string, on: boolean] }>()
const groupId = useId()
const choices = computed(() => [
  { value: '1', label: cw('single'), cells: 1 }, { value: '2h', label: cw('horizontal'), cells: 2 },
  { value: '2v', label: cw('vertical'), cells: 2 }, { value: '4', label: cw('four'), cells: 4 },
])
const selectedLabel = computed(() => choices.value.find(choice => choice.value === props.layout)?.label ?? cw('layout'))
const links = computed(() => [
  { key: 'crosshair', label: cw('crosshair') }, { key: 'viewport', label: cw('timeRange') },
  { key: 'symbol', label: cw('symbol') }, { key: 'timeframe', label: cw('timeframe') },
])
</script>

<style scoped>
.cw-layout { flex: 0 0 auto; }
.cw-layout :deep(summary) { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 30px; padding: 4px 9px; border: 1px solid var(--cw-border); border-radius: 4px; list-style: none; cursor: pointer; }
.cw-layout :deep(summary::-webkit-details-marker) { display: none; }
.cw-layout :deep(summary:hover) { background: var(--cw-hover); }
.cw-layout-menu { width: 236px; padding: 10px; border: 1px solid var(--cw-border); border-radius: 6px; background: var(--cw-panel); color: var(--cw-text); box-shadow: 0 8px 24px #0003; }
.cw-layout-menu fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
.cw-layout-choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.cw-layout-choices label { display: flex; flex-direction: column; align-items: center; gap: 7px; padding: 10px 6px; border: 1px solid var(--cw-border); border-radius: 4px; cursor: pointer; }
.cw-layout-choices label:hover, .cw-layout-choices label.selected { background: var(--cw-hover); }
.cw-layout-choices label.selected { border-color: var(--cw-accent); }
.cw-layout-choices label:focus-within { outline: 2px solid var(--cw-accent); outline-offset: 1px; }
.cw-layout-preview { display: grid; width: 32px; height: 24px; gap: 3px; }
.cw-layout-preview[data-layout='2h'], .cw-layout-preview[data-layout='4'] { grid-template-columns: repeat(2, 1fr); }
.cw-layout-preview[data-layout='2v'], .cw-layout-preview[data-layout='4'] { grid-template-rows: repeat(2, 1fr); }
.cw-layout-preview i { border: 1px solid currentColor; border-radius: 1px; }
.cw-layout-menu .cw-layout-sync { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 3px 8px; margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--cw-border); }
.cw-layout-sync legend { padding: 0 6px 0 0; color: var(--cw-muted); font-size: 12px; }
.cw-layout-sync label { display: flex; align-items: center; gap: 7px; min-height: 32px; white-space: nowrap; cursor: pointer; }
.cw-layout-sync input { width: 15px; height: 15px; margin: 0; accent-color: var(--ui-blue, #5086f5); }
@media(pointer:coarse) { .cw-layout :deep(summary), .cw-layout-sync label { min-height: 44px; } }
</style>
