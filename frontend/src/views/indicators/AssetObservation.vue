<template>
  <section class="observation-workspace">
    <div class="observation-main">
  <div class="observation-page">
    <header class="observation-header">
      <h1>{{ t('observation.title') }}</h1>
      <div class="observation-actions">
        <button class="app-button-secondary observation-symbol-picker" type="button" aria-haspopup="dialog" @click="openSearch('switchSymbol')">
          <span>{{ instrument?.name ?? t('observation.selectAsset') }}</span><MagnifyingGlassIcon class="h-4 w-4" aria-hidden="true" />
        </button>
        <button class="app-button-secondary" :disabled="loading" @click="refresh"><ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': loading }" />{{ t('observation.refresh') }}</button>
        <button class="app-button-secondary" type="button" :aria-expanded="watchlistVisible" @click="toggleWatchlist">{{ cw('watchlist') }}</button>
      </div>
    </header>

    <div v-if="error || watchlistError" class="observation-notice observation-error" role="alert">
      <span>{{ error || watchlistError }} {{ error && data ? t('observation.retained') : '' }}</span>
      <button class="app-button-secondary" :disabled="loading" @click="error ? refresh() : refreshWatchlist()">{{ t('common.retry') }}</button>
    </div>
    <div v-if="loading && !data" class="observation-loading" role="status">{{ t('observation.loading') }}</div>

    <template v-if="data && stats">
      <section class="observation-summary" :aria-busy="loading">
        <div class="observation-asset">
          <div class="observation-name"><h2>{{ name(symbol) }}</h2><button class="app-icon-button" :aria-label="t(watched ? 'observation.unwatch' : 'observation.watch')" :aria-pressed="watched" @click="toggleWatch"><StarIcon class="h-5 w-5" :class="{ 'observation-starred': watched }" /></button></div>
          <div class="observation-symbol">{{ instrument?.name }} · {{ isIndex ? t('observation.indexPoints') : instrument?.currency }}</div>
          <div class="observation-price">{{ number(stats.latest.close) }}<span :class="changeClass(stats.returns.day)">{{ percent(stats.returns.day) }}</span></div>
          <p class="observation-asof">{{ t('observation.asOf', { date: date(stats.latest.timestamp) }) }} · {{ t('observation.dailySnapshot') }}</p>
        </div>
        <div class="observation-main-metric">
          <span>{{ t('observation.reboundFromLow') }}</span>
          <strong :class="changeClass(stats.rebound)">{{ percent(stats.rebound) }}</strong>
          <p v-if="stats.drawdownLow">{{ t('observation.drawdownLowAt', { price: number(stats.drawdownLow.price), date: date(stats.drawdownLow.timestamp) }) }}</p>
        </div>
        <div class="observation-main-metric">
          <span>{{ t('observation.fromPeak') }}</span>
          <strong :class="changeClass(stats.drawdown)">{{ percent(stats.drawdown) }}</strong>
          <p>{{ t('observation.peakAt', { price: number(stats.peakPrice), date: date(stats.peak.timestamp) }) }}</p>
        </div>
        <div class="observation-main-metric">
          <span>{{ t('observation.recovery') }}</span>
          <strong>{{ percent(stats.recovery) }}</strong>
          <p>{{ t('observation.daysSincePeak', { days: stats.daysSincePeak }) }}</p>
        </div>
      </section>

      <div v-if="stale || data.incomplete" class="observation-notice" role="status">{{ stale ? t('observation.stale') : t('observation.incomplete') }}</div>

      <section class="observation-chart-panel">
        <div class="observation-chart-toolbar">
          <h2>{{ t('observation.priceAndDrawdown') }}</h2>
          <div class="observation-chart-controls">
            <select v-model="basis" :disabled="data.closeOnly" :aria-label="t('observation.priceBasis')"><option value="high">{{ t('observation.intradayExtremes') }}</option><option value="close">{{ t('observation.closingPrices') }}</option></select>
            <div class="observation-range" :aria-label="t('observation.chartRange')"><button v-for="item in ranges" :key="item" :aria-pressed="range === item" @click="range = item">{{ t(`observation.ranges.${item}`) }}</button></div>
          </div>
        </div>
        <AssetObservationChart :key="symbol" :bars="data.bars" :drawdowns="stats.drawdowns" :peak="stats.peakPrice" :range="range" />
        <dl class="observation-facts"><div><dt>{{ t('observation.maxDrawdown') }}</dt><dd class="observation-negative">{{ percent(stats.maxDrawdown) }}</dd></div></dl>
        <p class="observation-chart-note">{{ t('observation.chartNote') }} {{ data.closeOnly ? t('observation.closeOnly') : '' }}</p>
      </section>

      <div class="observation-details">
        <section class="observation-detail-panel">
          <h2>{{ t('observation.performance') }}</h2>
          <dl class="observation-returns"><div v-for="(value, key) in stats.returns" :key="key"><dt>{{ t(`observation.periods.${key}`) }}</dt><dd :class="changeClass(value)">{{ percent(value) }}</dd></div></dl>
        </section>
        <section class="observation-detail-panel">
          <h2>{{ t(stats.yearComplete ? 'observation.range52w' : 'observation.availableRange') }}</h2>
          <div class="observation-range-values"><strong>{{ number(stats.yearLow) }}</strong><strong>{{ number(stats.yearHigh) }}</strong></div>
          <div class="observation-range-track"><span :style="{ left: `${stats.yearPosition}%` }" /></div>
          <div class="observation-range-values observation-muted"><span>{{ t('observation.low') }}</span><span>{{ t('observation.high') }}</span></div>
          <dl class="observation-facts"><div><dt>{{ t('observation.from52wHigh') }}</dt><dd>{{ percent(percentageChange(stats.latest.close, stats.yearHigh)) }}</dd></div></dl>
        </section>
        <section class="observation-detail-panel">
          <h2>{{ t('observation.latestSession') }}</h2>
          <dl class="observation-facts"><div v-for="key in (['open', 'high', 'low', 'close'] as const)" :key="key"><dt>{{ t(`observation.ohlc.${key}`) }}</dt><dd>{{ data.closeOnly && key !== 'close' ? '—' : number(stats.latest[key]) }}</dd></div><div v-if="!isIndex"><dt>{{ t('observation.volume') }} ({{ instrument?.name.split('/')[0] }})</dt><dd>{{ number(stats.latest.volume) }}</dd></div></dl>
        </section>
      </div>

      <section class="observation-source">
        <div class="observation-source-summary"><span>{{ t('observation.source') }}：{{ sourceName }}</span><span>{{ date(data.bars[0].timestamp) }} — {{ date(stats.latest.timestamp) }} · {{ t('observation.bars', { count: data.bars.length }) }}</span></div>
        <details><summary>{{ t('observation.methodology') }}</summary><div class="observation-methodology"><p>{{ t('observation.methodologyText') }}</p><p>{{ t('observation.reboundMethod') }}</p><p>{{ t('observation.returnMethod') }}</p><p v-if="symbol === 'binance:spot:BTCUSDT'">{{ t('observation.bitcoinHistory') }}</p><p v-if="isIndex">{{ t('observation.indexMethod') }}</p><template v-if="instrument?.symbol === 'HK_HSTECH'"><p>{{ t('observation.hstechSources') }}</p><div class="observation-source-links"><a href="https://quote.eastmoney.com/gb/zsHSTECH.html" target="_blank" rel="noopener noreferrer">{{ t('observation.eastmoney') }} ↗</a><a href="https://www.bitget.com/docs/catalog/cfd-market/cfd-market" target="_blank" rel="noopener noreferrer">Bitget CFD API ↗</a><a href="https://www.hsi.com.hk/eng/indexes/all-indexes/hstech" target="_blank" rel="noopener noreferrer">{{ t('observation.indexOfficial') }} ↗</a></div></template></div></details>
      </section>
    </template>
  </div>
    </div>
    <div v-if="rightOpen && !compactWorkspace" class="observation-resizer" role="separator" aria-orientation="vertical" tabindex="0"
      :aria-label="cw('resizeWatchlist')" :aria-valuenow="rightWidth" :aria-valuemin="240" :aria-valuemax="520"
      @keydown.left.prevent="rightWidth = Math.min(520, rightWidth + 20)" @keydown.right.prevent="rightWidth = Math.max(240, rightWidth - 20)"
      @pointerdown="resizeRight" />
    <WorkspaceWatchlist :controller="listsController" :symbols="symbols" :active-symbol-id="activeSymbolId"
      :visible="watchlistVisible" :compact="compactWorkspace" :width="rightWidth"
      @select="selectFromWatchlist" @add="openSearch('addWatch')" @close="watchlistDrawerOpen = false" />
    <WorkspaceSymbolPicker v-model="searchOpen" :symbols="symbols" :title="searchTitle" @select="pickSymbol" />
    <WorkspaceNamePrompt ref="namePrompt" />
  </section>
