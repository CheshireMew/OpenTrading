<template>
  <section class="app-panel">
    <div class="app-panel-header flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <h2 class="app-section-title">{{ t('portfolioRisk.title') }}</h2>
      <div class="grid gap-2 sm:grid-cols-[8rem_12rem_auto]">
        <select v-model.number="periodDays" class="app-control"><option :value="90">90 days</option><option :value="365">1 year</option><option :value="1095">3 years</option></select>
        <input v-model.trim="benchmark" class="app-control" placeholder="BTC/USDT" />
        <button type="button" class="app-button-primary" :disabled="loading" @click="load">{{ loading ? t('portfolioRisk.running') : t('portfolioRisk.run') }}</button>
      </div>
    </div>
    <div v-if="error" class="m-5 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200" role="alert">{{ error }}</div>
    <div v-if="analytics" class="space-y-5 p-5">
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <article v-for="card in cards" :key="card.label" class="border bg-stone-50 p-4 dark:border-slate-700 dark:bg-slate-900/40"><p class="text-xs app-muted">{{ card.label }}</p><p class="mt-2 text-lg font-semibold" :class="card.tone">{{ card.value }}</p></article>
      </div>

      <div v-if="analytics.performance?.length" class="border p-4 dark:border-slate-700">
        <div class="flex items-center justify-between"><h3 class="font-semibold">{{ t('portfolioRisk.equityCurve') }}</h3><span class="text-xs app-muted">{{ analytics.startDate }} — {{ analytics.endDate }}</span></div>
        <svg viewBox="0 0 800 180" class="mt-4 h-44 w-full" preserveAspectRatio="none" role="img" :aria-label="t('portfolioRisk.equityCurve')"><polyline :points="equityPoints" fill="none" stroke="currentColor" stroke-width="3" class="text-emerald-600" vector-effect="non-scaling-stroke" /></svg>
      </div>

      <div class="grid gap-5 2xl:grid-cols-2">
        <div class="min-w-0"><h3 class="font-semibold">{{ t('portfolioRisk.riskContribution') }}</h3><div class="app-table-scroll mt-3 border dark:border-slate-700"><table class="min-w-full text-sm"><thead class="app-table-head"><tr><th class="px-3 py-2 text-left">{{ t('portfolioRisk.asset') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioRisk.weight') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioRisk.volatility') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioRisk.contribution') }}</th><th class="px-3 py-2 text-right">{{ t('portfolioRisk.periodReturn') }}</th></tr></thead><tbody><tr v-for="asset in analytics.assets || []" :key="asset.symbol" class="app-table-row"><td class="px-3 py-3 font-semibold">{{ asset.symbol }}</td><td class="px-3 py-3 text-right">{{ pct(asset.weightPct) }}</td><td class="px-3 py-3 text-right">{{ pct(asset.annualizedVolatilityPct) }}</td><td class="px-3 py-3 text-right">{{ pct(asset.riskContributionPct) }}</td><td class="px-3 py-3 text-right">{{ pct(asset.periodReturnPct) }}</td></tr></tbody></table></div></div>
        <div class="min-w-0"><h3 class="font-semibold">{{ t('portfolioRisk.correlation') }}</h3><div class="app-table-scroll mt-3 border dark:border-slate-700"><table class="min-w-full text-sm"><thead class="app-table-head"><tr><th class="px-3 py-2"></th><th v-for="symbol in analytics.symbols || []" :key="symbol" class="px-3 py-2 text-right">{{ short(symbol) }}</th></tr></thead><tbody><tr v-for="row in analytics.correlation || []" :key="row.symbol" class="app-table-row"><td class="px-3 py-3 font-semibold">{{ short(row.symbol) }}</td><td v-for="(value,index) in row.values || []" :key="index" class="px-3 py-3 text-right">{{ value == null ? '--' : value.toFixed(2) }}</td></tr></tbody></table></div></div>
      </div>

      <div class="border p-4 dark:border-slate-700">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between"><div><h3 class="font-semibold">{{ t('portfolioRisk.scenarios') }}</h3><p class="mt-1 text-sm app-muted">{{ t('portfolioRisk.scenarioHint') }}</p></div><div class="flex gap-2"><input v-model.trim="shockText" class="app-control min-w-[20rem]" placeholder="BTC/USDT:-35, ETH/USDT:-45" /><button type="button" class="app-button-secondary" @click="load">{{ t('portfolioRisk.applyShock') }}</button></div></div>
        <div class="mt-4 grid gap-3 md:grid-cols-3"><article v-for="scenario in analytics.scenarios || []" :key="scenario.id" class="border p-4 dark:border-slate-700"><p class="font-semibold">{{ scenario.name }}</p><p class="mt-2 text-xl font-semibold" :class="tone(scenario.projectedPnl)">{{ money(scenario.projectedPnl) }}</p><p class="mt-1 text-xs app-muted">{{ pct(scenario.projectedReturnPct) }} · {{ money(scenario.projectedEquity) }}</p></article></div>
      </div>
      <div v-if="analytics.issues?.length" class="border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200"><p class="font-semibold">{{ t('portfolioRisk.dataIssues') }}</p><ul class="mt-2 list-disc space-y-1 pl-5"><li v-for="issue in analytics.issues" :key="issue">{{ issue }}</li></ul></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiErrorMessage } from '@/api/request'
