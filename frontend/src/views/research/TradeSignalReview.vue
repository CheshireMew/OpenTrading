<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <section class="app-hero-panel flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p class="app-eyebrow">Signal Validation</p>
          <h1 class="app-title mt-2">{{ t('signalReview.title') }}</h1>
          <p class="app-subtitle mt-3 max-w-3xl">{{ t('signalReview.subtitle') }}</p>
        </div>
        <button type="button" class="app-button-primary" :disabled="evaluating" @click="evaluate()">
          {{ evaluating ? t('signalReview.evaluating') : t('signalReview.evaluateAll') }}
        </button>
      </section>

      <div v-if="error" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200" role="alert">{{ error }}</div>
      <div v-if="feedback" class="border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200" role="status">{{ feedback }}</div>

      <section class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <article v-for="card in statCards" :key="card.label" class="app-panel p-5">
          <p class="text-xs font-semibold uppercase tracking-wider app-muted">{{ card.label }}</p>
          <p class="mt-2 text-2xl font-semibold text-stone-950 dark:text-white">{{ card.value }}</p>
        </article>
      </section>

      <div class="grid gap-5 xl:grid-cols-2">
        <section class="app-panel overflow-hidden">
          <div class="app-panel-header"><h2 class="app-section-title">{{ t('signalReview.confidenceCalibration') }}</h2></div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead class="app-muted"><tr><th class="p-3">{{ t('signalReview.confidenceRange') }}</th><th class="p-3">{{ t('signalReview.resolved') }}</th><th class="p-3">{{ t('signalReview.expectedWinRate') }}</th><th class="p-3">{{ t('signalReview.actualWinRate') }}</th><th class="p-3">{{ t('signalReview.calibrationGap') }}</th></tr></thead>
              <tbody><tr v-for="bucket in stats?.confidenceCalibration || []" :key="bucket.key" class="border-t dark:border-slate-700"><td class="p-3 font-semibold">{{ bucket.key }}</td><td class="p-3">{{ bucket.resolved }} / {{ bucket.total }}</td><td class="p-3">{{ percent(bucket.expectedWinRatePct) }}</td><td class="p-3">{{ percent(bucket.winRatePct) }}</td><td class="p-3" :class="gapClass(bucket.calibrationGapPct)">{{ signedPercent(bucket.calibrationGapPct) }}</td></tr></tbody>
            </table>
          </div>
        </section>
        <section class="app-panel overflow-hidden">
          <div class="app-panel-header"><h2 class="app-section-title">{{ t('signalReview.groupPerformance') }}</h2></div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead class="app-muted"><tr><th class="p-3">{{ t('signalReview.dimension') }}</th><th class="p-3">{{ t('signalReview.total') }}</th><th class="p-3">{{ t('signalReview.resolved') }}</th><th class="p-3">{{ t('signalReview.winRate') }}</th><th class="p-3">Avg MFE</th><th class="p-3">Avg MAE</th></tr></thead>
              <tbody><tr v-for="row in groupedStats" :key="row.id" class="border-t dark:border-slate-700"><td class="p-3 font-semibold">{{ row.label }}</td><td class="p-3">{{ row.total }}</td><td class="p-3">{{ row.resolved }}</td><td class="p-3">{{ percent(row.winRatePct) }}</td><td class="p-3">{{ percent(row.averageMfePct) }}</td><td class="p-3">{{ percent(row.averageMaePct) }}</td></tr></tbody>
            </table>
          </div>
        </section>
      </div>

      <section class="app-panel p-4">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(12rem,1fr)_12rem_12rem_auto]">
          <input v-model.trim="filters.symbol" class="app-control" :placeholder="t('signalReview.symbol')" @keydown.enter.prevent="load" />
          <select v-model="filters.outcome" class="app-control">
            <option value="">{{ t('signalReview.allOutcomes') }}</option>
            <option v-for="status in outcomes" :key="status" :value="status">{{ outcomeLabel(status) }}</option>
          </select>
          <select v-model="filters.source" class="app-control">
            <option value="">{{ t('signalReview.allSources') }}</option>
            <option value="rules">Rules</option><option value="ai">AI</option>
          </select>
          <button type="button" class="app-button-secondary" :disabled="loading" @click="load">{{ t('signalReview.filter') }}</button>
        </div>
        <label class="mt-3 inline-flex items-center gap-2 text-sm app-muted"><input v-model="filters.archived" type="checkbox" @change="load" />{{ t('signalReview.includeArchived') }}</label>
      </section>

      <section class="app-panel overflow-hidden">
        <div class="app-panel-header flex items-center justify-between">
          <h2 class="app-section-title">{{ t('signalReview.records') }}</h2>
          <span class="app-chip">{{ total }}</span>
        </div>
        <div v-if="loading" class="p-8 text-center app-muted">{{ t('signalReview.loading') }}</div>
        <div v-else-if="!signals.length" class="p-8 text-center app-muted">{{ t('signalReview.empty') }}</div>
        <div v-else class="divide-y divide-stone-200 dark:divide-slate-700">
          <article v-for="signal in signals" :key="signal.id" class="p-5">
            <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <router-link :to="`/research/assets/${encodeURIComponent(signal.symbol)}`" class="font-semibold text-emerald-700 hover:underline dark:text-emerald-300">{{ signal.symbol }}</router-link>
                  <span class="app-chip">{{ signal.timeframe }}</span><span class="app-chip">{{ signal.source }}</span>
                  <span class="app-chip" :class="statusClass(signal.outcomeStatus)">{{ outcomeLabel(signal.outcomeStatus) }}</span>
                  <span v-if="signal.archivedAt" class="app-chip">{{ t('signalReview.archived') }}</span>
                </div>
                <p class="mt-3 text-sm leading-6 text-stone-700 dark:text-slate-200">{{ signal.reason }}</p>
                <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4 xl:grid-cols-8">
                  <div><dt class="app-muted">Side</dt><dd>{{ signal.side || '--' }}</dd></div>
                  <div><dt class="app-muted">Entry</dt><dd>{{ format(signal.entry) }}</dd></div>
                  <div><dt class="app-muted">Target</dt><dd>{{ format(signal.target) }}</dd></div>
                  <div><dt class="app-muted">Stop</dt><dd>{{ format(signal.stop) }}</dd></div>
                  <div><dt class="app-muted">Confidence</dt><dd>{{ signal.confidence ?? '--' }}</dd></div>
                  <div><dt class="app-muted">MFE</dt><dd>{{ percent(signal.mfePct) }}</dd></div>
                  <div><dt class="app-muted">MAE</dt><dd>{{ percent(signal.maePct) }}</dd></div>
                  <div><dt class="app-muted">24h</dt><dd>{{ percent(signal.forwardReturns?.['24h']) }}</dd></div>
                </dl>
              </div>
              <div class="flex shrink-0 gap-2">
                <button type="button" class="app-button-secondary" :disabled="evaluating" @click="evaluate(signal.id)">{{ t('signalReview.evaluate') }}</button>
                <button type="button" class="app-button-secondary" @click="toggleArchive(signal)">{{ signal.archivedAt ? t('signalReview.restore') : t('signalReview.archive') }}</button>
              </div>
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { researchApi, type TradeSignalResponse, type TradeSignalStatsResponse } from '@/modules/research'

