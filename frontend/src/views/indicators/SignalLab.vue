<template>
  <section class="liquidity-page" :class="{ 'liquidity-page--embedded': embedded }" :aria-label="t('nav.signalLab')">
    <header class="liquidity-header">
      <div v-if="!embedded"><p class="eyebrow">{{ t('signalLab.pageKicker') }}</p><h1>{{ t('nav.signalLab') }}</h1></div>
      <div class="header-actions">
        <span class="date-pill">{{ today }}</span>
        <button type="button" class="liquidity-button" :disabled="loading || refreshing" @click="loadLiquidity">{{ t('signalLab.reload') }}</button>
      </div>
    </header>
    <div class="liquidity-content">
      <div class="section-lead">
        <p>{{ t('signalLab.intro') }}</p>
        <div class="toolbar">
          <div class="toolbar-control">
            <span>{{ t('signalLab.historyRange') }}</span>
            <div class="segmented" role="group" :aria-label="t('signalLab.historyRange')">
              <button v-for="period in periods" :key="period" type="button" :aria-pressed="days === period"
                      :disabled="refreshing" @click="days = period">{{ t(`signalLab.range${period}`) }}</button>
            </div>
          </div>
          <div class="toolbar-control">
            <span>{{ t('signalLab.changeWindow') }}</span>
            <div class="segmented" role="group" :aria-label="t('signalLab.changeWindow')">
              <button v-for="period in windows" :key="period" type="button" :aria-pressed="changeDays === period"
                      :disabled="refreshing" @click="changeDays = period">{{ t('signalLab.days', { count: period }) }}</button>
            </div>
          </div>
          <button v-if="!PUBLIC_SITE" class="liquidity-button primary" type="button" :disabled="refreshing" @click="refreshLiquidity">
            {{ t(refreshing ? 'signalLab.refreshing' : 'signalLab.refresh') }}
          </button>
        </div>
      </div>

      <div v-if="liquidityError" class="notice error" role="alert">
        <strong>{{ t('signalLab.readError') }}</strong>
        <span>{{ liquidityError }}</span>
        <button type="button" class="liquidity-button" @click="loadLiquidity">{{ t('common.retry') }}</button>
      </div>
      <div v-else class="notice" :class="status.tone" role="status" aria-live="polite">{{ status.text }}</div>

      <div v-if="liquidity" class="content-grid">
        <article class="panel score-panel">
          <p class="eyebrow">{{ t('signalLab.currentRegime') }}</p>
          <div class="gauge" :style="{ '--score': liquidity.score ?? 0, '--gauge-color': pressureColor(liquidity.score) }">
            <div class="gauge-value">{{ n(liquidity.score, 0) }}<small>/100</small></div>
          </div>
          <strong class="score-state" :class="{ pressure: liquidity.tone === 'pressure' }">{{ backendText(liquidity.state) }}</strong>
          <p class="muted">{{ t('signalLab.scoreDirection') }}</p>
          <dl class="score-meta">
            <div><dt>{{ t('signalLab.coverage') }}</dt><dd>{{ pct(liquidity.coverage) }}</dd></div>
            <div><dt>{{ t('signalLab.rawScore') }}</dt><dd>{{ n(liquidity.raw_score) }}</dd></div>
            <div><dt>{{ t('signalLab.historySample') }}</dt><dd>{{ t('signalLab.weeks', { count: n(liquidity.thresholds.sample_size, 0) }) }}</dd></div>
            <div><dt>{{ t('signalLab.changeWindow') }}</dt><dd>{{ t('signalLab.days', { count: changeDays }) }}</dd></div>
          </dl>
        </article>

        <article class="panel history-panel">
          <div class="panel-head">
            <div><p class="eyebrow">{{ t('signalLab.pressureKicker') }}</p><h2>{{ t('signalLab.pressureHistory') }}</h2></div>
            <span class="legend"><i></i>{{ t('signalLab.pressure') }}</span>
          </div>
          <div ref="chartContainer">
            <svg v-if="chart" class="pressure-chart" :viewBox="`0 0 ${chart.width} ${chart.height}`"
                 role="img" :aria-label="t('signalLab.pressureHistory')">
              <g v-for="tick in chart.yTicks" :key="tick.value">
                <line :class="tick.threshold ? 'chart-threshold' : 'chart-grid'"
                      :x1="chart.left" :x2="chart.right" :y1="tick.y" :y2="tick.y" />
                <text :x="chart.left - 8" :y="tick.y + 3" text-anchor="end">{{ tick.value }}</text>
              </g>
              <path class="chart-area" :d="chart.area" />
              <path class="chart-line" :d="chart.path" />
              <circle class="chart-latest" :cx="chart.latest.x" :cy="chart.latest.y" r="4" />
              <text v-for="tick in chart.xTicks" :key="tick.index" :x="tick.x" :y="chart.height - 7"
                    :text-anchor="tick.anchor">{{ tick.date }}</text>
            </svg>
            <p v-else class="empty">{{ t('signalLab.noPressure') }}</p>
          </div>
        </article>

        <article class="panel wide">
          <div class="panel-head">
            <div><p class="eyebrow">{{ t('signalLab.driversKicker') }}</p><h2>{{ t('signalLab.drivers') }}</h2></div>
            <span class="muted">{{ liquidity.updated_at ? t('signalLab.lastObserved', { date: dateText(liquidity.updated_at) }) : t('signalLab.noObservation') }}</span>
          </div>
          <ol v-if="liquidity.alerts.length" class="driver-grid">
            <li v-for="(alert, index) in liquidity.alerts" :key="alert" class="driver">
              <span aria-hidden="true">{{ index + 1 }}</span>{{ backendText(alert) }}
            </li>
          </ol>
          <p v-else class="empty">{{ t('signalLab.noDrivers') }}</p>
        </article>

        <article class="panel wide">
          <div class="panel-head">
            <div><p class="eyebrow">{{ t('signalLab.indicatorsKicker') }}</p><h2>{{ t('signalLab.indicators') }}</h2></div>
            <span class="muted">{{ t('signalLab.pressureScale') }}</span>
          </div>
          <div class="indicator-scroll">
            <table class="indicator-table" :aria-label="t('signalLab.indicators')">
              <colgroup><col v-for="column in columns" :key="column" :class="`col-${column}`"></colgroup>
              <thead class="sr-only"><tr><th v-for="column in columns" :key="column" scope="col">{{ t(`signalLab.${column}`) }}</th></tr></thead>
              <tbody v-for="group in indicatorGroups" :key="group.label" class="indicator-group">
                <tr class="indicator-group-row">
                  <th :colspan="columns.length" scope="rowgroup"><strong>{{ backendText(group.label) }}</strong><span>{{ backendText(group.description) }}</span></th>
                </tr>
                <tr class="indicator-column-head" aria-hidden="true">
                  <th v-for="column in columns" :key="column">{{ t(`signalLab.${column}`) }}</th>
                </tr>
                <tr v-for="{ item, component, spark } in group.rows" :key="item.indicator_id" class="indicator-row">
                  <td class="indicator-name" :data-label="t('signalLab.indicator')"><strong>{{ backendText(item.name) }}</strong><small>{{ backendText(item.description) }}</small></td>
                  <td :data-label="t('signalLab.value')">{{ n(item.current_value) }} <small v-if="item.current_value !== null">{{ backendText(item.unit) }}</small></td>
                  <td :data-label="t('signalLab.trend')">
                    <svg v-if="spark" class="spark" viewBox="0 0 76 24" role="img" :aria-label="`${backendText(item.name)} · ${t('signalLab.trend')}`"><path :d="spark" /></svg>
                    <span v-else>—</span>
                  </td>
                  <td :data-label="t('signalLab.pressureScore')">
                    <span v-if="component?.score != null" class="pressure-bar"
                          :style="{ '--pressure': component.score + '%', '--bar-color': pressureColor(component.score) }">
                      <i aria-hidden="true"></i><b>{{ n(component.score, 0) }}</b>
                    </span>
                    <span v-else>—</span>
                  </td>
                  <td :data-label="t('signalLab.pressureZ')">{{ signed(component?.z_score) }}</td>
                  <td :data-label="t('signalLab.percentile')">{{ pct(component?.percentile) }}</td>
                  <td :data-label="t('signalLab.weight')">{{ item.is_scored ? pct(component?.effective_weight) : t('signalLab.observationOnly') }}</td>
                  <td :data-label="t('signalLab.contribution')">{{ signed(component?.contribution, 3) }}</td>
                  <td :data-label="t('signalLab.date')">
                    <span class="lag" :class="{ stale: item.is_stale }">{{ item.last_updated ? dateText(item.last_updated) : t('signalLab.noData') }}<template v-if="item.data_lag_days !== null"> · {{ t('signalLab.lagDays', { count: item.data_lag_days }) }}</template></span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel wide methodology">
          <div><p class="eyebrow">{{ t('signalLab.methodKicker') }}</p><h2>{{ t('signalLab.methodTitle') }}</h2></div>
          <div class="method-grid">
            <div v-for="step in methodSteps" :key="step"><strong>{{ t(`signalLab.method${step}`) }}</strong><p>{{ t(`signalLab.method${step}Body`) }}</p></div>
          </div>
          <p class="scope-note"><strong>{{ t('signalLab.scope') }}</strong> {{ backendText(liquidity.data_scope_note) }}</p>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiGet, apiPost } from '@/api/request'
