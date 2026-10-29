<template>
  <div class="app-layout-switch" role="group" :aria-label="t('workspaceViews.layout')">
    <button v-for="option in options" :key="option.value" type="button"
      :aria-pressed="modelValue === option.value" @click="$emit('update:modelValue', option.value)">
      <component :is="icons[option.icon || option.value] || ViewColumnsIcon" aria-hidden="true" />
      <span>{{ option.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ViewColumnsIcon, TableCellsIcon, AdjustmentsHorizontalIcon, Squares2X2Icon, ArrowsPointingOutIcon, ChartBarIcon, CodeBracketIcon } from '@heroicons/vue/24/outline'
defineProps<{ modelValue: string; options: { value: string; label: string; icon?: string }[] }>()
defineEmits<{ 'update:modelValue': [value: string] }>()
const { t } = useI18n()
const icons: Record<string, typeof ViewColumnsIcon> = {
  table: TableCellsIcon, compact: TableCellsIcon, split: ViewColumnsIcon, filters: AdjustmentsHorizontalIcon,
  cards: Squares2X2Icon, focus: ArrowsPointingOutIcon, results: ArrowsPointingOutIcon,
  ratio: ChartBarIcon, prices: ViewColumnsIcon, editor: CodeBracketIcon, watchlist: ViewColumnsIcon,
}
</script>

<style>
.app-layout-switch { display:inline-flex; align-items:stretch; flex-wrap:wrap; gap:3px; padding:3px; border:1px solid var(--ui-border-strong); border-radius:6px; width:fit-content; max-width:100%; }
.app-layout-switch button { display:flex; align-items:center; justify-content:center; gap:7px; padding:7px 11px; min-height:34px; border-radius:3px; color:var(--ui-muted); font-size:12px; white-space:nowrap; }
.app-layout-switch button svg { width:16px; height:16px; flex-shrink:0; }
.app-layout-switch button:hover { color:var(--ui-title); background:var(--ui-hover); }
.app-layout-switch button[aria-pressed=true] { background:var(--ui-accent); color:var(--ui-panel); }
.dark .app-layout-switch button[aria-pressed=true] { color:#09231f; }
@media (max-width:767px), (pointer:coarse) { .app-layout-switch button { min-height:40px; } }
</style>
