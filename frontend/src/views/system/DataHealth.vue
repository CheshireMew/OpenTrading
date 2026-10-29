<template>
  <div class="app-page"><div class="app-page-inner-wide">
    <header class="app-workspace-header"><div><h1 class="app-title">{{ t('dataHealth.title') }}</h1><p v-if="health" class="app-muted">{{ dateTime(health.checkedAt) }}</p></div><div class="flex flex-wrap gap-2"><button type="button" class="app-button-secondary" :disabled="loading || repairing" @click="load">{{ loading ? t('dataHealth.loading') : t('dataHealth.refresh') }}</button><button type="button" class="app-button-secondary" :disabled="repairing" @click="repair('verify_database')">{{ t('dataHealth.verifyDb') }}</button></div></header>
    <div v-if="error" role="alert" class="app-inline-note text-rose-700 dark:text-rose-300">{{ error }}<button type="button" class="ml-3 underline" :disabled="loading" @click="load">{{ t('common.retry') }}</button></div>
    <div v-if="feedback" role="status" class="app-inline-note">{{ feedback }}</div>
    <AppLoadingState v-if="loading && !health" :label="t('dataHealth.loading')" />
    <template v-if="health">
      <dl class="app-metric-strip"><div><dt>{{ t('dataHealth.overall') }}</dt><dd :class="statusTone(health.status)">{{ statusLabel(health.status) }}</dd></div><div><dt>{{ t('ui.needsAttention') }}</dt><dd><a href="#health-attention" class="health-summary-link">{{ affectedSources.length }}</a></dd></div><div><dt>{{ t('dataHealth.sources') }}</dt><dd>{{ health.sources?.length || 0 }}</dd></div><div><dt>{{ t('dataHealth.revision') }}</dt><dd>{{ health.databaseRevision || '—' }}</dd></div></dl>
      <section id="health-attention" class="space-y-4"><h2 class="app-section-title">{{ t('ui.needsAttention') }}</h2><p v-if="!affectedSources.length" class="app-inline-note">{{ t('ui.sourcesReady') }}</p>
        <article v-for="source in affectedSources" :key="source.id" class="app-panel health-source">
          <div class="health-source-heading"><div><h3 class="font-semibold">{{ source.name }}</h3><p v-if="source.detail" class="app-muted mt-2 text-sm">{{ source.detail }}</p></div><span class="app-chip" :class="statusTone(source.status)">{{ statusLabel(source.status) }}</span></div>
          <dl class="health-source-values"><div v-for="field in sourceFields(source)" :key="field.label"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl>
          <div v-if="source.repairActions?.length" class="mt-5 flex flex-wrap items-center gap-3"><button v-for="action in source.repairActions" :key="action" type="button" class="app-button-secondary" :disabled="repairing" @click="sourceAction(action)">{{ pendingAction === action ? t('ui.working') : actionLabel(action) }}</button></div>
        </article>
      </section>
      <details id="health-ready" v-if="readySources.length" class="app-panel"><summary class="px-5 py-4 text-sm font-semibold">{{ t('ui.readySources', { count: readySources.length }) }}</summary><div class="health-ready-list"><div v-for="source in readySources" :key="source.id" class="health-ready-row"><div><h3 class="text-sm font-semibold">{{ source.name }}</h3><p v-if="source.detail" class="app-muted mt-1 text-xs">{{ source.detail }}</p></div><span class="text-sm text-emerald-700 dark:text-emerald-300">{{ statusLabel(source.status) }}</span></div></div></details>
    </template>
    <section ref="historyPanel" class="app-panel p-5" tabindex="-1"><h2 class="app-section-title">{{ t('dataHealth.repairHistory') }}</h2><p class="app-muted mt-2 text-sm">{{ t('dataHealth.repairHint') }}</p><form class="health-history-form" @submit.prevent="repair('hydrate_symbol_history')"><label><span class="label">{{ t('dataHealth.symbol') }}</span><input ref="symbolField" v-model.trim="symbol" class="app-control w-full" placeholder="BTC/USDT" required /></label><label><span class="label">{{ t('dataHealth.timeframe') }}</span><select v-model="timeframe" class="app-control w-full"><option value="1h">1h</option><option value="4h">4h</option><option value="1d">1d</option></select></label><label><span class="label">{{ t('dataHealth.days') }}</span><input v-model.number="days" type="number" min="1" max="3650" class="app-control w-full" required /></label><button type="submit" class="app-button-primary" :disabled="repairing || !symbol">{{ pendingAction === 'hydrate_symbol_history' ? t('ui.working') : t('dataHealth.hydrate') }}</button></form></section>
    <details class="app-panel"><summary class="px-5 py-4 text-sm font-semibold">{{ t('dataHealth.jobs') }}</summary><div class="flex flex-wrap gap-3 border-t p-5" style="border-color:var(--ui-border)"><button v-for="action in ['refresh_binance_snapshot', 'evaluate_research_alerts', 'evaluate_trade_signals'] as const" :key="action" type="button" class="app-button-secondary" :disabled="repairing" @click="repair(action)">{{ pendingAction === action ? t('ui.working') : actionLabel(action) }}</button></div></details>
  </div></div>
