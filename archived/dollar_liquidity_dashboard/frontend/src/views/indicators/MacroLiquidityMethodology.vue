<template>
  <div class="macro-detail-page min-h-full overflow-y-auto text-slate-900 dark:text-slate-100">
    <section class="flex w-full flex-col gap-6 px-3 py-5 sm:px-4 lg:px-5 xl:px-6">
      <div class="flex flex-col gap-4 border-b border-stone-200 pb-5 dark:border-slate-800 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <RouterLink class="detail-back-link" :to="{ name: 'IndicatorsMacro' }">{{ t('macro.back') }}</RouterLink>
          <p class="detail-kicker mt-4">{{ t('macro.methodology') }}</p>
          <h1 class="detail-title mt-2">{{ t('macroMethod.title') }}</h1>
          <p class="mt-3 max-w-3xl text-sm leading-6 text-stone-600 dark:text-slate-400">
            {{ t('macroMethod.subtitle') }}
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <RouterLink class="detail-secondary-button" :to="{ name: 'IndicatorsMacroHistory' }">{{ t('macro.history') }}</RouterLink>
          <button class="detail-primary-button" :disabled="loading" @click="refresh">
            {{ loading ? t('macro.refreshing') : t('macro.refreshData') }}
          </button>
        </div>
      </div>

      <div v-if="error" class="border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-950/40 dark:text-red-200">
        {{ error }}
      </div>

      <section class="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <article class="detail-panel p-5">
          <p class="detail-kicker">{{ t('macroMethod.positioning.kicker') }}</p>
          <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('macroMethod.positioning.title') }}</h2>
          <div class="mt-5 space-y-3 text-sm leading-6 text-stone-600 dark:text-slate-400">
            <p>{{ t('macroMethod.positioning.p1') }}</p>
            <p>{{ t('macroMethod.positioning.p2') }}</p>
            <p>{{ t('macroMethod.positioning.p3') }}</p>
          </div>
        </article>

        <article class="detail-panel p-5">
          <p class="detail-kicker">{{ t('macroMethod.publicMethod.kicker') }}</p>
          <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('macroMethod.publicMethod.title') }}</h2>
          <div class="mt-5 space-y-3 text-sm leading-6 text-stone-600 dark:text-slate-400">
            <p>{{ t('macroMethod.publicMethod.p1') }}</p>
            <p>{{ t('macroMethod.publicMethod.p2') }}</p>
            <p>{{ t('macroMethod.publicMethod.p3') }}</p>
          </div>
        </article>
      </section>

      <section class="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <article class="detail-panel p-5">
          <p class="detail-kicker">{{ t('macroMethod.regimeKicker') }}</p>
          <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('macroMethod.regimeTitle') }}</h2>
          <div class="mt-5 grid gap-3 sm:grid-cols-2">
            <div v-for="regime in regimes" :key="regime.title" class="method-card">
              <div class="method-swatch" :style="{ background: regime.color }"></div>
              <h3 class="mt-3 text-sm font-semibold text-slate-950 dark:text-white">{{ regime.title }}</h3>
              <p class="mt-1 text-xs text-stone-500 dark:text-slate-400">{{ regime.range }}</p>
              <p class="mt-3 text-xs leading-5 text-stone-600 dark:text-slate-400">{{ regime.description }}</p>
            </div>
          </div>
        </article>

        <article class="detail-panel p-5">
          <p class="detail-kicker">{{ t('macroMethod.processKicker') }}</p>
          <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('macroMethod.processTitle') }}</h2>
          <ol class="mt-5 space-y-4">
            <li v-for="step in methodologySteps" :key="step.title" class="method-step">
              <span>{{ step.index }}</span>
              <div>
                <h3 class="text-sm font-semibold text-slate-950 dark:text-white">{{ step.title }}</h3>
                <p class="mt-1 text-xs leading-5 text-stone-600 dark:text-slate-400">{{ step.body }}</p>
              </div>
            </li>
          </ol>
        </article>
      </section>

      <section class="detail-panel">
        <div class="border-b border-stone-200 p-5 dark:border-slate-800">
          <p class="detail-kicker">{{ t('macroMethod.weightsKicker') }}</p>
          <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('macroMethod.weightsTitle') }}</h2>
          <p class="mt-2 text-sm text-stone-500 dark:text-slate-400">
            {{ t('macroMethod.weightsDescription') }}
          </p>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="method-table-head">
              <tr>
                <th class="px-5 py-3 font-semibold">{{ t('macro.columns.indicator') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macroMethod.columns.group') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macroMethod.columns.direction') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macroMethod.columns.rawWeight') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macro.columns.effectiveWeight') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macroMethod.columns.currentScore') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macro.columns.pressureZ') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macro.columns.percentile') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macro.columns.contribution') }}</th>
                <th class="px-5 py-3 font-semibold">{{ t('macroMethod.columns.dataLag') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="driver in drivers" :key="driver.definition.id" class="method-table-row">
                <td class="px-5 py-4">
                  <div class="font-semibold text-slate-950 dark:text-white">{{ driver.definition.label }}</div>
                  <div class="mt-1 text-xs text-stone-500 dark:text-slate-500">{{ driver.definition.description }}</div>
                </td>
                <td class="px-5 py-4">{{ driver.definition.groupLabel }}</td>
                <td class="px-5 py-4">{{ polarityLabel(driver.definition.polarity) }}</td>
                <td class="px-5 py-4">{{ componentWeight(driver) }}</td>
                <td class="px-5 py-4">{{ formatWeight(driver.effectiveWeight) }}</td>
                <td class="px-5 py-4">{{ driver.score }}</td>
                <td class="px-5 py-4" :class="driver.zScore && driver.zScore >= 0 ? 'text-[#c84c28] dark:text-orange-300' : 'text-[#0f6b4f] dark:text-emerald-300'">
                  {{ formatSignedNumber(driver.zScore) }}
                </td>
                <td class="px-5 py-4">{{ formatPercentile(driver.percentile) }}</td>
                <td class="px-5 py-4" :class="driver.contribution && driver.contribution >= 0 ? 'text-[#c84c28] dark:text-orange-300' : 'text-[#0f6b4f] dark:text-emerald-300'">
                  {{ formatSignedNumber(driver.contribution) }}
                </td>
                <td class="px-5 py-4">{{ driver.dataLagLabel }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="grid gap-4 lg:grid-cols-3">
        <article v-for="section in detailSections" :key="section.title" class="detail-panel p-5">
          <p class="detail-kicker">{{ section.kicker }}</p>
          <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ section.title }}</h2>
          <ul class="mt-5 space-y-3">
            <li v-for="item in section.items" :key="item" class="flex gap-2 text-sm leading-6 text-stone-600 dark:text-slate-400">
              <span class="mt-2 h-1.5 w-1.5 flex-shrink-0 bg-[#0f6b4f] dark:bg-emerald-400"></span>
              <span>{{ item }}</span>
            </li>
          </ul>
        </article>
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatPercentile, formatSignedNumber } from '@/modules/format'
import { useMacroLiquidityPage, type MacroDriver, type MacroPolarity } from '@/modules/market'
import { useMacroRegimes } from '@/modules/market/macroLiquidityPresentation'

