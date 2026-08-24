<template>
  <div :class="['macro-page min-h-full overflow-y-auto text-slate-900 transition-colors dark:text-slate-100', theme === 'dark' ? 'macro-page--dark' : 'macro-page--light']">
    <section class="flex w-full flex-col gap-8 px-3 py-5 sm:px-4 lg:px-5 xl:px-6">
      <div class="macro-hero max-w-4xl space-y-4 border-b border-stone-200 pb-6 dark:border-slate-800">
        <div class="macro-kicker inline-flex items-center gap-2 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]">
          Dollar Liquidity Monitor
        </div>
        <h1 class="macro-title max-w-3xl text-4xl font-semibold leading-tight dark:text-white sm:text-5xl">
          {{ t('macro.title') }}
        </h1>
        <p class="max-w-3xl text-sm leading-6 text-stone-600 dark:text-slate-400 sm:text-base">
          {{ t('macro.subtitle') }}
        </p>
      </div>

      <div v-if="error" class="border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-950/40 dark:text-red-200">
        {{ error }}
      </div>

      <div v-if="loading" class="grid gap-4 md:grid-cols-3">
        <div v-for="item in 6" :key="item" class="h-44 animate-pulse border border-slate-200 bg-white/70 dark:border-slate-800 dark:bg-slate-900/50"></div>
      </div>

      <template v-else>
        <section>
          <div class="macro-panel p-5">
            <div class="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div class="panel-kicker">{{ t('macro.scoreKicker') }}</div>
                <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('macro.pressureDashboard') }}</h2>
              </div>
              <div class="flex flex-wrap items-center gap-3">
                <select v-model.number="changeDays" class="macro-period-select self-start" :aria-label="t('macro.currentWindowLabel')" :disabled="loading" @change="load()">
                  <option :value="7">{{ t('macro.dayCount', { count: 7 }) }}</option>
                  <option :value="30">{{ t('macro.dayCount', { count: 30 }) }}</option>
                  <option :value="90">{{ t('macro.dayCount', { count: 90 }) }}</option>
                </select>
                <button class="macro-primary-button self-start" :disabled="loading" @click="refresh">
                  {{ loading ? t('macro.refreshing') : t('macro.refresh') }}
                </button>
                <RouterLink class="macro-secondary-button self-start" :to="{ name: 'IndicatorsMacroHistory' }">
                  {{ t('macro.history') }}
                </RouterLink>
                <a class="macro-secondary-button self-start" href="#macro-drivers">
                  {{ t('macro.viewDrivers') }}
                </a>
                <RouterLink class="macro-secondary-button self-start" :to="{ name: 'IndicatorsMacroMethodology' }">
                  {{ t('macro.methodology') }}
                </RouterLink>
              </div>
            </div>

            <div class="grid gap-5">
              <div class="score-summary-grid">
                <div class="score-summary-card score-summary-card--primary">
                  <span>{{ t('macro.statusPercentile') }}</span>
                  <strong :class="scoreToneClass">{{ statusPercentileLabel }}</strong>
                  <em>{{ t('macro.rawScore') }} {{ rawScore === null ? '--' : rawScore.toFixed(2) }}</em>
                </div>
                <div class="score-summary-card">
                  <span>{{ t('macro.liquidityStatus') }}</span>
                  <strong :class="scoreToneClass">{{ scoreLabel }}</strong>
                </div>
                <div class="score-summary-card">
                  <span>{{ t('macro.lastUpdated') }}</span>
                  <strong>{{ lastUpdated }}</strong>
                </div>
              </div>
              <div class="w-full">
                <div class="score-scale-track">
                  <div class="score-scale-zone score-scale-zone--tight"></div>
                  <div class="score-scale-zone score-scale-zone--neutral-tight"></div>
                  <div class="score-scale-zone score-scale-zone--neutral-loose"></div>
                  <div class="score-scale-zone score-scale-zone--loose"></div>
                  <div class="score-scale-split" style="left: 20%"></div>
                  <div class="score-scale-split" style="left: 50%"></div>
                  <div class="score-scale-split" style="left: 80%"></div>
                  <div class="score-scale-marker" :style="{ left: `${scorePercentilePosition}%` }"></div>
                </div>
                <div class="score-scale-labels">
                  <div>
                    <strong>{{ t('macro.scale.loose') }}</strong>
                    <span>≤ P20</span>
                  </div>
                  <div>
                    <strong>{{ t('macro.scale.neutralLoose') }}</strong>
                    <span>P20-P50</span>
                  </div>
                  <div>
                    <strong>{{ t('macro.scale.neutralTight') }}</strong>
                    <span>P50-P80</span>
                  </div>
                  <div>
                    <strong>{{ t('macro.scale.tight') }}</strong>
                    <span>≥ P80</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="mt-6 space-y-2 border-t border-stone-200 pt-4 dark:border-slate-800">
              <div v-for="item in alerts" :key="item" class="flex gap-2 text-sm text-stone-700 dark:text-slate-300">
                <span class="mt-2 h-1.5 w-1.5 flex-shrink-0 bg-[#0f6b4f] dark:bg-emerald-400"></span>
                <span>{{ item }}</span>
              </div>
            </div>
          </div>
        </section>

        <section v-for="group in groups" :key="group.id" class="space-y-3">
          <div class="flex flex-col justify-between gap-2 border-l-2 border-[#0f6b4f] pl-3 dark:border-emerald-400 sm:flex-row sm:items-end">
            <div>
              <h2 class="text-lg font-semibold text-slate-950 dark:text-white">{{ group.title }}</h2>
              <p class="mt-1 text-sm text-slate-500 dark:text-slate-500">{{ group.description }}</p>
            </div>
          </div>

          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <article v-for="card in group.cards" :key="card.definition.id" class="metric-card">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-xs uppercase tracking-wide text-stone-500 dark:text-slate-500">{{ card.definition.shortLabel }}</div>
                  <h3 class="mt-1 text-sm font-semibold text-slate-950 dark:text-white">{{ card.definition.label }}</h3>
                </div>
                <span :class="['change-pill', toneClass(card.tone)]">{{ card.changeLabel }}</span>
              </div>

              <div class="mt-4 flex items-end justify-between gap-3">
                <div class="text-2xl font-semibold text-slate-950 dark:text-white">{{ card.valueLabel }}</div>
                <div class="text-right text-[11px] text-stone-500 dark:text-slate-500">{{ card.freshness }}</div>
              </div>

              <MacroSparkline
                class="mt-3"
                :history="card.indicator?.history || []"
                :color="sparkColor(card.tone)"
                :mode="['TGA', 'ONRRP', 'SRF_USAGE'].includes(card.definition.id) ? 'bar' : 'line'"
              />

              <p class="mt-3 border-t border-stone-200 pt-3 text-xs leading-5 text-stone-500 dark:border-slate-800 dark:text-slate-500">
                {{ card.definition.description }}
              </p>
            </article>
          </div>
        </section>

        <section id="macro-drivers" class="macro-panel p-5">
          <div class="panel-kicker">{{ t('macro.keyDrivers') }}</div>
          <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('macro.contributionBars') }}</h2>
          <div class="mt-5 space-y-3">
            <div v-for="driver in drivers" :key="driver.definition.id" class="driver-row grid gap-2 sm:grid-cols-[150px_minmax(0,1fr)_56px] sm:items-center">
              <div class="min-w-0">
                <div class="truncate text-sm font-medium text-slate-800 dark:text-slate-200">{{ driver.definition.label }}</div>
                <div class="text-[11px] text-slate-500 dark:text-slate-500">{{ changeWindowLabel }} {{ driver.changeLabel }}</div>
              </div>
              <div class="relative h-5 bg-stone-200 dark:bg-slate-800">
                <div class="absolute inset-y-0 left-1/2 w-px bg-white dark:bg-slate-950"></div>
                <div
                  v-if="driver.score >= 50"
                  class="absolute inset-y-0 left-1/2 bg-[#c84c28] dark:bg-orange-500"
                  :style="{ width: `${driver.score - 50}%` }"
                ></div>
                <div
                  v-else
                  class="absolute inset-y-0 bg-[#0f6b4f] dark:bg-emerald-400"
                  :style="{ left: `${driver.score}%`, width: `${50 - driver.score}%` }"
                ></div>
              </div>
              <div :class="['text-right text-sm font-semibold', driver.score >= 50 ? 'text-[#c84c28] dark:text-orange-300' : 'text-[#0f6b4f] dark:text-emerald-300']">
                {{ driver.score }}
              </div>
            </div>
          </div>
        </section>

        <section class="macro-panel p-5">
          <div class="panel-kicker">{{ t('macro.modelDiagnostics') }}</div>
          <div class="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <h2 class="text-lg font-semibold text-slate-950 dark:text-white">{{ t('macro.contributionFreshness') }}</h2>
            <span class="text-xs text-stone-500 dark:text-slate-500">{{ t('macro.currentWindow', { window: changeWindowLabel }) }}</span>
          </div>
          <div class="mt-5 overflow-x-auto">
            <table class="min-w-full text-left text-sm">
              <thead class="diagnostic-table-head">
                <tr>
                  <th class="px-4 py-3 font-semibold">{{ t('macro.columns.indicator') }}</th>
                  <th class="px-4 py-3 font-semibold">{{ t('macro.columns.currentValue') }}</th>
                  <th class="px-4 py-3 font-semibold">{{ t('macro.columns.pressureZ') }}</th>
                  <th class="px-4 py-3 font-semibold">{{ t('macro.columns.percentile') }}</th>
                  <th class="px-4 py-3 font-semibold">{{ t('macro.columns.effectiveWeight') }}</th>
                  <th class="px-4 py-3 font-semibold">{{ t('macro.columns.contribution') }}</th>
                  <th class="px-4 py-3 font-semibold">{{ t('macro.columns.dataStatus') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="driver in drivers" :key="driver.definition.id" class="diagnostic-table-row">
                  <td class="px-4 py-3">
                    <div class="font-semibold text-slate-950 dark:text-white">{{ driver.definition.label }}</div>
                    <div class="mt-1 text-xs text-stone-500 dark:text-slate-500">{{ driver.definition.shortLabel }}</div>
                  </td>
                  <td class="px-4 py-3 tabular-nums">{{ driver.valueLabel }}</td>
                  <td class="px-4 py-3 tabular-nums" :class="pressureClass(driver.zScore)">{{ formatSignedNumber(driver.zScore) }}</td>
                  <td class="px-4 py-3 tabular-nums">{{ formatPercentile(driver.percentile) }}</td>
                  <td class="px-4 py-3 tabular-nums">{{ formatWeight(driver.effectiveWeight) }}</td>
                  <td class="px-4 py-3 tabular-nums" :class="pressureClass(driver.contribution)">{{ formatSignedNumber(driver.contribution) }}</td>
                  <td class="px-4 py-3">
                    <span :class="['data-lag-pill', lagClass(driver.dataLagDays)]">{{ driver.dataLagLabel }}</span>
                    <div class="mt-1 text-xs text-stone-500 dark:text-slate-500">{{ driver.freshness }}</div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="macro-panel p-5">
          <div class="panel-kicker">{{ t('macro.dataSourceStatus') }}</div>
          <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('macro.lagCheck') }}</h2>
          <div class="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div v-for="card in cards" :key="card.definition.id" class="source-status-card">
              <div class="truncate text-sm font-semibold text-slate-950 dark:text-white">{{ card.definition.label }}</div>
              <div class="mt-2 flex items-center justify-between gap-3">
                <span class="text-xs text-stone-500 dark:text-slate-500">{{ card.freshness }}</span>
                <span :class="['data-lag-pill', lagClass(card.dataLagDays)]">{{ card.dataLagLabel }}</span>
              </div>
            </div>
          </div>
        </section>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import MacroSparkline from '@/components/market/MacroSparkline.vue'
