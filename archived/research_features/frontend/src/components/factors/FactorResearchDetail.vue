<template>
  <section class="space-y-6">
    <div class="grid gap-6 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
      <section class="panel overflow-hidden">
        <div class="border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <h2 class="text-lg font-semibold text-slate-900 dark:text-white">{{ $t('factorResearch.rankingTitle') }}</h2>
          <p class="text-sm text-slate-500 dark:text-slate-400">{{ $t('factorResearch.rankingSubtitle') }}</p>
        </div>
        <div class="max-h-[880px] overflow-y-auto">
          <button v-for="item in panel.ranking" :key="item.factor_id" class="block w-full border-b border-stone-100 px-5 py-4 text-left transition last:border-b-0 hover:bg-stone-50 dark:border-slate-700 dark:hover:bg-slate-900/50" :class="item.factor_id === panel.selectedFactorId ? 'bg-[#edf3ee] dark:bg-emerald-500/10' : ''" @click="panel.selectFactor(item.factor_id)">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-semibold text-slate-900 dark:text-white">{{ item.name }}</div>
                <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">{{ item.category }} · {{ item.feature_mode }}</div>
              </div>
              <div class="text-right">
                <div class="text-xl font-semibold" :class="panel.scoreClass(item.score)">{{ panel.formatNumber(item.score, 2) }}</div>
                <div class="text-xs text-slate-400">{{ $t('factorResearch.score') }}</div>
              </div>
            </div>
            <div class="mt-3 grid grid-cols-4 gap-2 text-xs">
              <div class="mini-stat">
                <div class="mini-stat-label">{{ $t('factorResearch.correlation') }}</div>
                <div class="mini-stat-value" :class="panel.correlationClass(item.correlation)">{{ panel.formatNumber(item.correlation, 3) }}</div>
              </div>
              <div class="mini-stat">
                <div class="mini-stat-label">{{ $t('factorResearch.stability') }}</div>
                <div class="mini-stat-value">{{ panel.formatPct(item.stability) }}</div>
              </div>
              <div class="mini-stat">
                <div class="mini-stat-label">{{ $t('factorResearch.turnover') }}</div>
                <div class="mini-stat-value">{{ panel.formatPct(item.turnover) }}</div>
              </div>
              <div class="mini-stat">
                <div class="mini-stat-label">{{ $t('factorResearch.bestLag') }}</div>
                <div class="mini-stat-value">+{{ item.best_lag }}</div>
              </div>
            </div>
          </button>
          <div v-if="!panel.ranking.length && !panel.loading" class="px-5 py-12 text-center text-sm text-slate-500 dark:text-slate-400">
            {{ $t('factorResearch.noRanking') }}
          </div>
        </div>
      </section>

      <section v-if="panel.selectedDetail" class="space-y-6">
        <div class="panel p-5">
          <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <div class="app-eyebrow">{{ panel.selectedDetail.category }}</div>
              <h2 class="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{{ panel.selectedDetail.name }}</h2>
              <p class="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">{{ panel.selectedDetail.description || $t('factorResearch.noDescription') }}</p>
            </div>
            <div class="border border-stone-200 bg-[#fbfaf7] px-4 py-3 text-sm dark:border-slate-700 dark:bg-slate-900/60">
              <div class="text-slate-500 dark:text-slate-400">{{ $t('factorResearch.sampleRange') }}</div>
              <div class="mt-1 font-semibold text-slate-900 dark:text-white">{{ panel.formatDate(panel.selectedDetail.sample_range.start) }} - {{ panel.formatDate(panel.selectedDetail.sample_range.end) }}</div>
            </div>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article class="metric-card">
            <div class="metric-label">{{ $t('factorResearch.correlation') }}</div>
            <div class="metric-value" :class="panel.correlationClass(panel.selectedDetail.correlation)">{{ panel.formatNumber(panel.selectedDetail.correlation, 3) }}</div>
          </article>
          <article class="metric-card">
            <div class="metric-label">{{ $t('factorResearch.rankCorrelation') }}</div>
            <div class="metric-value" :class="panel.correlationClass(panel.selectedDetail.rank_correlation)">{{ panel.formatNumber(panel.selectedDetail.rank_correlation, 3) }}</div>
          </article>
          <article class="metric-card">
            <div class="metric-label">{{ $t('factorResearch.hitRate') }}</div>
            <div class="metric-value text-slate-900 dark:text-white">{{ panel.formatPct(panel.selectedDetail.hit_rate) }}</div>
          </article>
          <article class="metric-card">
            <div class="metric-label">{{ $t('factorResearch.quantileSpread') }}</div>
            <div class="metric-value" :class="panel.correlationClass(panel.selectedDetail.quantile_spread)">{{ panel.formatPct(panel.selectedDetail.quantile_spread) }}</div>
          </article>
          <article class="metric-card">
            <div class="metric-label">{{ $t('factorResearch.turnover') }}</div>
            <div class="metric-value text-slate-900 dark:text-white">{{ panel.formatPct(panel.selectedDetail.turnover) }}</div>
          </article>
          <article class="metric-card">
            <div class="metric-label">{{ $t('factorResearch.icIr') }}</div>
            <div class="metric-value" :class="panel.correlationClass(panel.selectedDetail.ic_ir)">{{ panel.formatNumber(panel.selectedDetail.ic_ir, 3) }}</div>
          </article>
        </div>

        <section class="panel p-5">
          <div class="detail-head">
            <div>
              <h3 class="detail-title">{{ $t('factorResearch.forwardMetricsTitle') }}</h3>
              <p class="detail-subtitle">{{ $t('factorResearch.forwardMetricsSubtitle') }}</p>
            </div>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="border-b border-slate-200 text-left text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th class="px-2 py-3">{{ $t('factorResearch.forwardBarsShort') }}</th>
                  <th class="px-2 py-3">{{ $t('factorResearch.correlation') }}</th>
                  <th class="px-2 py-3">{{ $t('factorResearch.rankCorrelation') }}</th>
                  <th class="px-2 py-3">{{ $t('factorResearch.icIr') }}</th>
                  <th class="px-2 py-3">{{ $t('factorResearch.hitRate') }}</th>
                  <th class="px-2 py-3">{{ $t('factorResearch.quantileSpread') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in panel.selectedDetail.forward_metrics" :key="item.horizon" class="border-b border-slate-100 last:border-b-0 dark:border-slate-800">
                  <td class="px-2 py-3 font-medium text-slate-900 dark:text-white">+{{ item.horizon }}</td>
                  <td class="px-2 py-3" :class="panel.correlationClass(item.correlation)">{{ panel.formatNumber(item.correlation, 3) }}</td>
                  <td class="px-2 py-3" :class="panel.correlationClass(item.rank_correlation)">{{ panel.formatNumber(item.rank_correlation, 3) }}</td>
                  <td class="px-2 py-3" :class="panel.correlationClass(item.ic_ir)">{{ panel.formatNumber(item.ic_ir, 3) }}</td>
                  <td class="px-2 py-3 text-slate-900 dark:text-white">{{ panel.formatPct(item.hit_rate) }}</td>
                  <td class="px-2 py-3" :class="panel.correlationClass(item.quantile_spread)">{{ panel.formatPct(item.quantile_spread) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>
    </div>

    <section v-if="panel.selectedDetail" class="grid gap-6 xl:grid-cols-2">
      <section class="detail-card">
        <div class="detail-head">
          <div>
            <h3 class="detail-title">{{ $t('factorResearch.seriesTitle') }}</h3>
            <p class="detail-subtitle">{{ $t('factorResearch.seriesSubtitle') }}</p>
          </div>
        </div>
        <div class="h-[320px]">
          <FactorLineChart :dark="panel.isDark" :categories="panel.selectedDetail.normalized_series.map((item) => item.date.slice(0, 10))" :series="[
            { name: $t('factorResearch.priceZ'), data: panel.selectedDetail.normalized_series.map((item) => item.price_z), color: '#0f172a' },
            { name: $t('factorResearch.factorZ'), data: panel.selectedDetail.normalized_series.map((item) => item.factor_z), color: '#06b6d4' },
          ]" />
        </div>
      </section>

      <section class="detail-card">
        <div class="detail-head">
          <div>
            <h3 class="detail-title">{{ $t('factorResearch.blendSeriesTitle') }}</h3>
            <p class="detail-subtitle">{{ $t('factorResearch.blendSeriesSubtitle') }}</p>
          </div>
        </div>
        <div class="h-[320px]">
          <FactorLineChart :dark="panel.isDark" :categories="(panel.blend?.normalized_series || []).map((item) => item.date.slice(0, 10))" :series="[
            { name: $t('factorResearch.priceZ'), data: (panel.blend?.normalized_series || []).map((item) => item.price_z), color: '#0f172a' },
            { name: $t('factorResearch.blendScore'), data: (panel.blend?.normalized_series || []).map((item) => item.factor_z), color: '#14b8a6' },
          ]" />
        </div>
      </section>
    </section>
  </section>
</template>

<script setup lang="ts">
import FactorLineChart from '@/components/factors/FactorLineChart.vue'
import type { FactorResearchDetailView } from '@/modules/factors/viewTypes'

const props = defineProps<{ panel: FactorResearchDetailView }>()
const panel = props.panel
</script>

<style scoped>
.panel {
  border: 1px solid #e4ded3;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}
.metric-card {
  border: 1px solid #e4ded3;
  background: #ffffff;
  padding: 1.25rem;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}
.metric-label { @apply text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400; }
.metric-value { @apply mt-3 text-2xl font-semibold; }
.detail-card {
  border: 1px solid #e4ded3;
  background: #ffffff;
  padding: 1.25rem;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}
.detail-head { @apply mb-4 flex items-center justify-between gap-3; }
.detail-title { @apply text-lg font-semibold text-stone-950 dark:text-white; }
.detail-subtitle { @apply mt-1 text-sm text-stone-500 dark:text-slate-400; }
.mini-stat { @apply px-3 py-2 dark:bg-slate-900; background: #fbfaf7; }
.mini-stat-label { @apply text-[11px] uppercase tracking-wide text-slate-400; }
.mini-stat-value { @apply mt-1 font-semibold text-stone-950 dark:text-white; }

:global(.dark) .panel,
:global(.dark) .metric-card,
:global(.dark) .detail-card {
  border-color: #334155;
  background: #1e293b;
}
</style>