const {
  loading,
  error,
  thresholds,
  drivers,
  load,
  refresh,
} = useMacroLiquidityPage(365)
const { t } = useI18n()

const regimes = useMacroRegimes(thresholds)

const methodologySteps = computed(() => Array.from({ length: 6 }, (_, index) => ({
  index: String(index + 1).padStart(2, '0'),
  title: t(`macroMethod.steps.${index}.title`),
  body: t(`macroMethod.steps.${index}.body`),
})))

const detailSections = computed(() => ['formula', 'data', 'limits'].map((section) => ({
  kicker: t(`macroMethod.details.${section}.kicker`),
  title: t(`macroMethod.details.${section}.title`),
  items: [0, 1, 2].map((index) => t(`macroMethod.details.${section}.items.${index}`)),
})))

const polarityLabel = (polarity: MacroPolarity) => (
  t(polarity === 'higherTightens' ? 'macroMethod.higherTightens' : 'macroMethod.lowerTightens')
)

const formatWeight = (value: number) => `${value.toFixed(2)}%`
const componentWeight = (driver: MacroDriver) => `${driver.rawWeight.toFixed(2)}%`

onMounted(() => {
  load()
})
</script>

<style scoped>
.macro-detail-page {
  background: #f7f4ed;
}

.dark .macro-detail-page {
  background:
    radial-gradient(circle at top left, rgba(8, 145, 178, 0.16), transparent 34rem),
    linear-gradient(180deg, #020713 0%, #030816 52%, #020617 100%);
}

.detail-panel,
.method-card {
  border: 1px solid #e4ded3;
  background: rgba(255, 255, 255, 0.88);
}

.dark .detail-panel,
.dark .method-card {
  border-color: rgba(30, 41, 59, 0.95);
  background: rgba(2, 6, 23, 0.72);
}

.method-card {
  padding: 0.9rem;
}

.detail-kicker {
  color: #0f6b4f;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.detail-title {
  color: #14110f;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(2rem, 4vw, 3.25rem);
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1.1;
}

.dark .detail-title {
  color: #ffffff;
}

.detail-back-link,
.detail-primary-button,
.detail-secondary-button {
  border: 1px solid #0f6b4f;
  padding: 0.65rem 0.95rem;
  font-size: 0.82rem;
  font-weight: 700;
}

.detail-back-link,
.detail-secondary-button {
  background: #ffffff;
  color: #0f6b4f;
}

.detail-primary-button {
  background: #0f6b4f;
  color: #ffffff;
}

.detail-primary-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.method-swatch {
  height: 0.35rem;
  width: 3rem;
}

.method-step {
  display: grid;
  grid-template-columns: 2.25rem minmax(0, 1fr);
  gap: 0.9rem;
}

.method-step span {
  color: #0f6b4f;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.35rem;
  font-weight: 700;
}

.method-table-head {
  background: rgba(237, 243, 238, 0.9);
  color: #0f172a;
}

.dark .method-table-head {
  background: rgba(15, 23, 42, 0.86);
  color: #e2e8f0;
}

.method-table-row {
  border-top: 1px solid #eee7dc;
}

.dark .method-table-row {
  border-color: rgba(30, 41, 59, 0.75);
}
</style>
