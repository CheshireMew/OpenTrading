<template>
  <button v-if="compact && visible && !embedded" class="watch-backdrop" type="button" :aria-label="cw('close')" @click="emit('close')" />
  <component :is="embedded ? 'div' : 'aside'" v-if="visible" ref="dialogRef" class="watch-panel" :class="{ 'watch-drawer': compact && !embedded, 'watch-embedded': embedded }" :style="embedded ? undefined : { width: width + 'px' }"
    tabindex="-1" :role="compact && !embedded ? 'dialog' : undefined" :aria-modal="compact && !embedded ? true : undefined" :aria-label="cw('watchlist')" >
    <header class="watch-header">
      <button v-if="compact && !embedded" class="watch-icon" type="button" :aria-label="cw('close')" @click="emit('close')"><IconX /></button>
      <div class="watch-list-select">
        <select v-model="watchlistId" :aria-label="cw('watchlists')" :disabled="!watchlists.length">
          <option v-for="item in watchlists" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
        <IconChevronDown :size="14" stroke="1.25" aria-hidden="true" />
      </div>
      <button v-if="editing" class="watch-icon" type="button" :aria-label="cw('finishWatchlistEditing')" :title="cw('finishWatchlistEditing')" @click="editing = false"><IconCheck /></button>
      <button class="watch-icon" type="button" :aria-label="cw('addWatchSymbol')" :title="cw('addWatchSymbol')" :disabled="!watchlist" @click="emit('add')"><IconPlus /></button>
      <WorkspacePopover ref="optionsMenu" class="watch-options" :label="cw('watchlistActions')">
        <template #trigger><IconDots :size="20" stroke="1.25" aria-hidden="true" /><span class="sr-only">{{ cw('watchlistActions') }}</span></template>
        <div class="watch-menu">
          <button type="button" @click="listAction(controller.newWatchlist)"><IconPlaylistAdd />{{ cw('createWatchlist') }}</button>
          <button type="button" :disabled="!watchlist" @click="listAction(controller.renameWatchlist)"><IconPencil />{{ cw('renameList') }}</button>
          <button type="button" :disabled="!watchlist || controller.managing.value" @click="removeList"><IconTrash />{{ cw('deleteWatchlist') }}</button>
          <button type="button" :disabled="!watchlist" @click="listAction(() => { editing = !editing })"><IconListDetails />{{ cw(editing ? 'finishWatchlistEditing' : 'editWatchlist') }}</button>
        </div>
      </WorkspacePopover>
    </header>
    <div v-if="pendingWatch.includes(watchlistId)" class="watch-notice" role="status">
      <span>{{ cw('pendingWatch') }}</span><button type="button" @click="controller.persistWatch(watchSymbols)">{{ cw('retrySave') }}</button>
    </div>
    <div class="watch-rows">
      <table v-if="watchSymbols.length" :class="{ 'watch-editing': editing }">
        <colgroup><col class="watch-symbol-column" /><col class="watch-price-column" /><col class="watch-change-column" /><col class="watch-percent-column" /><col class="watch-remove-column" /></colgroup>
        <thead><tr><th scope="col">{{ cw('symbol') }}</th><th scope="col">{{ cw('lastPrice') }}</th><th scope="col">{{ cw('change') }}</th><th scope="col">{{ cw('changePercent') }}</th><th scope="col"><span class="sr-only">{{ cw('editWatchlist') }}</span></th></tr></thead>
        <tbody>
          <tr v-for="(id, index) in watchSymbols" :key="id" :class="{ selected: activeSymbolId === id }" draggable="true"
            @dragstart="startDrag($event, index)" @dragend="dragIndex = -1" @dragover.prevent @drop.prevent="controller.moveWatch(index)" @pointerenter="emit('preload', id)" @click="emit('select', id)">
            <td :title="symbolTitle(id)"><button class="watch-symbol" type="button" :aria-label="symbolTitle(id)" :aria-pressed="activeSymbolId === id" @focus="emit('preload', id)" @click.stop="emit('select', id)">
              <WorkspaceSymbolIcon :symbol="symbolsById.get(id)" :fallback="id" /><span>{{ displaySymbol(id) }}</span>
            </button></td>
            <td :class="quoteClass(id)" :title="priceText(quotes[id]?.price)">{{ priceText(quotes[id]?.price) }}</td>
            <td :class="quoteClass(id)" :title="signedText(quotes[id]?.change)">{{ signedText(quotes[id]?.change) }}</td>
            <td :class="quoteClass(id)" :title="messageText(quotes[id]?.error ?? quotes[id]?.basis)">{{ percentText(quotes[id]?.change_pct) }}</td>
            <td><button class="watch-remove" type="button" :disabled="controller.managing.value" :aria-label="cw('removeSymbol', { symbol: displaySymbol(id) })" :title="cw('removeSymbol', { symbol: displaySymbol(id) })" @click.stop="controller.removeWatch(id)"><IconX :size="14" stroke="1.25" /></button></td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="watchlist" class="watch-empty"><p>{{ cw('emptyWatchlist') }}</p><button type="button" class="mt-2 underline" @click="emit('add')">{{ cw('addWatchSymbol') }}</button></div>
    </div>
    <section v-if="activeSymbol" class="watch-instrument">
      <strong>{{ activeSymbol.name }}</strong>
      <small>{{ workspaceMarketLabel(activeSymbol.id) }}</small>
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
  </component>
  <AppConfirmDialog ref="confirmation" />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import IconPlus from '@tabler/icons-vue/icons/IconPlus'