import { useTheme } from '@/composables/useTheme'
import { formatPercentile, formatSignedNumber } from '@/modules/format'
import { useMacroLiquidityPage, type MacroMetricCard } from '@/modules/market'
import { macroPressureClass, macroScoreToneClass } from '@/modules/market/macroLiquidityPresentation'

const lookbackDays = 365
const { t } = useI18n()
const changeDays = ref(30)
const { theme } = useTheme()
const {
  loading,
  error,
  score,
  rawScore,
  scorePercentile,
  scoreLabel,
  scoreTone,
  cards,
  groups,
  drivers,
  alerts,
  lastUpdated,
  changeWindowLabel,
  load,
  refresh,
} = useMacroLiquidityPage(lookbackDays, changeDays)

const clampPercent = (value: number) => Math.max(0, Math.min(100, value))
const scorePercentilePosition = computed(() => clampPercent(scorePercentile.value ?? score.value ?? 0))
const statusPercentileLabel = computed(() => (
  scorePercentile.value === null ? '--' : `P${Math.round(scorePercentile.value)}`
))
const scoreToneClass = computed(() => macroScoreToneClass(scoreTone.value))

const toneClass = (tone: MacroMetricCard['tone']) => {
  if (tone === 'support') return 'border-[#b8d2c4] bg-[#edf3ee] text-[#0f6b4f] dark:border-emerald-400/40 dark:bg-emerald-400/10 dark:text-emerald-300'
  if (tone === 'pressure') return 'border-[#efc4b5] bg-[#fff3ed] text-[#c84c28] dark:border-orange-400/40 dark:bg-orange-400/10 dark:text-orange-300'
  return 'border-stone-200 bg-stone-100 text-stone-600 dark:border-slate-600 dark:bg-slate-800/70 dark:text-slate-300'
}