import { PUBLIC_SITE } from '@/app/publicSite'
import { useDateTime } from '@/composables/useDateTime'
import { backendText } from '@/i18n/backendText'
import type { SignalLabIndicator, SignalLabLiquidityResponse, SignalLabPoint, SignalLabPressureComponent } from '@/modules/market/contracts'
import { useSignalResource } from '@/modules/market/signalLab'

defineProps<{ embedded?: boolean }>()

const { t, locale } = useI18n()
const { formatDate } = useDateTime()
const today = computed(() => formatDate(new Date(), { weekday: 'short', month: 'long' }))
const periods = [180, 365, 1095, 1825]
const windows = [7, 30, 90]
const columns = ['indicator', 'value', 'trend', 'pressureScore', 'pressureZ', 'percentile', 'weight', 'contribution', 'date']
const methodSteps = ['Direction', 'Normalize', 'Weight', 'Rank']
const days = ref(365)
const changeDays = ref(30)
const refreshing = ref(false)
const refreshSummary = ref<{ series: number; rows: number }>()
const { data: liquidity, loading, error: liquidityError, load } = useSignalResource<SignalLabLiquidityResponse>()

const dateText = (value: string) => {
  const date = value.slice(0, 10)
  return locale.value === 'zh-CN' ? date.replace(/-/g, '/') : date
}
const n = (value: number | null | undefined, decimals = 2) => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString(locale.value, { maximumFractionDigits: decimals })
  : '—'
