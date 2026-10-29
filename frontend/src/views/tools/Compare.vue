<template>
  <div class="app-page">
    <div class="app-page-inner-wide flex min-h-full flex-col">
    <header class="app-workspace-header"><h1 class="app-title">{{ $t('nav.compare') }}</h1><AppLayoutSwitch v-model="pageLayout" :options="layoutOptions" /></header>
    <!-- Configuration Panel -->
    <div class="app-hero-panel flex flex-wrap items-end gap-4 transition-colors">
      <div class="flex-1 min-w-[200px]">
        <label class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('compare.symbolA') }}</label>
        <SymbolSearchBox v-model="config.symbolA" :aria-label="$t('compare.symbolA')" output-mode="base" @select="handleSymbolSelect" />
      </div>

      <div class="flex items-center justify-center p-2">
         <span class="text-stone-400 dark:text-slate-500 font-bold text-xl">VS</span>
      </div>

      <div class="flex-1 min-w-[200px]">
        <label class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('compare.symbolB') }}</label>
        <SymbolSearchBox v-model="config.symbolB" :aria-label="$t('compare.symbolB')" output-mode="base" @select="handleSymbolSelect" />
      </div>

      <div class="w-32">
        <label for="compare-timeframe" class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('compare.timeframe') }}</label>
        <select id="compare-timeframe" v-model="config.timeframe" class="app-control w-full">
          <option value="5m">{{ $t('compare.tf.5m') }}</option>
          <option value="15m">{{ $t('compare.tf.15m') }}</option>
          <option value="1h">{{ $t('compare.tf.1h') }}</option>
          <option value="4h">{{ $t('compare.tf.4h') }}</option>
          <option value="1d">{{ $t('compare.tf.1d') }}</option>
          <option value="1w">{{ $t('compare.tf.1w') }}</option>
          <option value="1M">{{ $t('compare.tf.1M') }}</option>
        </select>
      </div>

      <div class="w-32">
        <label for="compare-days" class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('compare.days') }}</label>
        <input id="compare-days" v-model.number="config.days" type="number" min="1" max="90" class="app-control w-full" />
      </div>

      <button type="button" @click="fetchComparisonData" :disabled="loading || !canCompare" class="app-button-primary app-touch-target flex items-center px-6 py-2">
        <ArrowPathIcon v-if="loading" class="h-4 w-4 animate-spin" aria-hidden="true" />
        {{ loading ? $t('compare.analyzing') : $t('compare.compare') }}
      </button>
    </div>

    <div v-if="errorMessage" role="alert" class="flex flex-wrap items-center justify-between gap-3 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
      <span>{{ errorMessage }}</span>
      <button v-if="initialized" type="button" class="app-button-secondary app-touch-target" :disabled="loading || !canCompare" @click="fetchComparisonData">{{ $t('common.retry') }}</button>
    </div>

    <section v-if="statistics" class="app-metric-strip compare-metrics">
      <article v-for="card in [
        [$t('compare.returnA'), statistics.symbol_a_return_pct],
        [$t('compare.returnB'), statistics.symbol_b_return_pct],
        [$t('compare.excessReturn'), statistics.excess_return_pct],
        [$t('compare.correlation'), statistics.return_correlation],
        [$t('compare.alignedPoints'), statistics.aligned_points],
      ]" :key="card[0]" class="py-4"><p class="text-xs app-muted">{{ card[0] }}</p><p class="app-metric-value">{{ formatStatistic(card[1]) }}</p></article>
    </section>

    <div v-if="(loading || !initialized) && !hasData" role="status" aria-live="polite" class="app-panel flex min-h-[28rem] items-center justify-center p-8 text-center app-muted">
      {{ $t('compare.loadingData') }}
    </div>

    <div v-else-if="initialized && !errorMessage && !hasData" class="app-panel flex min-h-[28rem] items-center justify-center p-8 text-center">
      <div class="max-w-md"><h2 class="app-section-title">{{ $t('compare.emptyTitle') }}</h2><p class="app-subtitle mt-2">{{ $t('compare.emptyDescription') }}</p></div>
    </div>

    <!-- Charts Grid -->
    <div v-else-if="hasData" class="compare-charts" :class="`compare-layout-${pageLayout}`">
      <label v-if="pageLayout === 'focus'" for="compare-focused-chart" class="flex items-center gap-3 text-sm">{{ $t('workspaceViews.chart') }}<select id="compare-focused-chart" v-model="focusedChart" :aria-label="$t('workspaceViews.chart')" class="app-control"><option value="ratio">{{ $t('compare.ratio') }}</option><option value="a">{{ resultSymbols.symbolA }}</option><option value="b">{{ resultSymbols.symbolB }}</option></select></label>

      <!-- Ratio Chart (Full Width) -->
      <div class="app-panel relative flex flex-col overflow-hidden transition-colors compare-ratio-chart" v-show="pageLayout !== 'focus' || focusedChart === 'ratio'">
        <div class="absolute top-2 left-2 z-10 border border-[#b8d2c4] bg-white/90 px-2 py-1 text-sm font-bold text-[#0f6b4f] dark:border-green-500/30 dark:bg-gray-900/80 dark:text-green-400">
          {{ $t('compare.ratio') }}: {{ resultSymbols.symbolA }} / {{ resultSymbols.symbolB }}
        </div>
        <TradingViewChart
          ref="chartRatioRef"
          :data="dataRatio"
          chart-type="area"
          :colors="chartColors"
        />
      </div>