</template>

<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowPathIcon, MagnifyingGlassIcon, StarIcon } from '@heroicons/vue/24/outline'
import WorkspaceNamePrompt from '@/components/chartWorkspace/WorkspaceNamePrompt.vue'
import WorkspaceSymbolPicker from '@/components/chartWorkspace/WorkspaceSymbolPicker.vue'
import WorkspaceWatchlist from '@/components/chartWorkspace/WorkspaceWatchlist.vue'
import AssetObservationChart from '@/components/market/AssetObservationChart.vue'
import { useRequestError } from '@/composables/useRequestError'
import { useWorkspacePanels } from '@/modules/chartWorkspace/workspacePanels'
import { createSharedWorkspaceWatchlists } from '@/modules/chartWorkspace/workspaceWatchlists'
import { cw, workspaceMarketLabel } from '@/modules/chartWorkspace/locale'
import { useAssetObservation } from '@/modules/market/useAssetObservation'
import { percentageChange, type ObservationRange } from '@/modules/market/assetObservation'

const { t, locale } = useI18n()
const { symbols, activeSymbolId, basis, data, stats, instrument, isIndex, stale, loading, error, selectSymbol, load, refreshSymbols } = useAssetObservation()
const searchOpen = ref(false)
const searchTitle = ref<'switchSymbol' | 'addWatch'>('switchSymbol')
const namePrompt = ref<InstanceType<typeof WorkspaceNamePrompt>>()
const { error: watchlistError, setError: setWatchlistError, clearError: clearWatchlistError } = useRequestError(t)
const reportWatchlistError = (cause: unknown) => setWatchlistError(cause, 'chartWorkspace.loadFailed')
watch(searchOpen, open => { if (open) void refreshSymbols().catch(reportWatchlistError) })
const listsController = createSharedWorkspaceWatchlists({
  activeSymbolId,
  requestName: (title, value) => namePrompt.value?.requestName(title, value) ?? Promise.resolve(null),
  onError: reportWatchlistError,
})
const { rightOpen, rightWidth, compactWorkspace, watchlistDrawerOpen, watchlistVisible, toggleWatchlist, resizeRight } = useWorkspacePanels({ dirty: () => {}, resizeChart: () => {} })
const symbol = activeSymbolId
const watchlist = listsController.watchSymbols
const watched = computed(() => watchlist.value.includes(activeSymbolId.value))
const instrumentsById = computed(() => new Map(symbols.value.map(item => [item.id, item])))
const name = (id: string) => {
  const item = instrumentsById.value.get(id)
  const labels: Record<string, string> = { BTCUSDT: 'bitcoin', ETHUSDT: 'ethereum', HK_HSTECH: 'hstech' }
  const label = item && labels[item.symbol] ? t('observation.' + labels[item.symbol]) : item?.name ?? id
  return item?.market === 'usdm' ? label + ' · ' + workspaceMarketLabel(id) : label
}
function toggleWatch() {
  const items = watched.value ? watchlist.value.filter(id => id !== activeSymbolId.value) : [...watchlist.value, activeSymbolId.value]
  void listsController.persistWatch(items)
}
const ranges: ObservationRange[] = ['3m', '1y', '3y', 'all']
const range = ref<ObservationRange>('all')
const number = (value: number) => value.toLocaleString(locale.value, { maximumFractionDigits: value > 0 && value < 1 ? 6 : 2 })
const percent = (value: number | null) => value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
const date = (value: number) => new Date(value).toISOString().slice(0, 10)
const changeClass = (value: number | null) => value ? value > 0 ? 'observation-positive' : 'observation-negative' : ''
const sourceName = computed(() => {
  const source = data.value?.source || ''
  const keys: Record<string, string> = { eastmoney: 'eastmoney', sina_hk: 'sina', sina_cn: 'sina', sina_us: 'sina', cache: 'cache', exchange: 'exchange' }
  return keys[source] ? t(`observation.${keys[source]}`) : source.toUpperCase()
})