import IconX from '@tabler/icons-vue/icons/IconX'
import IconDots from '@tabler/icons-vue/icons/IconDots'
import IconCheck from '@tabler/icons-vue/icons/IconCheck'
import IconChevronDown from '@tabler/icons-vue/icons/IconChevronDown'
import IconPlaylistAdd from '@tabler/icons-vue/icons/IconPlaylistAdd'
import IconPencil from '@tabler/icons-vue/icons/IconPencil'
import IconListDetails from '@tabler/icons-vue/icons/IconListDetails'
import IconTrash from '@tabler/icons-vue/icons/IconTrash'
import AppConfirmDialog from '@/components/AppConfirmDialog.vue'
import { useI18n } from 'vue-i18n'
import WorkspacePopover from './WorkspacePopover.vue'
import WorkspaceSymbolIcon from './WorkspaceSymbolIcon.vue'
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
  embedded?: boolean
}>()
const emit = defineEmits<{ add: []; select: [id: string]; preload: [id: string]; close: [] }>()
const { watchlists, watchlist, watchlistId, watchSymbols, pendingWatch, quotes, dragIndex } = props.controller
const { dialogRef } = useModalDialog(computed(() => props.visible && props.compact && !props.embedded), () => emit('close'))
const symbolsById = computed(() => new Map(props.symbols.map(item => [item.id, item])))
const activeSymbol = computed(() => symbolsById.value.get(props.activeSymbolId))
const activeQuote = computed(() => quotes.value[props.activeSymbolId])
const editing = ref(false)
const optionsMenu = ref<InstanceType<typeof WorkspacePopover>>()
const {t}=useI18n(),confirmation=ref<InstanceType<typeof AppConfirmDialog>>()
async function removeList(){optionsMenu.value?.close();const list=watchlist.value;if(list&&await confirmation.value?.confirm(list.name,t('ui.deleteWatchlistContents')))await props.controller.deleteWatchlist()}
function listAction(action: () => unknown) { optionsMenu.value?.close(); void action() }
const displaySymbol = (id: string) => {
  const symbol = symbolsById.value.get(id)
  const ticker = symbol?.market === 'alpha' || symbol?.market === 'web3' ? symbol.name.split('/')[0] : symbol?.symbol
  return (ticker ?? id.split(':').pop() ?? id) + (symbol?.market === 'usdm' ? '.P' : '')
}
const symbolTitle = (id: string) => [displaySymbol(id), workspaceMarketLabel(id), quotes.value[id]?.basis === '交易日' ? cw('tradingDay') : '24h'].join(' · ')
const priceText = (value: unknown) => formatNumber(value, 8)
const signedText = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? (value > 0 ? '+' : '') + priceText(value) : '—'
const percentText = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%` : '—'
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
.watch-panel { display: flex; flex: 0 0 auto; flex-direction: column; min-width: 320px; max-width: 520px; min-height: 0; background: var(--ui-panel); color: var(--ui-text); font-size: 13px; outline: none; }
.watch-panel.watch-embedded { flex: 1; min-width: 0; max-width: none; }
.watch-header { display: flex; flex: 0 0 auto; align-items: center; gap: 4px; min-height: 48px; padding: 4px 8px 4px 12px; border-bottom: 1px solid var(--ui-border); }
.watch-list-select { position: relative; flex: 1; min-width: 0; }
.watch-header .watch-list-select select { display: block; width: 100%; min-width: 0; padding: 5px 22px 5px 0; border: 0; appearance: none; outline-offset: 2px; background: transparent; color: var(--ui-title); font-size: 15px; font-weight: 600; text-overflow: ellipsis; cursor: pointer; }
.watch-list-select option { background: var(--ui-panel); color: var(--ui-text); }
.watch-list-select > svg { position: absolute; top: 50%; right: 3px; transform: translateY(-50%); pointer-events: none; color: var(--ui-muted); }
.watch-panel button { border-radius: 4px; color: inherit; white-space: nowrap; }
.watch-panel button:hover { background: var(--ui-hover); }
.watch-panel button:disabled { color: var(--ui-faint); opacity: 1; }
.watch-icon { display: inline-flex; flex: 0 0 32px; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; }
.watch-icon svg { width: 20px; height: 20px; }
.watch-options { position: relative; flex: 0 0 32px; }
.watch-options :deep(summary) { display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 4px; list-style: none; cursor: pointer; }
.watch-options :deep(summary::-webkit-details-marker) { display: none; }
.watch-options :deep(summary:hover), .watch-options[open] :deep(summary) { background: var(--ui-hover); }
.watch-menu { position: absolute; z-index: 8; top: calc(100% + 6px); right: 0; width: max-content; min-width: 180px; padding: 5px; border: 1px solid var(--ui-borderStrong); border-radius: 6px; background: var(--ui-panel); box-shadow: 0 8px 24px #0003; }
.watch-menu button { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 34px; padding: 6px 10px; text-align: left; }
.watch-menu svg { width: 18px; height: 18px; }
.watch-notice { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 6px 10px; background: var(--ui-elevated); font-size: 12px; }
.watch-rows { flex: 1; min-height: 74px; overflow: auto; overscroll-behavior: contain; }
.watch-rows table { width: 100%; min-width: 320px; table-layout: fixed; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.watch-symbol-column { width: 35%; }.watch-price-column { width: 25%; }.watch-change-column { width: 20%; }.watch-percent-column { width: 20%; }
.watch-remove-column { width: 32px; }
.watch-rows th { position: sticky; top: 0; z-index: 1; height: 34px; padding: 0 5px; border-bottom: 1px solid var(--ui-borderStrong); background: var(--ui-panel); color: var(--ui-muted); font-size: 12px; font-weight: 500; text-align: right; white-space: nowrap; }
.watch-rows td { height: 32px; padding: 0 5px; overflow: hidden; border-bottom: 1px solid var(--ui-border); font-size: 13px; text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.watch-rows :is(td, th):first-child { padding-left: 8px; padding-right: 2px; text-align: left; }
.watch-rows :is(td, th):last-child { padding-right: 8px; }
.watch-rows tr { cursor: pointer; }
.watch-rows tr.selected { background: var(--ui-hover); }
.watch-rows tbody tr:hover { background: var(--ui-hover); }
.watch-rows .watch-symbol { display: flex; align-items: center; gap: 7px; width: 100%; min-width: 0; height: 31px; padding: 0; background: transparent; text-align: left; font-size: 13px; font-weight: 500; }
.watch-symbol > span:last-child { overflow: hidden; text-overflow: ellipsis; }
.watch-rows .watch-remove { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; color: var(--ui-muted); }
.watch-rows .watch-remove:hover { color: var(--ui-negative); }
.watch-empty { padding: 12px; color: var(--ui-muted); }
.watch-up { color: var(--ui-positiveInk) !important; }
.watch-down { color: var(--ui-negativeInk) !important; }
.watch-instrument { flex: 0 0 auto; max-height: 48%; overflow: auto; padding: 11px 12px; border-top: 1px solid var(--ui-border); }
.watch-instrument > strong { color: var(--ui-title); font-size: 15px; }
.watch-instrument small { font-size: 11px; color: var(--ui-muted); }
.watch-instrument > small { display: block; margin-top: 2px; }
.watch-price { margin: 8px 0; font-size: clamp(18px, 2vw, 24px); font-weight: 600; font-variant-numeric: tabular-nums; }
.watch-instrument dl { display: grid; grid-template-columns: 1fr auto; gap: 4px 8px; font-size: 12px; }
.watch-instrument dt { color: var(--ui-muted); }
.watch-instrument dd { margin: 0; text-align: right; }
.watch-instrument footer { display: flex; gap: 4px; margin-top: 6px; }
.watch-instrument footer button{min-height:32px;padding:4px 6px}
.watch-quote-error { color: var(--ui-negativeInk); margin-bottom: 6px; }
.watch-backdrop { position: absolute; inset: 0; z-index: 29; background: #0005 !important; border-radius: 0 !important; }
.watch-drawer { position: absolute; inset-block: 0; right: 0; z-index: 30; min-width: 0; max-width: calc(100% - 32px); box-shadow: -8px 0 24px #0003; }
@media(pointer:coarse){.watch-remove-column{width:44px}.watch-rows .watch-remove{width:44px;height:44px}.watch-rows td{height:44px}.watch-icon,.watch-options :deep(summary),.watch-instrument footer button{min-width:44px;min-height:44px}.watch-header{padding-left:8px}.watch-rows table{min-width:320px}}
</style>