</template>
<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppLoadingState from '@/components/AppLoadingState.vue'
import { apiErrorMessage } from '@/api/request'
import { useDateTime } from '@/composables/useDateTime'
import { systemApi } from '@/modules/system/api'
import type { DataHealthResponse, DataRepairCommand, DataSourceHealthResponse } from '@/modules/system/generatedContracts'
const { t } = useI18n()
const { formatDateTime } = useDateTime()
const health = ref<DataHealthResponse | null>(null)
const loading = ref(false), repairing = ref(false), error = ref(''), feedback = ref('')
const symbol = ref('BTC/USDT'), timeframe = ref('1h'), days = ref(365), pendingAction = ref('')
const historyPanel = ref<HTMLElement | null>(null), symbolField = ref<HTMLInputElement | null>(null)
const affectedSources = computed(() => (health.value?.sources || []).filter(source => source.status !== 'ready'))
const readySources = computed(() => (health.value?.sources || []).filter(source => source.status === 'ready'))
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try { health.value = await systemApi.getDataHealth() }
  catch (cause) { error.value = apiErrorMessage(cause, t('ui.healthLoadFailed')) }
  finally { loading.value = false }
}
async function repair(action: DataRepairCommand['action']) {
  if (repairing.value) return
  repairing.value = true
  pendingAction.value = action
  error.value = ''; feedback.value = ''
  try {
    const result = await systemApi.repairData({ action, symbol: symbol.value || null, timeframe: timeframe.value, days: days.value })
    feedback.value = result.detail
    await load()
  } catch (cause) { error.value = apiErrorMessage(cause, t('ui.repairFailed')) }
  finally { repairing.value = false; pendingAction.value = '' }
}
async function sourceAction(action: string) {
  if (action === 'hydrate_symbol_history') {
    historyPanel.value?.scrollIntoView({ block: 'center', behavior: 'auto' })
    await nextTick(); symbolField.value?.focus({ preventScroll: true })
  } else if (['verify_database', 'refresh_binance_snapshot', 'evaluate_research_alerts', 'evaluate_trade_signals'].includes(action)) {
    await repair(action as DataRepairCommand['action'])
  }
}
const statusLabel = (value: string) => t('dataHealth.status.' + value)
const statusTone = (value: string) => value === 'ready' || value === 'healthy' ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'
// Health timestamps are UTC; this endpoint also returns ISO values without an offset.
const dateTime = (value?: string | null) => value ? formatDateTime(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : value + 'Z') : '—'
const age = (value: number) => value < 3600 ? Math.round(value / 60) + 'm' : value < 86400 ? (value / 3600).toFixed(1) + 'h' : (value / 86400).toFixed(1) + 'd'
const actionLabel = (value: string) => t('dataHealth.actions.' + value)
function sourceFields(source: DataSourceHealthResponse) {
  const fields = [{ label: t('dataHealth.records'), value: source.recordCount.toLocaleString() }]
  if (source.gapCount != null) fields.push({ label: t('dataHealth.gaps'), value: String(source.gapCount) })
  if (source.coverageStart) fields.push({ label: t('dataHealth.coverageStart'), value: dateTime(source.coverageStart) })
  if (source.coverageEnd) fields.push({ label: t('dataHealth.coverageEnd'), value: dateTime(source.coverageEnd) })
  if (source.ageSeconds != null) fields.push({ label: t('dataHealth.age'), value: age(source.ageSeconds) })
  if (source.lastSuccessAt) fields.push({ label: t('dataHealth.lastSuccess'), value: dateTime(source.lastSuccessAt) })
  if (source.lastFailureAt) fields.push({ label: t('dataHealth.lastFailure'), value: dateTime(source.lastFailureAt) })
  if (source.nextRunAt) fields.push({ label: t('dataHealth.nextRun'), value: dateTime(source.nextRunAt) })
  return fields
}
onMounted(load)
</script>
<style scoped>
.health-source { padding: 20px; }
.health-source-heading { display: flex; align-items: start; justify-content: space-between; gap: 16px; }
.health-source-heading > span { flex-shrink: 0; }
.health-source-values { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px 24px; margin-top: 20px; }
.health-source-values dt { color: var(--ui-muted); font-size: 12px; }
.health-source-values dd { margin-top: 6px; font-size: 14px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.health-history-form { display: grid; grid-template-columns: minmax(160px, 2fr) 1fr 1fr auto; gap: 16px; align-items: end; margin-top: 20px; }
.health-ready-list { padding: 0 20px; border-top: 1px solid var(--ui-border); }
.health-ready-row { display: flex; justify-content: space-between; gap: 20px; padding-block: 16px; border-bottom: 1px solid var(--ui-border); }
.health-ready-row:last-child { border-bottom: 0; }
@container app-content (max-width: 48rem) { .health-history-form { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@container app-content (max-width: 28rem) { .health-history-form { grid-template-columns: minmax(0, 1fr); } }
.health-summary-link { color:var(--ui-accent); text-underline-offset:5px; }
.health-summary-link:hover { text-decoration:underline; }
#health-attention { scroll-margin-top:16px; }
</style>