<div class="compare-price-charts" v-show="pageLayout !== 'focus' || focusedChart !== 'ratio'">      <!-- Chart A -->
      <div class="app-panel relative flex flex-col overflow-hidden transition-colors" v-show="pageLayout !== 'focus' || focusedChart === 'a'">
        <div class="absolute top-2 left-2 z-10 border border-[#b8d2c4] bg-white/90 px-2 py-1 text-sm font-bold text-[#0f6b4f] dark:border-emerald-500/30 dark:bg-gray-900/80 dark:text-emerald-300">
          {{ symbolLabel(resultSymbols.symbolA) }}
        </div>
        <TradingViewChart
          ref="chartARef"
          :data="dataA"
          :colors="{ ...chartColors, upColor: '#3b82f6', downColor: '#1d4ed8' }"
        />
      </div>

      <!-- Chart B -->
      <div class="app-panel relative flex flex-col overflow-hidden transition-colors" v-show="pageLayout !== 'focus' || focusedChart === 'b'">
        <div class="absolute top-2 left-2 z-10 border border-[#efc4b5] bg-white/90 px-2 py-1 text-sm font-bold text-[#c84c28] dark:border-purple-500/30 dark:bg-gray-900/80 dark:text-purple-400">
          {{ symbolLabel(resultSymbols.symbolB) }}
        </div>
        <TradingViewChart
          ref="chartBRef"
          :data="dataB"
          :colors="{ ...chartColors, upColor: '#a855f7', downColor: '#7e22ce' }"
        />
      </div>

</div>

    </div>
    </div>
  </div>
</template>

<script setup>
import AppLayoutSwitch from "@/components/AppLayoutSwitch.vue"
import { usePageLayout } from "@/composables/usePageLayout"
import { computed, ref } from "vue"
import { useI18n } from "vue-i18n"
const formatStatistic = value => value == null ? '—' : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : value
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import TradingViewChart from '@/components/TradingViewChart.vue'
import SymbolSearchBox from '@/components/SymbolSearchBox.vue'
import { useComparePage } from '@/modules/tools'

const {
  chartColors,
  config,
  loading,
  initialized,
  errorMessage,
  hasData,
  resultSymbols,
  dataA,
  dataB,
  dataRatio,
  statistics,
  chartARef,
  chartBRef,
  chartRatioRef,
  fetchComparisonData,
  handleSymbolSelect,
  symbolLabel,
  canCompare,
} = useComparePage()

const { t } = useI18n()
const pageLayout = usePageLayout('compare', ['ratio', 'prices', 'focus'], 'ratio')
const focusedChart = ref('ratio')
const layoutOptions = computed(() => ['ratio', 'prices', 'focus'].map(value => ({ value, label: t(`workspaceViews.${value}`) })))
</script>

<style scoped>
.compare-charts { display: grid; gap: 20px; }
.compare-ratio-chart { min-height: 360px; }
.compare-price-charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.compare-price-charts > div { min-height: 300px; }
.compare-metrics { grid-template-columns: repeat(5, minmax(0, 1fr)); }
@container app-content (max-width: 48rem) { .compare-price-charts { grid-template-columns: minmax(0, 1fr); } .compare-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

.compare-layout-prices .compare-price-charts { order:-1; }
.compare-layout-prices .compare-price-charts > div { min-height:440px; }
.compare-layout-prices .compare-ratio-chart { min-height:240px; }
.compare-layout-focus .compare-price-charts { grid-template-columns:minmax(0,1fr); }
.compare-layout-focus .compare-ratio-chart,.compare-layout-focus .compare-price-charts > div { min-height:560px; }
@container app-content (max-width:48rem) { .compare-layout-focus .compare-ratio-chart,.compare-layout-focus .compare-price-charts > div { min-height:400px; } }
</style>
