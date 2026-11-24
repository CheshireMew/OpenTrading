<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <section class="app-page-header flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div><h1 class="app-title">{{ asset?.symbol || routeSymbol }}</h1></div>
        <div class="flex flex-wrap gap-2"><select :aria-label="t('assetResearch.timeframe')" v-model="timeframe" class="app-control"><option v-for="value in timeframes" :key="value" :value="value">{{ value }}</option></select><button type="button" class="app-button-secondary" :disabled="loading" @click="load">{{ t('assetResearch.refresh') }}</button><router-link v-if="compareTarget" :to="compareTarget" class="app-button-secondary">{{ t('assetResearch.openCompare') }}</router-link><AddToResearchButton v-if="asset" :symbol="asset.symbol" :asset-class="asset.assetClass" :display-name="asset.symbol" :source-context="researchSourceContext" @added="onResearchAdded" /></div>
      </section>
      <div v-if="error" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200" role="alert">{{ error }}</div>
      <div v-if="loading && !asset" class="app-panel p-10 text-center app-muted">{{ t('assetResearch.loading') }}</div>
      <template v-else-if="asset">
        <section class="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <article class="app-panel p-5"><p class="text-xs app-muted">{{ t('assetResearch.currentPrice') }}</p><p class="mt-2 text-2xl font-semibold">{{ number(asset.currentPrice) }}</p></article>
          <article v-for="indicator in indicatorCards" :key="indicator.label" class="app-panel p-5"><p class="text-xs app-muted">{{ indicator.label }}</p><p class="mt-2 text-xl font-semibold">{{ indicator.value }}</p></article>
          <article class="app-panel p-5"><p class="text-xs app-muted">{{ t('assetResearch.trackedIn') }}</p><p class="mt-2 text-xl font-semibold">{{ asset.watchItems?.length || 0 }}</p></article>
        </section>
        <section class="app-panel p-5"><div class="flex items-center justify-between"><h2 class="app-section-title">{{ t('assetResearch.priceHistory') }}</h2><span class="app-chip">{{ timeframe }}</span></div><SignalLabChart v-if="asset.history?.length" class="mt-5" :label="`${asset.symbol} · ${t('assetResearch.priceHistory')}`" :dates="historyDates" :series="historySeries" time-of-day /><p v-else class="py-12 text-center app-muted">{{ t('assetResearch.noHistory') }}</p></section>
        <div v-if="asset.assetClass === 'web3'" class="grid gap-5 xl:grid-cols-3">
          <section class="app-panel p-5"><h2 class="app-section-title">{{ t('assetResearch.web3Identity') }}</h2><dl class="mt-4 space-y-3 text-sm"><div><dt class="app-muted">{{ t('assetResearch.chain') }}</dt><dd class="break-all font-semibold">{{ web3Context.chainId || '--' }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.platform') }}</dt><dd class="font-semibold">{{ web3Context.platform || '--' }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.contract') }}</dt><dd class="break-all font-mono text-xs">{{ web3Context.contractAddress || '--' }}</dd></div></dl></section>
          <section class="app-panel p-5"><h2 class="app-section-title">{{ t('assetResearch.web3Rank') }}</h2><dl class="mt-4 grid grid-cols-2 gap-3 text-sm"><div><dt class="app-muted">{{ t('assetResearch.rank') }}</dt><dd class="text-xl font-semibold">{{ web3Rank.rank ?? '--' }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.heat') }}</dt><dd class="text-xl font-semibold">{{ number(web3Rank.heat_score) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.change24h') }}</dt><dd>{{ percent(web3Rank.metrics?.percent_change_24h) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.liquidity') }}</dt><dd>{{ number(web3Rank.metrics?.liquidity) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.smartMoneyRisk') }}</dt><dd>{{ web3Rank.metrics?.smart_money_risk_level ?? '--' }}</dd></div></dl></section>
          <section class="app-panel p-5"><h2 class="app-section-title">{{ t('assetResearch.web3Audit') }}</h2><dl class="mt-4 grid grid-cols-2 gap-3 text-sm"><div><dt class="app-muted">{{ t('assetResearch.risk') }}</dt><dd class="font-semibold">{{ web3Audit.risk_level_enum || web3Audit.risk_level || '--' }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.verified') }}</dt><dd>{{ booleanLabel(web3Audit.is_verified) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.buyTax') }}</dt><dd>{{ percent(web3Audit.buy_tax) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.sellTax') }}</dt><dd>{{ percent(web3Audit.sell_tax) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.riskItems') }}</dt><dd>{{ web3Audit.risk_items?.length || 0 }}</dd></div></dl></section>
        </div>
        <section v-if="benchmarkStats" class="app-panel p-5"><div class="flex flex-wrap items-center justify-between gap-3"><div><h2 class="app-section-title">{{ t('assetResearch.benchmarkComparison') }}</h2><p class="mt-1 text-sm app-muted">{{ t('assetResearch.comparisonDays', { days: benchmarkContext.days }) }} · {{ benchmarkContext.benchmarkSymbol }} · {{ benchmarkContext.timeframe }}</p></div><router-link :to="compareTarget || '/tools/compare'" class="app-button-secondary">{{ t('assetResearch.openCompare') }}</router-link></div><dl class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><div><dt class="app-muted text-xs">{{ asset.symbol }}</dt><dd class="mt-1 font-semibold">{{ percent(benchmarkStats.symbol_a_return_pct) }}</dd></div><div><dt class="app-muted text-xs">{{ benchmarkContext.benchmarkSymbol }}</dt><dd class="mt-1 font-semibold">{{ percent(benchmarkStats.symbol_b_return_pct) }}</dd></div><div><dt class="app-muted text-xs">{{ t('assetResearch.excessReturn') }}</dt><dd class="mt-1 font-semibold">{{ signedPercent(benchmarkStats.excess_return_pct) }}</dd></div><div><dt class="app-muted text-xs">{{ t('assetResearch.correlation') }}</dt><dd class="mt-1 font-semibold">{{ number(benchmarkStats.return_correlation) }}</dd></div><div><dt class="app-muted text-xs">{{ t('assetResearch.alignedPoints') }}</dt><dd class="mt-1 font-semibold">{{ benchmarkStats.aligned_points ?? '--' }}</dd></div></dl></section>
        <div class="grid gap-5 xl:grid-cols-2">
          <section class="app-panel"><div class="app-panel-header"><h2 class="app-section-title">{{ t('assetResearch.thesisAndJournal') }}</h2></div><div class="space-y-3 p-5"><article v-for="item in asset.watchItems || []" :key="item.id" class="border p-4 dark:border-slate-700"><p class="text-xs app-muted">{{ item.tags?.join(' · ') }}</p><p class="mt-2 text-sm leading-6">{{ item.thesis || t('assetResearch.noThesis') }}</p><div class="mt-3 flex gap-4 text-xs app-muted"><span>{{ t('assetResearch.target') }} {{ number(item.targetPrice) }}</span><span>{{ t('assetResearch.invalidation') }} {{ number(item.invalidationPrice) }}</span></div></article><article v-for="note in asset.notes || []" :key="note.id" class="border-l-2 border-emerald-600 pl-4"><p class="font-semibold">{{ note.title }}</p><p class="mt-1 text-sm leading-6 app-muted">{{ note.content }}</p><p class="mt-2 text-xs app-muted">{{ dateTime(note.occurredAt) }}</p></article><p v-if="!asset.watchItems?.length && !asset.notes?.length" class="py-8 text-center app-muted">{{ t('assetResearch.noResearch') }}</p></div></section>
          <section class="app-panel"><div class="app-panel-header"><h2 class="app-section-title">{{ t('assetResearch.signals') }}</h2></div><div class="space-y-3 p-5"><article v-for="signal in asset.signals || []" :key="signal.id" class="border p-4 dark:border-slate-700"><div class="flex flex-wrap gap-2"><span class="app-chip">{{ signal.source }}</span><span class="app-chip">{{ signal.timeframe }}</span><span class="app-chip">{{ outcome(signal.outcomeStatus) }}</span></div><p class="mt-3 text-sm leading-6">{{ signal.reason }}</p><dl class="mt-3 grid grid-cols-4 gap-2 text-xs"><div><dt class="app-muted">{{ t('assetResearch.entry') }}</dt><dd>{{ number(signal.entry) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.target') }}</dt><dd>{{ number(signal.target) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.mfe') }}</dt><dd>{{ percent(signal.mfePct) }}</dd></div><div><dt class="app-muted">{{ t('assetResearch.mae') }}</dt><dd>{{ percent(signal.maePct) }}</dd></div></dl></article><p v-if="!asset.signals?.length" class="py-8 text-center app-muted">{{ t('assetResearch.noSignals') }}</p></div></section>
          <section class="app-panel"><div class="app-panel-header"><h2 class="app-section-title">{{ t('assetResearch.alerts') }}</h2></div><div class="space-y-3 p-5"><article v-for="alert in asset.alerts || []" :key="alert.id" class="flex items-center justify-between gap-4 border p-4 dark:border-slate-700"><div><p class="font-semibold">{{ alert.name }}</p><p class="mt-1 text-sm app-muted">{{ alert.metric }} · {{ alert.operator }} · {{ alert.threshold }}</p></div><span class="app-chip">{{ alert.enabled ? t('assetResearch.active') : t('assetResearch.paused') }}</span></article><p v-if="!asset.alerts?.length" class="py-8 text-center app-muted">{{ t('assetResearch.noAlerts') }}</p></div></section>
          <section class="app-panel"><div class="app-panel-header"><h2 class="app-section-title">{{ t('assetResearch.timeline') }}</h2></div><div class="space-y-4 p-5"><article v-for="event in asset.events || []" :key="event.id" class="border-l-2 border-stone-300 pl-4 dark:border-slate-600"><p class="font-semibold">{{ event.title }}</p><p v-if="event.body" class="mt-1 text-sm app-muted">{{ event.body }}</p><p class="mt-2 text-xs app-muted">{{ dateTime(event.occurredAt) }}</p></article><p v-if="!asset.events?.length" class="py-8 text-center app-muted">{{ t('assetResearch.noEvents') }}</p></div></section>
        </div>
        <section v-if="contextRows.length" class="app-panel p-5"><h2 class="app-section-title">{{ t('assetResearch.marketContext') }}</h2><div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><div v-for="row in contextRows" :key="row.key" class="border p-3 dark:border-slate-700"><p class="text-xs app-muted">{{ row.key }}</p><p class="mt-1 break-all text-sm font-semibold">{{ row.value }}</p></div></div></section>
        <div v-if="asset.issues?.length" class="border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200"><ul class="list-disc space-y-1 pl-5"><li v-for="issue in asset.issues" :key="issue">{{ issue }}</li></ul></div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onActivated, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'; import { useDateTime } from '@/composables/useDateTime'
