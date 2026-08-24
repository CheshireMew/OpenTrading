<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <FactorResearchHero :panel="page.heroPanel" />
      <FactorResearchFilters :panel="page.filtersPanel" />

      <section v-if="page.error" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
        {{ page.error }}
      </section>

      <section v-if="page.summaryPanel.summary" class="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <article class="summary-card">
          <div class="summary-label">{{ $t('factorResearch.target') }}</div>
          <div class="summary-value">{{ page.summaryPanel.summary.target_label }}</div>
          <div class="summary-hint">{{ page.summaryPanel.summary.symbol }} · {{ page.summaryPanel.summary.timeframe }}</div>
        </article>
        <article class="summary-card">
          <div class="summary-label">{{ $t('factorResearch.factorCount') }}</div>
          <div class="summary-value">{{ page.summaryPanel.summary.factor_count }}</div>
          <div class="summary-hint">{{ $t('factorResearch.blendCount') }} {{ page.summaryPanel.summary.blend_factor_count }}</div>
        </article>
        <article class="summary-card">
          <div class="summary-label">{{ $t('factorResearch.sampleRange') }}</div>
          <div class="summary-value text-lg">{{ page.summaryPanel.formatDate(page.summaryPanel.summary.sample_range.start) }}</div>
          <div class="summary-hint">{{ page.summaryPanel.formatDate(page.summaryPanel.summary.sample_range.end) }}</div>
        </article>
        <article class="summary-card">
          <div class="summary-label">{{ $t('factorResearch.forwardHorizons') }}</div>
          <div class="summary-value">{{ page.summaryPanel.summary.forward_horizons.join(' / ') }}</div>
          <div class="summary-hint">{{ $t('factorResearch.horizonBars') }} {{ page.summaryPanel.summary.horizon_bars }}</div>
        </article>
        <article class="summary-card">
          <div class="summary-label">{{ $t('factorResearch.datasetId') }}</div>
          <div class="summary-value">#{{ page.summaryPanel.summary.dataset_id }}</div>
          <div class="summary-hint">{{ $t('factorResearch.maxLagBars') }} {{ page.summaryPanel.summary.max_lag_bars }}</div>
        </article>
      </section>

      <div class="grid gap-6 2xl:grid-cols-[360px_minmax(0,1fr)]">
        <FactorResearchSidebar :panel="page.sidebarPanel" />
        <FactorResearchDetail :panel="page.detailPanel" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import FactorResearchDetail from '@/components/factors/FactorResearchDetail.vue'
import FactorResearchFilters from '@/components/factors/FactorResearchFilters.vue'
import FactorResearchHero from '@/components/factors/FactorResearchHero.vue'
import FactorResearchSidebar from '@/components/factors/FactorResearchSidebar.vue'
import { useFactorResearchPage } from '@/modules/factors/useFactorResearchPage'

const page = useFactorResearchPage()
</script>

<style scoped>
.summary-card {
  border: 1px solid #e4ded3;
  background: #ffffff;
  padding: 1.25rem;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}

:global(.dark) .summary-card {
  border-color: #334155;
  background: #1e293b;
}
.summary-label { @apply text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400; }
.summary-value { @apply mt-3 text-2xl font-semibold text-stone-950 dark:text-white; }
.summary-hint { @apply mt-2 text-xs text-stone-500 dark:text-slate-400; }
</style>