function openSearch(title: typeof searchTitle.value) {
  searchTitle.value = title
  searchOpen.value = true
}
function pickSymbol(id: string) {
  if (searchTitle.value === 'switchSymbol') selectSymbol(id)
  else if (!listsController.watchSymbols.value.includes(id)) void listsController.persistWatch([...listsController.watchSymbols.value, id])
}
function selectFromWatchlist(id: string) {
  selectSymbol(id)
  watchlistDrawerOpen.value = false
}
async function refreshWatchlist() {
  clearWatchlistError()
  try {
    await listsController.loadWatchlists()
    void listsController.refreshQuotes()
  } catch (cause) { reportWatchlistError(cause) }
}
function refresh() {
  void load()
  void listsController.refreshQuotes()
}
watch(activeSymbolId, () => { void listsController.refreshQuotes() })
onMounted(() => {
  void load()
  void refreshWatchlist()
})
onBeforeUnmount(listsController.dispose)
onActivated(listsController.resume)
onDeactivated(listsController.pause)
</script>

<style scoped>
.observation-workspace { display: flex; position: relative; height: 100%; min-height: 0; background: var(--ui-canvas); }
.observation-main { flex: 1; min-width: 0; overflow: auto; container: observation-content / inline-size; }
.observation-resizer { width: 4px; flex-shrink: 0; background: var(--ui-border); cursor: col-resize; }
.observation-symbol-picker { justify-content: space-between; }