import { useMoney } from '@/composables/useMoney'
import { toolsApi } from '@/modules/tools'
import type { PortfolioAnalyticsResponse } from '@/modules/tools/contracts'

const props = defineProps<{ portfolioId: string; refreshKey?: string | null }>()
const { t } = useI18n(); const { formatMoney } = useMoney()
const analytics = ref<PortfolioAnalyticsResponse | null>(null); const loading = ref(false); const error = ref('')
const periodDays = ref(365); const benchmark = ref('BTC/USDT'); const shockText = ref('')
const shocks = () => Object.fromEntries(shockText.value.split(',').map(part => part.split(':').map(value => value.trim())).filter(parts => parts[0] && Number.isFinite(Number(parts[1]))).map(([symbol,value]) => [symbol.toUpperCase(), Number(value)]))
const load = async () => { if (!props.portfolioId) return; loading.value = true; error.value = ''; try { analytics.value = await toolsApi.analyzePortfolio(props.portfolioId, { periodDays: periodDays.value, benchmarkSymbol: benchmark.value || 'BTC/USDT', customShocks: shocks() }) } catch (cause) { error.value = apiErrorMessage(cause, t('portfolioRisk.failed')) } finally { loading.value = false } }
const pct = (value?: number | null) => value == null ? '--' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
const tone = (value?: number | null) => Number(value || 0) >= 0 ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'
const money = (value: number) => formatMoney(value)
const short = (value: string) => value.replace('/USDT', '')
const cards = computed(() => { const a = analytics.value; return [{ label: 'TWR', value: pct(a?.timeWeightedReturnPct), tone: tone(a?.timeWeightedReturnPct) }, { label: 'MWR / XIRR', value: pct(a?.moneyWeightedReturnPct), tone: tone(a?.moneyWeightedReturnPct) }, { label: t('portfolioRisk.benchmark'), value: pct(a?.benchmarkReturnPct), tone: tone(a?.benchmarkReturnPct) }, { label: t('portfolioRisk.volatility'), value: pct(a?.annualizedVolatilityPct), tone: '' }, { label: 'VaR 95%', value: a?.valueAtRisk95 == null ? '--' : money(a.valueAtRisk95), tone: 'text-rose-600 dark:text-rose-300' }, { label: t('portfolioRisk.maxDrawdown'), value: pct(a?.maxDrawdownPct == null ? null : -a.maxDrawdownPct), tone: 'text-rose-600 dark:text-rose-300' }] })
const equityPoints = computed(() => { const rows = analytics.value?.performance || []; if (!rows.length) return ''; const values = rows.map(row => row.equity); const min = Math.min(...values), max = Math.max(...values), range = max - min || 1; return rows.map((row,index) => `${rows.length === 1 ? 0 : index/(rows.length-1)*800},${170-(row.equity-min)/range*160}`).join(' ') })
watch(() => [props.portfolioId, props.refreshKey], load, { immediate: true })
</script>