const pct = (value: number | null | undefined) => value == null ? '—' : `${n(value, 1)}%`
const signed = (value: number | null | undefined, decimals = 2) => value != null && value > 0 ? `+${n(value, decimals)}` : n(value, decimals)

function pressureColor(value: number | null): string {
  const thresholds = liquidity.value?.thresholds
  if (value === null || !thresholds) return 'var(--liquidity-neutral)'
  if (value >= thresholds.p80) return 'var(--liquidity-red)'
  if (value >= thresholds.p50) return 'var(--liquidity-amber)'
  return 'var(--liquidity-green)'
}

function fetchLiquidity(signal: AbortSignal) {
  return apiGet('signal_lab_liquidity', { signal, query: { days: days.value, change_days: changeDays.value } })
}

function loadLiquidity() {
  refreshSummary.value = undefined
  return load(fetchLiquidity)
}

async function refreshLiquidity() {
  if (PUBLIC_SITE) return loadLiquidity()
  refreshing.value = true
  refreshSummary.value = undefined
  try {
    await load(async signal => {
      const updated = await apiPost('refresh_signal_lab_liquidity', {}, { signal, client: 'longTask' })
      const result = days.value === 365 && changeDays.value === 30 ? updated.liquidity : await fetchLiquidity(signal)
      if (!signal.aborted) {
        refreshSummary.value = { series: updated.refresh.series_count, rows: updated.refresh.row_count }
      }
      return result
    })
  } finally {
    refreshing.value = false
  }
}