import { useRequestError } from '@/composables/useRequestError'
import { researchApi } from '@/modules/research'
import type { AssetResearchResponse, ResearchWatchItemResponse } from '@/modules/research/contracts'
import AddToResearchButton from '@/components/research/AddToResearchButton.vue'
import SignalLabChart from '@/components/market/SignalLabChart.vue'
const route = useRoute(); const { t, locale } = useI18n(); const asset = ref<AssetResearchResponse | null>(null); const loading = ref(false); const { error, setError, clearError } = useRequestError(t); const timeframe = ref('1h'); const timeframes = ['15m','1h','4h','1d']
const routeSymbol = computed(() => String(route.params.symbol || '').replace(/~/g, '/'))
let loadVersion = 0
let loadedKey = '', pendingKey = ''
const requestKey = () => JSON.stringify([routeSymbol.value, timeframe.value, route.query.asset_class, route.query.chain_id, route.query.platform])
const load = async () => {
  if (route.name !== 'AssetResearch') return
  const key = requestKey()
  if (loading.value && pendingKey === key) return
  const version = ++loadVersion
  if (loadedKey !== key) asset.value = null
  pendingKey = key; loading.value = true; clearError()
  try {
    const response = await researchApi.getAsset(routeSymbol.value, timeframe.value, 365, {
      assetClass: typeof route.query.asset_class === 'string' ? route.query.asset_class : undefined,
      chainId: typeof route.query.chain_id === 'string' ? route.query.chain_id : undefined,
      platform: typeof route.query.platform === 'string' ? route.query.platform : undefined,
    })
    if (version === loadVersion) { asset.value = response; loadedKey = key }
  } catch (reason) { if (version === loadVersion) setError(reason, 'assetResearch.loadFailed') }
  finally { if (version === loadVersion) { loading.value = false; pendingKey = '' } }
}
const loadRoute = () => { if (route.name === 'AssetResearch' && (!asset.value || requestKey() !== loadedKey)) void load() }
function onResearchAdded(symbol: string, item: ResearchWatchItemResponse) {
  const current = asset.value
  if (!current || current.symbol !== symbol) return
  // The create response is authoritative. Refreshing market history must not
  // hide a successfully saved research record behind a slow quote request.
  ++loadVersion
  loading.value = false
  clearError()
  asset.value = { ...current, watchItems: [item, ...(current.watchItems || []).filter((value: ResearchWatchItemResponse) => value.id !== item.id)] }
}
const number = (value?: number | null) => value == null ? '--' : new Intl.NumberFormat(undefined,{maximumFractionDigits:6}).format(value)
const percent = (value?: number | null) => value == null ? '--' : `${value.toFixed(2)}%`; const {formatDateTime:dateTime} = useDateTime(); const outcome = (value:string) => t(`signalReview.outcomes.${value}`)
const signedPercent = (value?: number | null) => value == null ? '--' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
const booleanLabel = (value?: boolean | null) => value == null ? '--' : value ? t('common.yes') : t('common.no')
const indicatorNumber = (value?: number | null) => value == null ? '--' : new Intl.NumberFormat(locale.value, Math.abs(value) >= 1 || value === 0 ? { maximumFractionDigits:2 } : { maximumSignificantDigits:4 }).format(value)
const indicatorCards = computed(() => { const i = asset.value?.indicators; return [{label:'RSI',value:indicatorNumber(i?.rsi)},{label:'EMA',value:indicatorNumber(i?.ema)},{label:'ATR',value:indicatorNumber(i?.atr)},{label:t('assetResearch.volatility'),value:percent(i?.annualized_volatility_pct)}] })
const historyDates = computed(() => (asset.value?.history || []).map(row => new Date(row.timestamp).toISOString()))
const historySeries = computed(() => [{ name: asset.value?.symbol || routeSymbol.value, values:(asset.value?.history || []).map(row => row.close) }])
const contextRows = computed(() => {
  const context = asset.value?.marketContext || {}
  const rows: { key: string; value: string }[] = []
  if (context.priceBasis) rows.push({ key: t('assetResearch.priceBasis'), value: String(context.priceBasis) })
  for (const [source, label] of [['spot_ticker', 'spot24h'], ['usdm_ticker', 'futures24h']] as const) {
    const ticker = context[source] as Record<string, unknown> | undefined
    const change = ticker?.priceChangePercent
    if (change != null && Number.isFinite(Number(change))) rows.push({ key: t('assetResearch.' + label), value: percent(Number(change)) })
  }
  const mark = context.usdm_mark as Record<string, unknown> | undefined
  if (mark?.lastFundingRate != null && Number.isFinite(Number(mark.lastFundingRate))) rows.push({ key: t('assetResearch.fundingRate'), value: percent(Number(mark.lastFundingRate) * 100) })
  return rows
})
const marketContext = computed<Record<string, any>>(() => asset.value?.marketContext || {})
const web3Context = computed(() => marketContext.value)
const web3Rank = computed(() => marketContext.value.web3Rank || {})
const web3Audit = computed(() => marketContext.value.web3Audit || {})
const benchmarkContext = computed(() => marketContext.value.benchmarkComparison || {})
const benchmarkStats = computed(() => benchmarkContext.value.statistics || null)
const compareTarget = computed(() => {
  if (!asset.value || asset.value.assetClass === 'web3' || asset.value.assetClass === 'cash') return ''
  const benchmark = benchmarkContext.value.benchmarkSymbol || (asset.value.symbol === 'BTC/USDT' ? 'ETH/USDT' : 'BTC/USDT')
  return { path: '/tools/compare', query: { symbol_a: asset.value.symbol, symbol_b: benchmark, days: '90', timeframe: timeframe.value } }
})
const researchSourceContext = computed(() => ({ route: route.fullPath, ...(asset.value?.assetClass === 'web3' ? { chainId: web3Context.value.chainId, platform: web3Context.value.platform, contractAddress: web3Context.value.contractAddress } : {}) }))
onBeforeUnmount(() => { loadVersion++ })
watch(() => [route.params.symbol, route.query.asset_class, route.query.chain_id, route.query.platform], loadRoute)
onMounted(loadRoute); onActivated(loadRoute)
</script>