const { t } = useI18n()
const signals = ref<TradeSignalResponse[]>([])
const stats = ref<TradeSignalStatsResponse | null>(null)
const total = ref(0)
const loading = ref(false)
const evaluating = ref(false)
const error = ref('')
const feedback = ref('')
const filters = reactive({ symbol: '', outcome: '', source: '', archived: false })
const outcomes = ['pending', 'target_hit', 'stop_hit', 'ambiguous', 'expired', 'unavailable'] as const

const statCards = computed(() => {
  const value = stats.value?.overall
  return [
    { label: t('signalReview.total'), value: value?.total ?? 0 },
    { label: t('signalReview.resolved'), value: value?.resolved ?? 0 },
    { label: t('signalReview.winRate'), value: value?.winRatePct == null ? '--' : `${value.winRatePct.toFixed(1)}%` },
    { label: 'Avg MFE', value: percent(value?.averageMfePct) },
    { label: 'Avg MAE', value: percent(value?.averageMaePct) },
  ]
})
const groupedStats = computed(() => [
  ...(stats.value?.bySource || []).map((row) => ({ ...row, id: `source:${row.key}`, label: `${t('signalReview.source')}: ${row.key}` })),
  ...(stats.value?.byStrategy || []).map((row) => ({ ...row, id: `strategy:${row.key}`, label: `${t('signalReview.strategy')}: ${row.key}` })),
])

const load = async () => {
  loading.value = true; error.value = ''
  try {
    const [page, summary] = await Promise.all([
      researchApi.listSignals({ symbol: filters.symbol || null, outcome_status: filters.outcome || null, source: filters.source || null, include_archived: filters.archived, offset: 0, limit: 200 }),
      researchApi.getSignalStats(),
    ])
    signals.value = page.items || []; total.value = page.total; stats.value = summary
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason) } finally { loading.value = false }
}
const evaluate = async (id?: string) => {
  evaluating.value = true; error.value = ''; feedback.value = ''
  try { const result = await researchApi.evaluateSignals(id); feedback.value = t('signalReview.evaluatedResult', { count: result.evaluatedCount, resolved: result.resolvedCount }); await load() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason) } finally { evaluating.value = false }
}
const toggleArchive = async (signal: TradeSignalResponse) => { try { await researchApi.setSignalArchived(signal.id, signal.version, !signal.archivedAt); await load() } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason) } }
const outcomeLabel = (value: string) => t(`signalReview.outcomes.${value}`)
const statusClass = (value: string) => value === 'target_hit' ? 'text-emerald-700 dark:text-emerald-300' : value === 'stop_hit' ? 'text-rose-700 dark:text-rose-300' : ''
const format = (value?: number | null) => value == null ? '--' : new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 }).format(value)
const percent = (value?: number | null) => value == null ? '--' : `${value.toFixed(2)}%`
const signedPercent = (value?: number | null) => value == null ? '--' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
const gapClass = (value?: number | null) => value == null ? '' : Math.abs(value) <= 10 ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'
onMounted(load)
</script>