watch([days, changeDays], loadLiquidity, { immediate: true })

const status = computed(() => {
  if (refreshing.value) return { tone: 'info', text: t('signalLab.refreshingNote') }
  if (loading.value || !liquidity.value) return { tone: 'info', text: t('signalLab.loading') }
  if (refreshSummary.value) {
    const { series, rows } = refreshSummary.value
    return { tone: 'success', text: t('signalLab.refreshed', { series: n(series, 0), rows: n(rows, 0) }) }
  }
  return liquidity.value.score === null
    ? { tone: 'warning', text: t('signalLab.noScore') }
    : { tone: 'success', text: t('signalLab.scoreCoverage', { coverage: n(liquidity.value.coverage, 1) }) }
})

function miniChartPath(history: SignalLabPoint[]): string {
  const values = history.slice(-50).map(point => point.value)
  if (values.length < 2) return ''
  const minimum = Math.min(...values)
  const range = Math.max(...values) - minimum || 1
  return values.map((value, index) =>
    `${index === 0 ? 'M' : 'L'}${(index * 74 / (values.length - 1)).toFixed(1)},${(22 - (value - minimum) * 20 / range).toFixed(1)}`,
  ).join(' ')
}

const indicatorGroups = computed(() => {
  const groups = new Map<string, {
    label: string
    description: string
    rows: { item: SignalLabIndicator; component?: SignalLabPressureComponent; spark: string }[]
  }>()
  const byIndicator = new Map(liquidity.value?.components.map(item => [item.indicator_id, item]))
  for (const item of liquidity.value?.indicators ?? []) {
    let group = groups.get(item.group_label)
    if (!group) {
      group = { label: item.group_label, description: item.group_description, rows: [] }
      groups.set(item.group_label, group)
    }
    group.rows.push({ item, component: byIndicator.get(item.indicator_id), spark: miniChartPath(item.history) })
  }
  return [...groups.values()]
})

const chartContainer = ref<HTMLElement>()
const chartWidth = ref(760)
watch(chartContainer, (element, _previous, onCleanup) => {
  if (!element) return
  const measure = () => { chartWidth.value = Math.max(300, Math.round(element.getBoundingClientRect().width)) }
  const observer = new ResizeObserver(measure)
  measure()
  observer.observe(element)
  onCleanup(() => observer.disconnect())
})

const chart = computed(() => {
  const result = liquidity.value
  if (!result?.history.length) return null
  const width = chartWidth.value
  const height = width < 520 ? 210 : 250
  const left = width < 520 ? 32 : 36
  const right = width - 12
  const bottom = height - 28
  const last = result.history.length - 1
  const x = (index: number) => left + (last ? index / last : 0.5) * (right - left)
  const y = (score: number) => 14 + (100 - score) / 100 * (bottom - 14)
  const { p20, p50, p80 } = result.thresholds
  const path = result.history.map((point, index) => `${index ? 'L' : 'M'}${x(index).toFixed(2)},${y(point.score).toFixed(2)}`).join(' ')
  return {
    width, height, left, right, path,
    area: `${path} L${x(last)},${bottom} L${x(0)},${bottom} Z`,
    latest: { x: x(last), y: y(result.history[last].score) },
    yTicks: [0, p20, p50, p80, 100].map(value => ({ value, y: y(value), threshold: value === p20 || value === p80 })),
    xTicks: [...new Set([0, Math.floor(last / 2), last])].map(index => ({
      index, x: x(index), date: dateText(result.history[index].date),
      anchor: !last ? 'middle' : index === 0 ? 'start' : index === last ? 'end' : 'middle',
    })),
  }
})
</script>

<style scoped src="./signalLabLiquidity.css"></style>
