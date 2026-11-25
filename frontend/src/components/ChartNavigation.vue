<template>
  <div class="chart-navigation" role="group" :aria-label="t('chartControls.navigation')">
    <select :aria-label="t('chartControls.range')" :value="range" :disabled="!enabled" @change="controller.selectRange(($event.target as HTMLSelectElement).value)">
      <option v-if="range==='custom'" value="custom">{{ t('chartControls.custom') }}</option><option value="30">{{ t('chartControls.month') }}</option><option value="90">{{ t('chartControls.quarter') }}</option><option value="365">{{ t('chartControls.year') }}</option><option value="all">{{ t('chartControls.all') }}</option>
    </select>
    <button type="button" :disabled="!enabled" :title="t('chartControls.zoomIn')" :aria-label="t('chartControls.zoomIn')" @click="controller.zoom(1)"><PlusIcon /></button>
    <button type="button" :disabled="!enabled" :title="t('chartControls.zoomOut')" :aria-label="t('chartControls.zoomOut')" @click="controller.zoom(-1)"><MinusIcon /></button>
    <button v-if="controller.toggleSelect" type="button" :disabled="!enabled" :aria-pressed="selecting" :title="t('chartControls.dragZoom')" @click="controller.toggleSelect()"><MagnifyingGlassPlusIcon />{{ t('chartControls.select') }}</button>
    <button type="button" :disabled="!enabled" :title="t('chartControls.resetHint')" @click="controller.reset()"><ArrowPathIcon />{{ t('chartControls.reset') }}</button>
  </div>
</template>
<script setup lang="ts">
import {useI18n} from 'vue-i18n'
import {PlusIcon,MinusIcon,MagnifyingGlassPlusIcon,ArrowPathIcon} from '@heroicons/vue/24/outline'
import type {Ref} from 'vue'
const props=defineProps<{controller:{range:Ref<string>;selecting:Ref<boolean>;enabled:Readonly<Ref<boolean>>;zoom:(direction:number)=>void;reset:()=>void;selectRange:(range:string)=>void;toggleSelect?:()=>void}}>()
const {range,selecting,enabled}=props.controller
const {t}=useI18n()
</script>
<style scoped>
.chart-navigation{display:flex;justify-content:flex-end;align-items:center;flex-wrap:wrap;gap:4px;min-height:36px;margin-bottom:4px;color:var(--ui-muted);font-size:12px}
.chart-navigation :is(button,select){display:inline-flex;align-items:center;justify-content:center;gap:4px;min-height:32px;padding:4px 8px;border:1px solid var(--ui-border);border-radius:4px;background:var(--ui-panel);color:inherit;font:inherit}
.chart-navigation svg{width:16px;height:16px}.chart-navigation button:hover,.chart-navigation [aria-pressed=true]{background:var(--ui-hover);color:var(--ui-text)}.chart-navigation button:focus-visible,.chart-navigation select:focus-visible{outline:2px solid var(--ui-accent);outline-offset:1px}.chart-navigation button:disabled{opacity:.4;cursor:default}@media(pointer:coarse){.chart-navigation :is(button,select){min-height:44px;min-width:44px}}
</style>
