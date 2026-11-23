<template>
  <div ref="chartContainer" class="observation-chart" :style="chartHeight ? { height: chartHeight + 'px' } : undefined" role="img" :aria-label="t('observation.chartDescription')" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, TooltipComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { useTheme } from '@/composables/useTheme'
import { DARK_PALETTE, LIGHT_PALETTE } from '@/theme/palette.mjs'
import { observationRangeStart, type ObservationRange } from '@/modules/market/assetObservation'
import type { OhlcvPointResponse } from '@/modules/market/contracts'

echarts.use([LineChart, DataZoomComponent, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer])
const props = defineProps<{ bars: OhlcvPointResponse[]; drawdowns: { timestamp: number; value: number }[]; peak: number; range: ObservationRange }>()
const { t, locale } = useI18n()
const { theme } = useTheme()
const chartHeight = ref<number>()
const { chartContainer, renderChart } = useEcharts(() => {
  const colors = theme.value === 'dark' ? DARK_PALETTE : LIGHT_PALETTE
  const start = observationRangeStart(props.bars[props.bars.length - 1]?.timestamp || 0, props.range)
  const rows = props.bars.filter(row => row.timestamp >= start)
  const drawdowns = props.drawdowns.filter(row => row.timestamp >= start)
  const axis = { color: colors.muted, fontSize: 11 }
  return {
    animation: false,
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', backgroundColor: colors.panel, borderColor: colors.border, textStyle: { color: colors.text }, valueFormatter: (value: number) => Number(value).toLocaleString(locale.value, { maximumFractionDigits: 2 }) },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [{ left: 68, right: 22, top: 20, height: '54%' }, { left: 68, right: 22, top: '69%', height: '20%' }],
    xAxis: [0, 1].map(index => ({ type: 'category', gridIndex: index, boundaryGap: false, data: rows.map(row => new Date(row.timestamp).toISOString().slice(0, 10)), axisLabel: { ...axis, show: index === 1, hideOverlap: true }, axisLine: { lineStyle: { color: colors.border } }, axisTick: { show: false } })),
    yAxis: [
      { type: 'value', scale: true, axisLabel: { ...axis, formatter: (value: number) => Intl.NumberFormat(locale.value, { notation: 'compact', maximumFractionDigits: 1 }).format(value) }, splitLine: { lineStyle: { color: colors.grid } } },
      { type: 'value', gridIndex: 1, max: 0, axisLabel: { ...axis, formatter: '{value}%' }, splitLine: { lineStyle: { color: colors.grid } } },
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], zoomOnMouseWheel: false }, { type: 'slider', xAxisIndex: [0, 1], bottom: 0, height: 16, borderColor: colors.border, textStyle: axis, dataBackground: { lineStyle: { color: colors.muted }, areaStyle: { color: colors.elevated } }, start: 0, end: 100 }],
    series: [
      { name: t('observation.dailyPrice'), type: 'line', data: rows.map(row => row.close), showSymbol: false, sampling: 'lttb', lineStyle: { width: 2, color: colors.accent }, itemStyle: { color: colors.accent }, areaStyle: { color: colors.accent, opacity: 0.06 }, markLine: { symbol: 'none', silent: true, label: { formatter: t('observation.peak'), position: 'insideEndBottom', color: colors.muted }, lineStyle: { color: colors.muted, type: 'dashed', opacity: .65 }, data: [{ yAxis: props.peak }] } },
      { name: t('observation.drawdownChart'), type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: drawdowns.map(row => Number(row.value.toFixed(4))), showSymbol: false, sampling: 'lttb', lineStyle: { width: 1.5, color: colors.negative }, itemStyle: { color: colors.negative }, areaStyle: { color: colors.negative, opacity: .12 }, tooltip: { valueFormatter: (value: number) => `${Number(value).toFixed(2)}%` } },
    ],
  }
})
let sizeObserver: ResizeObserver | undefined
let resizeFrame = 0
onMounted(() => {
  const container = chartContainer.value
  const scrollport = container?.closest<HTMLElement>('.observation-main')
  const page = container?.closest<HTMLElement>('.observation-page')
  const panel = container?.parentElement
  if (!container || !scrollport || !page || !panel) return
  const updateSize = () => {
    cancelAnimationFrame(resizeFrame)
    resizeFrame = requestAnimationFrame(() => {
      if (!container.clientWidth) return
      const top = container.getBoundingClientRect().top - scrollport.getBoundingClientRect().top + scrollport.scrollTop
      const siblings = Array.from(panel.children).slice(Array.from(panel.children).indexOf(container) + 1)
      const footerHeight = siblings.reduce((height, element) => {
        const style = getComputedStyle(element)
        return height + element.getBoundingClientRect().height + parseFloat(style.marginTop) + parseFloat(style.marginBottom)
      }, 0)
      const panelStyle = getComputedStyle(panel)
      const bottom = footerHeight + parseFloat(panelStyle.paddingBottom) + parseFloat(panelStyle.borderBottomWidth) + parseFloat(getComputedStyle(page).paddingBottom)
      const preferred = window.innerWidth <= 640 ? 350 : 430
      chartHeight.value = Math.floor(Math.min(preferred, Math.max(220, scrollport.clientHeight - top - bottom)))
    })
  }
  sizeObserver = new ResizeObserver(updateSize)
  for (const element of [container, scrollport, page, panel]) sizeObserver.observe(element)
  updateSize()
})
onBeforeUnmount(() => {
  sizeObserver?.disconnect()
  cancelAnimationFrame(resizeFrame)
})
watch([() => props.bars, () => props.drawdowns, () => props.peak, () => props.range, theme, locale], renderChart)
</script>

<style scoped>
.observation-chart { width: 100%; height: clamp(220px, calc(100dvh - 140px), 430px); }
@media (max-width: 640px) { .observation-chart { height: clamp(220px, calc(100dvh - 140px), 350px); } }
</style>
