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
          <button v-for="item in results" :key="item.id" type="button" @pointerenter="emit('preload',item.id)" @focus="emit('preload',item.id)" @click="pick(item.id)">
            <strong>{{ symbolName(item) }}</strong><small>{{ workspaceMarketLabel(item.id) }}</small>
          </button>
          <p v-if="!results.length && !searching && !searchError">{{ cw('noSymbols') }}</p>
          <p v-if="searching" role="status">{{ cw('searchingOnchain') }}</p>
          <p v-else-if="searchError" role="alert">{{ cw('onchainSearchFailed') }}</p>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { XMarkIcon } from '@heroicons/vue/24/outline'
import { useModalDialog } from '@/composables/useModalDialog'
import type { ChartSymbol } from '@/modules/chartWorkspace/api'
import { chartApi } from '@/modules/chartWorkspace/api'
import { cw, workspaceMarketLabel, symbolName } from '@/modules/chartWorkspace/locale'
import { isOnchainAddressQuery, matchesChartSymbol } from '@/modules/chartWorkspace/symbolSearch'

const props = defineProps<{ symbols: ChartSymbol[]; title: 'addWatch' | 'switchSymbol' }>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ select: [id: string]; preload: [id: string]; discovered: [symbols: ChartSymbol[]] }>()
const query = ref('')
const market = ref('all')
const searchInput = ref<HTMLInputElement>()
const remote = ref<ChartSymbol[]>([]), searching = ref(false), searchError = ref(false)
const filters = [{ value: 'all', label: 'all' }, { value: 'spot', label: 'spot' }, { value: 'usdm', label: 'perpetual' }, { value: 'alpha', label: 'alpha' }, { value: 'web3', label: 'web3' }, { value: 'index', label: 'index' }, { value: 'fx', label: 'fx' }, { value: 'commodity', label: 'commodity' }]
const results = computed(() => [...new Map([...props.symbols, ...remote.value].map(item => [item.id, item])).values()].filter(item => (market.value === 'all' || item.market === market.value)
  && (matchesChartSymbol(item, query.value) || workspaceMarketLabel(item.id).toLowerCase().includes(query.value.trim().toLowerCase()))).slice(0, 100))
const { dialogRef } = useModalDialog(open, () => { open.value = false }, searchInput)
watch([open, query], ([isOpen, text], _, cleanup) => {
  remote.value = []; searching.value = false; searchError.value = false
  if (!isOpen || !isOnchainAddressQuery(text)) return
  const abort = new AbortController()
  searching.value = true
  const timer = setTimeout(() => {
    void chartApi.searchSymbols(text.trim(), abort.signal).then(items => {
      if (abort.signal.aborted) return
      remote.value = items
      emit('discovered', items)
    }).catch(() => { if (!abort.signal.aborted) searchError.value = true })
      .finally(() => { if (!abort.signal.aborted) searching.value = false })
  }, 300)
  cleanup(() => { clearTimeout(timer); abort.abort() })
})
function pick(id: string) {
  emit('select', id)
  open.value = false
}
</script>

<style scoped>
.symbol-picker { width: min(560px, 92vw); height: min(560px, 85dvh); display: flex; flex-direction: column; }
.symbol-picker > header, .symbol-picker > input, .symbol-filters { flex-shrink: 0; }
.symbol-picker header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-bottom: 1px solid var(--ui-border); }
.symbol-picker > input { min-height: 36px; margin: 10px 12px; }
.symbol-filters { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 12px 6px; }
.symbol-results { flex: 1; min-height: 0; overflow: auto; scrollbar-gutter: stable; overscroll-behavior: contain; padding: 0 12px; font-size: 13px; }
.symbol-results > button { display: flex; align-items: center; width: 100%; text-align: left; padding: 10px 6px; border-bottom: 1px solid var(--ui-border); gap: 9px; }
.symbol-results button:hover { background: var(--ui-hover); }
.symbol-results strong { flex: 1; }
.symbol-results :is(span, small, p) { color: var(--ui-muted); }
.symbol-results p { padding: 10px 6px; }
</style>
