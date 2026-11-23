<template>
  <Teleport to="body">
    <div v-if="open" class="workspace-dialog-backdrop" @click.self="open = false">
      <section ref="dialogRef" tabindex="-1" class="workspace-dialog symbol-picker" role="dialog" aria-modal="true" :aria-label="cw(title)">
        <header><strong>{{ cw(title) }}</strong><button class="app-icon-button" type="button" :aria-label="cw('close')" @click="open = false"><XMarkIcon class="h-4 w-4" /></button></header>
        <input ref="searchInput" v-model="query" class="app-control" type="search" :aria-label="cw('searchSymbolHint')" :placeholder="cw('searchSymbolHint')" />
        <div class="symbol-filters">
          <button v-for="filter in filters" :key="filter.value" type="button" class="app-segment-button" :class="{ 'is-active': market === filter.value }" :aria-pressed="market === filter.value" @click="market = filter.value">{{ cw(filter.label) }}</button>
        </div>
        <div class="symbol-results">
          <button v-for="item in results" :key="item.id" type="button" @click="pick(item.id)">
            <strong>{{ item.name }}</strong><span>{{ item.exchange.toUpperCase() }}</span><small>{{ workspaceMarketLabel(item.id) }}</small>
          </button>
          <p v-if="!results.length">{{ cw('noSymbols') }}</p>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { XMarkIcon } from '@heroicons/vue/24/outline'
import { useModalDialog } from '@/composables/useModalDialog'
import type { ChartSymbol } from '@/modules/chartWorkspace/api'
import { cw, workspaceMarketLabel } from '@/modules/chartWorkspace/locale'

const props = defineProps<{ symbols: ChartSymbol[]; title: 'addWatch' | 'switchSymbol' }>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ select: [id: string] }>()
const query = ref('')
const market = ref('all')
const searchInput = ref<HTMLInputElement>()
const filters = [{ value: 'all', label: 'all' }, { value: 'spot', label: 'spot' }, { value: 'usdm', label: 'perpetual' }, { value: 'index', label: 'index' }]
const results = computed(() => props.symbols.filter(item => (market.value === 'all' || item.market === market.value)
  && `${item.id} ${item.name}`.toLowerCase().includes(query.value.trim().toLowerCase())).slice(0, 100))
const { dialogRef } = useModalDialog(open, () => { open.value = false }, searchInput)
function pick(id: string) {
  emit('select', id)
  open.value = false
}
</script>

<style scoped>
.symbol-picker { width: min(560px, 92vw); height: min(560px, 85dvh); display: flex; flex-direction: column; }
.symbol-picker header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-bottom: 1px solid var(--ui-border); }
.symbol-picker > input { min-height: 36px; margin: 10px 12px; }
.symbol-filters { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 12px 6px; }
.symbol-results { overflow: auto; padding: 0 12px; font-size: 13px; }
.symbol-results > button { display: flex; align-items: center; width: 100%; text-align: left; padding: 10px 6px; border-bottom: 1px solid var(--ui-border); gap: 9px; }
.symbol-results button:hover { background: var(--ui-hover); }
.symbol-results strong { flex: 1; }
.symbol-results :is(span, small, p) { color: var(--ui-muted); }
.symbol-results p { padding: 10px 6px; }
</style>