const sparkColor = (tone: MacroMetricCard['tone']) => {
  if (tone === 'support') return theme.value === 'dark' ? '#34d399' : '#1d6fba'
  if (tone === 'pressure') return theme.value === 'dark' ? '#fb923c' : '#c84c28'
  return theme.value === 'dark' ? '#38bdf8' : '#8a6a24'
}

const formatWeight = (value: number) => `${value.toFixed(2)}%`
const pressureClass = macroPressureClass
const lagClass = (value: number | null) => {
  if (typeof value !== 'number') return 'data-lag-pill--stale'
  if (value <= 3) return 'data-lag-pill--fresh'
  if (value <= 14) return 'data-lag-pill--normal'
  return 'data-lag-pill--stale'
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.macro-page {
  background: #f7f4ed;
}

.macro-page--dark {
  background:
    radial-gradient(circle at top left, rgba(8, 145, 178, 0.16), transparent 34rem),
    linear-gradient(180deg, #020713 0%, #030816 52%, #020617 100%);
}

.metric-card,
.macro-panel {
  border: 1px solid #e4ded3;
  background: rgba(255, 255, 255, 0.88);
}

.macro-page--dark .metric-card,
.macro-page--dark .macro-panel {
  border-color: rgba(30, 41, 59, 0.95);
  background: rgba(2, 6, 23, 0.72);
}

.macro-kicker {
  border: 1px solid #cfded4;
  background: #edf3ee;
  color: #0f6b4f;
}

.macro-page--dark .macro-kicker {
  border-color: rgba(52, 211, 153, 0.3);
  background: rgba(52, 211, 153, 0.1);
  color: #6ee7b7;
}

.macro-title {
  color: #14110f;
  font-family: Georgia, "Times New Roman", serif;
  letter-spacing: 0;
}

.macro-page--dark .macro-title {
  color: #ffffff;
}

.score-summary-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 0.75rem;
}

.score-summary-card {
  border: 1px solid #eee7dc;
  background: #fbfaf7;
  padding: 0.7rem 0.8rem;
  min-width: 0;
}

.macro-page--dark .score-summary-card {
  border-color: rgba(30, 41, 59, 0.75);
  background: rgba(15, 23, 42, 0.32);
}

.score-summary-card span {
  display: block;
  font-size: 0.68rem;
  color: #78716c;
}

.macro-page--dark .score-summary-card span {
  color: #94a3b8;
}

.score-summary-card strong {
  margin-top: 0.35rem;
  display: block;
  font-size: 0.95rem;
}

.score-summary-card--primary strong {
  font-size: 2rem;
  line-height: 1;
}

.score-summary-card em {
  display: block;
  margin-top: 0.35rem;
  color: #78716c;
  font-size: 0.78rem;
  font-style: normal;
}

.macro-page--dark .score-summary-card em {
  color: #94a3b8;
}

@media (max-width: 640px) {
  .score-summary-grid {
    grid-template-columns: 1fr;
  }
}

.score-scale-track {
  position: relative;
  height: 0.9rem;
  overflow: visible;
  background: #e7e3dd;
}

.macro-page--dark .score-scale-track {
  background: #1e293b;
}

.score-scale-zone,
.score-scale-split,
.score-scale-marker {
  position: absolute;
  top: 0;
  bottom: 0;
}

.score-scale-zone--tight {
  left: 0;
  width: 20%;
  background: #0f6b4f;
}

.score-scale-zone--neutral-tight {
  left: 20%;
  width: 30%;
  background: #8a8f56;
}

.score-scale-zone--neutral-loose {
  left: 50%;
  width: 30%;
  background: #c9873a;
}

.score-scale-zone--loose {
  left: 80%;
  width: 20%;
  background: #c84c28;
}

.score-scale-split {
  width: 1px;
  background: rgba(255, 255, 255, 0.8);
}

.score-scale-marker {
  width: 2px;
  transform: translateX(-1px);
  background: #111827;
}

.score-scale-marker::after {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 0.9rem;
  height: 0.9rem;
  border: 2px solid #ffffff;
  background: #111827;
  content: "";
  transform: translate(-50%, -50%);
}

.macro-page--dark .score-scale-marker,
.macro-page--dark .score-scale-marker::after {
  background: #f8fafc;
}

.score-scale-labels {
  display: grid;
  grid-template-columns: 20fr 30fr 30fr 20fr;
  gap: 0.75rem;
  margin-top: 0.75rem;
  color: #64748b;
  font-size: 0.75rem;
  text-align: center;
}

.score-scale-labels strong,
.score-scale-labels span {
  display: block;
  min-width: 0;
}

.score-scale-labels strong {
  color: #334155;
  font-weight: 700;
}

.score-scale-labels span {
  margin-top: 0.15rem;
  color: #94a3b8;
}

.macro-page--dark .score-scale-labels strong {
  color: #cbd5e1;
}

@media (max-width: 640px) {
  .score-scale-labels {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.macro-primary-button,
.macro-secondary-button,
.macro-period-select {
  border: 1px solid #0f6b4f;
  padding: 0.65rem 0.95rem;
  font-size: 0.82rem;
  font-weight: 700;
  transition: background-color 0.18s ease, border-color 0.18s ease;
}

.macro-primary-button {
  background: #0f6b4f;
  color: #ffffff;
}

.macro-primary-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.macro-secondary-button,
.macro-period-select {
  background: #ffffff;
  color: #0f6b4f;
}

.macro-period-select:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.macro-page--dark .macro-secondary-button {
  background: rgba(15, 23, 42, 0.65);
  color: #cbd5e1;
}

.macro-page--dark .macro-period-select {
  background: rgba(15, 23, 42, 0.65);
  color: #cbd5e1;
}

.metric-card {
  padding: 1rem;
}

.metric-card {
  min-height: 17rem;
}

.change-pill {
  flex-shrink: 0;
  border-width: 1px;
  padding: 0.18rem 0.4rem;
  font-size: 0.68rem;
  font-weight: 700;
}

.panel-kicker {
  color: #0f6b4f;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.macro-page--dark .panel-kicker {
  color: #34d399;
}

.driver-row {
  border: 1px solid #eee7dc;
  background: #fbfaf7;
  padding: 0.7rem;
}

.macro-page--dark .driver-row {
  border-color: rgba(30, 41, 59, 0.75);
  background: rgba(15, 23, 42, 0.32);
}

.diagnostic-table-head {
  background: rgba(237, 243, 238, 0.9);
  color: #0f172a;
}

.macro-page--dark .diagnostic-table-head {
  background: rgba(15, 23, 42, 0.86);
  color: #e2e8f0;
}

.diagnostic-table-row {
  border-top: 1px solid #eee7dc;
}

.macro-page--dark .diagnostic-table-row {
  border-color: rgba(30, 41, 59, 0.75);
}

.source-status-card {
  border: 1px solid #eee7dc;
  background: #fbfaf7;
  padding: 0.8rem;
}

.macro-page--dark .source-status-card {
  border-color: rgba(30, 41, 59, 0.75);
  background: rgba(15, 23, 42, 0.32);
}

.data-lag-pill {
  display: inline-flex;
  align-items: center;
  border-width: 1px;
  padding: 0.15rem 0.4rem;
  font-size: 0.68rem;
  font-weight: 700;
  white-space: nowrap;
}

.data-lag-pill--fresh {
  border-color: #b8d2c4;
  background: #edf3ee;
  color: #0f6b4f;
}

.data-lag-pill--normal {
  border-color: #e4d2a3;
  background: #fbf7e9;
  color: #8a6a24;
}

.data-lag-pill--stale {
  border-color: #efc4b5;
  background: #fff3ed;
  color: #c84c28;
}

.macro-page--dark .data-lag-pill--fresh {
  border-color: rgba(52, 211, 153, 0.35);
  background: rgba(52, 211, 153, 0.1);
  color: #6ee7b7;
}

.macro-page--dark .data-lag-pill--normal {
  border-color: rgba(251, 191, 36, 0.35);
  background: rgba(251, 191, 36, 0.1);
  color: #fcd34d;
}

.macro-page--dark .data-lag-pill--stale {
  border-color: rgba(251, 146, 60, 0.35);
  background: rgba(251, 146, 60, 0.1);
  color: #fdba74;
}
</style>
