<template>
  <section class="panel p-5">
    <div class="grid gap-4 xl:grid-cols-[repeat(5,minmax(0,1fr))_auto]">
      <div>
        <label class="label">{{ $t('factorResearch.symbol') }}</label>
        <select v-model="panel.form.symbol" class="input">
          <option v-for="item in panel.catalog.symbols" :key="item" :value="item">{{ item }}</option>
        </select>
      </div>
      <div>
        <label class="label">{{ $t('factorResearch.timeframe') }}</label>
        <select v-model="panel.form.timeframe" class="input">
          <option v-for="item in panel.catalog.timeframes" :key="item" :value="item">{{ $t(`compare.tf.${item}`) }}</option>
        </select>
      </div>
      <div>
        <label class="label">{{ $t('factorResearch.lookbackDays') }}</label>
        <input v-model.number="panel.form.days" class="input" type="number" min="60" step="10" />
      </div>
      <div>
        <label class="label">{{ $t('factorResearch.horizonBars') }}</label>
        <input v-model.number="panel.form.horizon_bars" class="input" type="number" min="1" step="1" />
      </div>
      <div>
        <label class="label">{{ $t('factorResearch.maxLagBars') }}</label>
        <input v-model.number="panel.form.max_lag_bars" class="input" type="number" min="0" step="1" />
      </div>
      <button class="primary-btn" :disabled="panel.loading || panel.catalogLoading" @click="panel.runAnalysis">
        {{ panel.loading ? $t('factorResearch.analyzing') : $t('factorResearch.run') }}
      </button>
    </div>

    <div class="mt-5 grid gap-5 xl:grid-cols-[minmax(0,0.72fr)_minmax(0,1fr)]">
      <div class="card-shell">
        <div class="section-title">{{ $t('factorResearch.categoryScope') }}</div>
        <div class="section-subtitle">{{ $t('factorResearch.categoryScopeHint') }}</div>
        <div class="mt-4 flex flex-wrap gap-2">
          <button v-for="category in panel.catalog.categories" :key="category" class="chip" :class="panel.categoryChipClass(category)" @click="panel.toggleCategory(category)">
            {{ category }}
          </button>
        </div>
      </div>

      <div class="card-shell">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="section-title">{{ $t('factorResearch.factorPool') }}</div>
            <div class="section-subtitle">{{ $t('factorResearch.factorPoolHint') }}</div>
          </div>
          <button class="text-sm font-medium text-[#0f6b4f] dark:text-emerald-300" @click="panel.resetFactorSelection">{{ $t('factorResearch.useAll') }}</button>
        </div>
        <div class="mt-4 flex max-h-40 flex-wrap gap-2 overflow-y-auto pr-1">
          <button v-for="factor in panel.factorPool" :key="factor.factor_id" class="chip" :class="panel.factorChipClass(factor.factor_id)" @click="panel.toggleFactor(factor.factor_id)">
            {{ factor.name }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { FactorResearchFiltersView } from '@/modules/factors/viewTypes'

const props = defineProps<{ panel: FactorResearchFiltersView }>()
const panel = props.panel
</script>

<style scoped>
.panel {
  border: 1px solid #e4ded3;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}
.label { @apply mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400; }
.input { @apply w-full border bg-white px-3 py-2 text-sm text-stone-700 outline-none transition focus:border-emerald-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100; border-color: #e4ded3; }
.primary-btn { @apply px-5 py-3 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60 dark:bg-emerald-500 dark:text-slate-950 dark:hover:bg-emerald-400; background: #0f6b4f; }
.primary-btn:hover { background: #0b5a41; }
.card-shell { @apply border p-4 dark:border-slate-700 dark:bg-slate-900/50; border-color: #e4ded3; background: #fbfaf7; }
.section-title { @apply text-sm font-semibold text-stone-950 dark:text-white; }
.section-subtitle { @apply mt-1 text-xs text-stone-500 dark:text-slate-400; }
.chip { @apply border px-3 py-1.5 text-sm font-medium transition; }

:global(.dark) .panel {
  border-color: #334155;
  background: #1e293b;
}
</style>