.observation-page { max-width: 1560px; margin: 0 auto; padding: 30px 32px 40px; color: var(--ui-text); font-variant-numeric: tabular-nums; }
.observation-page h1, .observation-page h2, .observation-page p { margin: 0; }
.observation-header, .observation-actions, .observation-chart-toolbar, .observation-chart-controls, .observation-name { display: flex; align-items: center; gap: 12px; }
.observation-header { justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.observation-header h1 { color: var(--ui-title); font-size: 26px; font-weight: 600; letter-spacing: -.025em; }
.observation-actions { flex-wrap: wrap; }
.observation-actions > :first-child { min-width: 190px; }
.observation-summary { display: grid; grid-template-columns: minmax(0, 1.25fr) repeat(3, minmax(0, 1fr)); gap: 28px; padding: 26px 0 30px; border-top: 1px solid var(--ui-border); }
.observation-name h2 { color: var(--ui-title); font-size: 20px; font-weight: 600; }
.observation-starred { fill: var(--ui-accent); color: var(--ui-accent); }
.observation-symbol { color: var(--ui-muted); font-size: 12px; margin: 4px 0 15px; }
.observation-price { font-size: 32px; line-height: 1.2; font-weight: 600; color: var(--ui-title); display: flex; align-items: baseline; flex-wrap: wrap; gap: 12px; }
.observation-price span { font-size: 14px; font-weight: 500; }
.observation-asof { margin-top: 10px !important; color: var(--ui-muted); font-size: 12px; }
.observation-main-metric { border-left: 1px solid var(--ui-border); padding-left: 28px; display: flex; flex-direction: column; justify-content: center; }
.observation-main-metric > span { font-size: 13px; color: var(--ui-muted); }
.observation-main-metric > strong { font-size: clamp(30px, 3vw, 44px); font-weight: 550; letter-spacing: -.04em; line-height: 1.4; color: var(--ui-title); }
.observation-main-metric p { color: var(--ui-muted); font-size: 12px; line-height: 1.7; }
.observation-positive { color: var(--ui-positiveInk) !important; }
.observation-negative { color: var(--ui-negativeInk) !important; }
.observation-chart-panel { padding: 20px 20px 14px; background: var(--ui-panel); border: 1px solid var(--ui-border); border-radius: 8px; }
.observation-chart-toolbar { justify-content: space-between; margin-bottom: 6px; flex-wrap: wrap; }
.observation-page section h2 { font-size: 15px; font-weight: 600; color: var(--ui-title); }
.observation-asset h2 { font-size: 20px !important; }
.observation-chart-controls { flex-wrap: wrap; }
.observation-chart-controls select { max-width: 180px; border: 1px solid var(--ui-border); border-radius: 5px; background: var(--ui-toolbar); color: var(--ui-text); font-size: 12px; padding: 7px 10px; }
.observation-range { display: flex; gap: 3px; }
.observation-range button { padding: 6px 10px; border-radius: 4px; font-size: 12px; color: var(--ui-muted); }
.observation-range button[aria-pressed=true] { background: var(--ui-elevated); color: var(--ui-title); }
.observation-chart-note { color: var(--ui-muted); font-size: 12px; line-height: 1.8; padding: 12px 4px 0; }
.observation-details { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; margin-top: 18px; }
.observation-detail-panel { background: var(--ui-panel); border: 1px solid var(--ui-border); border-radius: 8px; padding: 20px; }
.observation-detail-panel h2 { margin-bottom: 20px; }
.observation-returns { display: grid; grid-template-columns: 1fr 1fr; gap: 20px 14px; }
.observation-returns dt, .observation-facts dt { color: var(--ui-muted); font-size: 12px; }
.observation-returns dd { font-size: 19px; font-weight: 550; margin: 4px 0 0; }
.observation-facts { display: grid; gap: 12px; margin: 18px 0 0; }
.observation-facts > div { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.observation-facts dd { margin: 0; font-size: 13px; }
.observation-range-values { display: flex; justify-content: space-between; font-size: 14px; gap: 12px; }
.observation-range-values strong { font-weight: 500; }
.observation-muted { color: var(--ui-muted); font-size: 11px; }
.observation-range-track { position: relative; height: 5px; border-radius: 3px; background: var(--ui-elevated); margin: 16px 5px 10px; }
.observation-range-track span { position: absolute; top: -4px; height: 13px; width: 4px; border-radius: 2px; background: var(--ui-accent); transform: translateX(-50%); }
.observation-source { margin-top: 24px; font-size: 12px; color: var(--ui-muted); line-height: 1.8; }
.observation-source-summary { display: flex; flex-wrap: wrap; gap: 6px 24px; margin-bottom: 10px; }
.observation-source summary { cursor: pointer; width: fit-content; }
.observation-methodology { padding: 12px 0; max-width: 1000px; }
.observation-methodology p + p { margin-top: 8px; }
.observation-source-links { display: flex; flex-wrap: wrap; gap: 20px; margin-top: 10px; }
.observation-source-links a { color: var(--ui-accent); text-decoration: underline; text-underline-offset: 3px; }
.observation-loading { padding: 80px 20px; text-align: center; color: var(--ui-muted); }
.observation-notice { padding: 12px 16px; margin-bottom: 18px; background: var(--ui-elevated); border-radius: 6px; font-size: 13px; line-height: 1.6; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.observation-error { color: var(--ui-negativeInk); }
.observation-page button:disabled { opacity: .6; cursor: wait; }
@container observation-content (max-width: 1050px) { .observation-page { padding: 24px 20px; } .observation-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; } .observation-main-metric { padding-left: 20px; } .observation-summary > :nth-child(3) { border-left: 0; padding-left: 0; } .observation-details { gap: 12px; } .observation-detail-panel { padding: 16px; } }
@container observation-content (max-width: 760px) { .observation-header { align-items: flex-start; flex-direction: column; } .observation-summary { gap: 18px 12px; } .observation-main-metric { padding-left: 12px; } .observation-main-metric > strong, .observation-price { font-size: 26px; } .observation-details { grid-template-columns: 1fr; } .observation-chart-panel { padding: 16px 8px 12px; } .observation-chart-toolbar { padding-inline: 8px; } .observation-chart-controls { gap: 8px; } .observation-page { padding: 20px 16px; } .observation-actions { width: 100%; } .observation-actions > :first-child { flex: 1; min-width: 160px; } }
</style>
