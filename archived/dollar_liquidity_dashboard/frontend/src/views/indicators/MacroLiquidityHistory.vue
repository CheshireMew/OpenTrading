<template>
  <div class="macro-detail-page min-h-full overflow-y-auto text-slate-900 dark:text-slate-100">
    <section class="flex w-full flex-col gap-6 px-3 py-5 sm:px-4 lg:px-5 xl:px-6">
      <div class="flex flex-col gap-4 border-b border-stone-200 pb-5 dark:border-slate-800 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <RouterLink class="detail-back-link" :to="{ name: 'IndicatorsMacro' }">{{ t('macro.back') }}</RouterLink>
          <p class="detail-kicker mt-4">{{ t('macro.history') }}</p>
          <h1 class="detail-title mt-2">{{ t('macro.historyTitle') }}</h1>
          <p class="mt-3 max-w-3xl text-sm leading-6 text-stone-600 dark:text-slate-400">
            {{ t('macro.historyDescription') }}
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <select v-model.number="pageDays" class="detail-select" :aria-label="t('macro.historyRange')">
            <option :value="365">{{ t('macro.recentYears', { count: 1 }) }}</option>
            <option :value="1095">{{ t('macro.recentYears', { count: 3 }) }}</option>
            <option :value="1825">{{ t('macro.recentYears', { count: 5 }) }}</option>
          </select>
          <button class="detail-primary-button" :disabled="loading" @click="refresh">
            {{ loading ? t('macro.refreshing') : t('macro.refreshData') }}
          </button>
        </div>
      </div>

      <div v-if="error" class="border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-950/40 dark:text-red-200">
        {{ error }}
      </div>

      <section class="detail-panel p-5">
        <div class="mb-5 grid gap-3 md:grid-cols-4">
          <div class="detail-stat">
            <span>{{ t('macro.currentStatus') }}</span>
            <strong :class="scoreToneClass">{{ scoreLabel }}</strong>
          </div>
          <div class="detail-stat">
            <span>{{ t('macro.currentScore') }}</span>
            <strong>{{ score === null ? '--' : score }}</strong>
          </div>
          <div class="detail-stat">
            <span>{{ t('macro.dataCoverage') }}</span>
            <strong>{{ coverageLabel }}</strong>
          </div>
          <div class="detail-stat">
            <span>{{ t('macro.lastUpdated') }}</span>
            <strong>{{ lastUpdated }}</strong>
          </div>
        </div>

        <div class="chart-frame">
          <div ref="chartContainer" class="h-[420px] w-full"></div>
        </div>
      </section>

      <section class="grid gap-4 lg:grid-cols-4">
        <article v-for="regime in regimes" :key="regime.title" class="detail-panel p-4">
          <div class="detail-regime-swatch" :style="{ background: regime.color }"></div>
          <h2 class="mt-3 text-base font-semibold text-slate-950 dark:text-white">{{ regime.title }}</h2>
          <p class="mt-1 text-sm text-stone-500 dark:text-slate-400">{{ regime.range }}</p>
          <p class="mt-3 text-xs leading-5 text-stone-600 dark:text-slate-400">{{ regime.description }}</p>
        </article>
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { useTheme } from '@/composables/useTheme'
import { useMacroLiquidityPage } from '@/modules/market'
import { macroScoreToneClass, macroThresholdValues, useMacroRegimes } from '@/modules/market/macroLiquidityPresentation'

echarts.use([LineChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])

const pageDays = ref(1825)
const { t } = useI18n()
const { theme } = useTheme()
const {
  dli,
  loading,
  error,
  score,
  scoreLabel,
  scoreTone,
  thresholds,
  lastUpdated,
  load,
  refresh,
} = useMacroLiquidityPage(pageDays)

const coverageLabel = computed(() => {
  const value = dli.value?.coverage
  return typeof value === 'number' ? `${value.toFixed(1)}%` : '--'
})

const scoreToneClass = computed(() => macroScoreToneClass(scoreTone.value))

const historyPoints = computed(() => dli.value?.history || [])
const thresholdValues = computed(() => macroThresholdValues(thresholds.value))
const regimes = useMacroRegimes(thresholds)

const buildChartOption = () => {
  const isDark = theme.value === 'dark'
  const labels = historyPoints.value.map((item) => item.date.slice(0, 10))
  const scores = historyPoints.value.map((item) => item.score)
  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      backgroundColor: isDark ? 'rgba(3, 7, 18, 0.95)' : 'rgba(255, 255, 255, 0.98)',
      borderColor: isDark ? 'rgba(148, 163, 184, 0.3)' : 'rgba(203, 213, 225, 0.95)',
      textStyle: { color: isDark ? '#e5e7eb' : '#0f172a', fontSize: 12 },
      valueFormatter: (value: number) => `${Number(value).toFixed(2)} / 100`,
    },
    grid: { left: 42, right: 24, top: 28, bottom: 34 },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: false,
      axisLine: { lineStyle: { color: isDark ? '#334155' : '#d6d3d1' } },
      axisLabel: { color: isDark ? '#94a3b8' : '#78716c' },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: isDark ? '#94a3b8' : '#78716c' },
      splitLine: { lineStyle: { color: isDark ? 'rgba(51, 65, 85, 0.65)' : 'rgba(214, 211, 209, 0.78)' } },
    },
    series: [{
      name: t('macro.dliScore'),
      type: 'line',
      data: scores,
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 3, color: '#0f6b4f' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(15, 107, 79, 0.24)' },
          { offset: 1, color: 'rgba(15, 107, 79, 0)' },
        ]),
      },
      markLine: {
        symbol: 'none',
        label: { color: isDark ? '#cbd5e1' : '#475569', formatter: '{b}' },
        lineStyle: { type: 'dashed', color: isDark ? '#64748b' : '#94a3b8' },
        data: [
          { yAxis: thresholdValues.value.p20, name: 'P20' },
          { yAxis: thresholdValues.value.p50, name: 'P50' },
          { yAxis: thresholdValues.value.p80, name: 'P80' },
        ],
      },
    }],
  }
}

const { chartContainer, renderChart } = useEcharts(buildChartOption)

watch([historyPoints, thresholds, theme], () => {
  renderChart()
}, { deep: true })

watch(pageDays, () => {
  load()
})

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

.detail-panel {
  border: 1px solid #e4ded3;
  background: rgba(255, 255, 255, 0.88);
}

.dark .detail-panel {
  border-color: rgba(30, 41, 59, 0.95);
  background: rgba(2, 6, 23, 0.72);
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
.detail-select {
  border: 1px solid #0f6b4f;
  padding: 0.65rem 0.95rem;
  font-size: 0.82rem;
  font-weight: 700;
}

.detail-back-link,
.detail-select {
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

.chart-frame,
.detail-stat {
  border: 1px solid #eee7dc;
  background: #fbfaf7;
}

.dark .chart-frame,
.dark .detail-stat {
  border-color: rgba(30, 41, 59, 0.75);
  background: rgba(15, 23, 42, 0.32);
}

.detail-stat {
  padding: 0.75rem 0.85rem;
}

.detail-stat span {
  display: block;
  font-size: 0.68rem;
  color: #78716c;
}

.detail-stat strong {
  display: block;
  margin-top: 0.35rem;
  font-size: 1rem;
}

.detail-regime-swatch {
  height: 0.35rem;
  width: 3rem;
}
</style>
