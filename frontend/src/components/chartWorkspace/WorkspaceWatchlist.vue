<template>
  <button v-if="compact && visible" class="watch-backdrop" type="button" :aria-label="cw('close')" @click="emit('close')" />
  <aside v-if="visible" ref="dialogRef" class="watch-panel" :class="{ 'watch-drawer': compact }" :style="{ width: width + 'px' }"
    tabindex="-1" :role="compact ? 'dialog' : undefined" :aria-modal="compact ? true : undefined" :aria-label="cw('watchlist')" >
    <header class="watch-header">
      <button v-if="compact" class="watch-icon" type="button" :aria-label="cw('close')" @click="emit('close')"><XMarkIcon /></button>
      <select v-model="watchlistId" :aria-label="cw('watchlists')" :disabled="!watchlists.length">
        <option v-for="item in watchlists" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
      <button type="button" @click="controller.newWatchlist">{{ cw('newList') }}</button>
      <button class="watch-icon" type="button" :aria-label="cw('renameList')" :disabled="!watchlist" @click="controller.renameWatchlist"><PencilSquareIcon /></button>
      <button class="watch-icon" type="button" :aria-label="cw('addWatchSymbol')" :disabled="!watchlist" @click="emit('add')"><PlusIcon /></button>
    </header>
    <div v-if="pendingWatch.includes(watchlistId)" class="watch-notice" role="status">
      <span>{{ cw('pendingWatch') }}</span><button type="button" @click="controller.persistWatch(watchSymbols)">{{ cw('retrySave') }}</button>
    </div>
    <div class="watch-rows">
      <table v-if="watchSymbols.length">
        <thead><tr><th>{{ cw('symbol') }}</th><th>{{ cw('lastAndChange') }}</th><th>{{ cw('changePercent') }}</th><th /></tr></thead>
        <tbody>
          <tr v-for="(id, index) in watchSymbols" :key="id" :class="{ selected: activeSymbolId === id }" draggable="true"
            @dragstart="startDrag($event, index)" @dragend="dragIndex = -1" @dragover.prevent @drop.prevent="controller.moveWatch(index)" @click="emit('select', id)">
            <td><button class="watch-symbol" type="button" :aria-pressed="activeSymbolId === id" @click.stop="emit('select', id)">
              <strong>{{ displaySymbol(id) }}</strong><small>{{ workspaceMarketLabel(id) }}</small>
            </button></td>
            <td :class="quoteClass(id)">{{ priceText(quotes[id]?.price) }}<small>{{ priceText(quotes[id]?.change) }}</small></td>
            <td :class="quoteClass(id)" :title="messageText(quotes[id]?.error ?? quotes[id]?.basis)">
              {{ quotes[id]?.change_pct?.toFixed(2) == null ? '—' : quotes[id]!.change_pct!.toFixed(2) + '%' }}
              <small>{{ quotes[id]?.basis === '交易日' ? cw('tradingDay') : '24h' }}</small>
            </td>
            <td><button class="watch-remove" type="button" :aria-label="cw('removeSymbol', { symbol: displaySymbol(id) })" @click.stop="controller.removeWatch(id)">×</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="watchlist" class="watch-empty"><p>{{ cw('emptyWatchlist') }}</p><button type="button" class="mt-2 underline" @click="emit('add')">{{ cw('addWatchSymbol') }}</button></div>
    </div>
    <section v-if="activeSymbol" class="watch-instrument">
      <strong>{{ activeSymbol.name }}</strong>
      <small>{{ activeSymbol.exchange.toUpperCase() }} · {{ workspaceMarketLabel(activeSymbol.id) }}</small>
      <div class="watch-price" :class="quoteClass(activeSymbol.id)">{{ priceText(activeQuote?.price) }} <small>{{ activeSymbol.currency }}</small></div>
      <p v-if="activeQuote?.error" class="watch-quote-error">{{ messageText(activeQuote.error) }}</p>
      <dl>
        <dt>{{ cw('unit') }}</dt><dd>{{ activeSymbol.metadata?.basecurrency ?? cw('notProvided') }}</dd>
        <dt>{{ cw('quoteCurrency') }}</dt><dd>{{ activeSymbol.currency }}</dd>
        <dt>{{ cw('change') }}</dt><dd>{{ priceText(activeQuote?.change) }}</dd>
        <dt>{{ cw('minimumTick') }}</dt><dd>{{ activeSymbol.metadata?.mintick ?? cw('notProvided') }}</dd>
        <dt>{{ cw('updatedAt') }}</dt><dd>{{ activeQuote?.updated_at ? formatDate(activeQuote.updated_at, true) : '—' }}</dd>
      </dl>
      <footer v-if="$slots.actions"><slot name="actions" /></footer>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { PencilSquareIcon, PlusIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { useModalDialog } from '@/composables/useModalDialog'
import { cw, formatDate, formatNumber, messageText, workspaceMarketLabel } from '@/modules/chartWorkspace/locale'
import type { ChartSymbol } from '@/modules/chartWorkspace/api'
import type { WorkspaceWatchlists } from '@/modules/chartWorkspace/workspaceWatchlists'

const props = defineProps<{
  controller: WorkspaceWatchlists
  symbols: ChartSymbol[]
  activeSymbolId: string
  visible: boolean
  compact: boolean
  width: number
}>()
const emit = defineEmits<{ add: []; select: [id: string]; close: [] }>()
const { watchlists, watchlist, watchlistId, watchSymbols, pendingWatch, quotes, dragIndex } = props.controller
const { dialogRef } = useModalDialog(computed(() => props.visible && props.compact), () => emit('close'))
const symbolsById = computed(() => new Map(props.symbols.map(item => [item.id, item])))
const activeSymbol = computed(() => symbolsById.value.get(props.activeSymbolId))
const activeQuote = computed(() => quotes.value[props.activeSymbolId])
const displaySymbol = (id: string) => symbolsById.value.get(id)?.name ?? id.split(':').pop() ?? id
const priceText = (value: unknown) => formatNumber(value, 8)
const quoteClass = (id: string) => {
  const change = quotes.value[id]?.change ?? 0
  return change > 0 ? 'watch-up' : change < 0 ? 'watch-down' : ''
}
function startDrag(event: DragEvent, index: number) {
  dragIndex.value = index
  event.dataTransfer?.setData('text/plain', watchSymbols.value[index])
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
</script>

<style scoped>
.watch-panel { display: flex; flex: 0 0 auto; flex-direction: column; min-width: 240px; max-width: 520px; min-height: 0; background: var(--ui-panel); color: var(--ui-text); font-size: 13px; outline: none; }
.watch-header { display: flex; flex: 0 0 auto; align-items: center; gap: 5px; padding: 7px 10px; border-bottom: 1px solid var(--ui-border); }
.watch-header select { flex: 1; min-width: 55px; padding: 4px 6px; border: 1px solid var(--ui-border); background: var(--ui-panel); border-radius: 4px; }
.watch-panel button { border-radius: 4px; padding: 4px 6px; color: inherit; white-space: nowrap; }
.watch-panel button:hover { background: var(--ui-hover); }
.watch-panel button:disabled { opacity: .45; }
.watch-icon svg { width: 16px; height: 16px; }
.watch-notice { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 6px 10px; background: var(--ui-elevated); font-size: 12px; }
.watch-rows { flex: 1; min-height: 74px; overflow: auto; }
.watch-rows table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.watch-rows th { position: sticky; top: 0; background: var(--ui-panel); color: var(--ui-muted); padding: 8px 4px; font-size: 11px; text-align: right; white-space: nowrap; }
.watch-rows td { padding: 7px 4px; border-bottom: 1px solid var(--ui-border); text-align: right; white-space: nowrap; }
.watch-rows :is(td, th):first-child { padding-left: 10px; text-align: left; }
.watch-rows td:last-child { width: 20px; }
.watch-rows small { display: block; margin-top: 2px; color: var(--ui-muted); font-size: 10px; }
.watch-rows tr { cursor: pointer; }
.watch-rows tr.selected { background: var(--ui-hover); box-shadow: inset 3px 0 var(--ui-accent); }
.watch-rows tbody tr:hover { background: var(--ui-hover); }
.watch-rows .watch-symbol { padding: 0; text-align: left; font-weight: 500; }
.watch-rows .watch-remove { opacity: 0; min-width: 18px; padding: 0 3px; }
.watch-rows tr:hover .watch-remove, .watch-rows tr:focus-within .watch-remove { opacity: 1; }
.watch-empty { padding: 12px; color: var(--ui-muted); }
.watch-up { color: var(--ui-positive) !important; }
.watch-down { color: var(--ui-negative) !important; }
.watch-instrument { flex: 0 0 auto; max-height: 48%; overflow: auto; padding: 11px 12px; border-top: 1px solid var(--ui-border); }
.watch-instrument > strong { color: var(--ui-title); font-size: 15px; }
.watch-instrument small { font-size: 11px; color: var(--ui-muted); }
.watch-instrument > small { display: block; margin-top: 2px; }
.watch-price { margin: 8px 0; font-size: clamp(18px, 2vw, 24px); font-weight: 600; font-variant-numeric: tabular-nums; }
.watch-instrument dl { display: grid; grid-template-columns: 1fr auto; gap: 4px 8px; font-size: 12px; }
.watch-instrument dt { color: var(--ui-muted); }
.watch-instrument dd { margin: 0; text-align: right; }
.watch-instrument footer { display: flex; gap: 4px; margin-top: 6px; }
.watch-quote-error { color: var(--ui-negative); margin-bottom: 6px; }
.watch-backdrop { position: absolute; inset: 0; z-index: 29; background: #0005 !important; border-radius: 0 !important; }
.watch-drawer { position: absolute; inset-block: 0; right: 0; z-index: 30; max-width: calc(100% - 32px); box-shadow: -8px 0 24px #0003; }
@media (hover: none) { .watch-rows .watch-remove { opacity: 1; } }
</style>
