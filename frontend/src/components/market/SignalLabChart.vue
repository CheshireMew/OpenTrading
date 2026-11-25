<template>
  <div class="interactive-chart"><ChartNavigation :controller="navigation" /><div ref="chartContainer" class="signal-chart" role="img" :aria-label="label" /></div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import ChartNavigation from '@/components/ChartNavigation.vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { useTheme } from '@/composables/useTheme'
import { useDateTime } from '@/composables/useDateTime'
import { DARK_PALETTE, LIGHT_PALETTE } from '@/theme/palette.mjs'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, CanvasRenderer])
const props = defineProps<{
  label: string
  dates: string[]
  series: { name: string; values: (number | null)[] }[]
  max?: number
  min?: number
  thresholds?: number[]
  timeOfDay?: boolean
}>()
const { theme } = useTheme()
const { locale } = useI18n()
const { timezone, formatDateTime } = useDateTime()
const dateLabel = (value: string) => props.timeOfDay
  ? formatDateTime(value, { year:undefined, month:'2-digit', day:'2-digit', hour12:false })
  : /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : value
const { chartContainer, renderChart, navigation } = useEcharts(() => {
  const palette = theme.value === 'dark' ? DARK_PALETTE : LIGHT_PALETTE
  return {
    animation: false,
    color: [palette.accent, palette.positive, palette.negative, palette.muted],
    legend: { show: props.series.length > 1, type: 'scroll', top: 0, left: 'center', padding: 0, textStyle: { color: palette.text }, pageTextStyle: { color: palette.text } },
    tooltip: { trigger: 'axis', renderMode: 'richText' },
    grid: { top: props.series.length > 1 ? 42 : 12, bottom: 34, left: 12, right: 16, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: props.dates,
      axisPointer: { label: { formatter: ({ value }: { value: string }) => props.timeOfDay ? formatDateTime(value) : dateLabel(value) } },
      axisLabel: { formatter: dateLabel, hideOverlap: true, color: palette.muted, margin: 12 } },
    yAxis: { type: 'value', scale: props.max === undefined, min:props.min, max: props.max, splitLine: { lineStyle: { color: palette.grid } }, axisLabel: { color: palette.muted } },
    series: props.series.map((line, index) => ({
      name: line.name, type: 'line', showSymbol: false, sampling: 'lttb', data: line.values,
      lineStyle: { width: index === 0 ? 2 : 1 },
      ...(index === 0 ? { areaStyle: { opacity: 0.06 } } : {}),
      ...(index===0&&props.thresholds?.length?{markLine:{symbol:'none',silent:true,label:{show:false},lineStyle:{color:palette.muted,type:'dashed',opacity:.5},data:props.thresholds.map(value=>({yAxis:value}))}}:{}),
    })),
  }
})
watch([() => props.dates, () => props.series, theme, locale, timezone], renderChart)
</script>

<style scoped>
.signal-chart { min-width: 0; width: 100%; height: min(clamp(245px, 42vh, 410px), calc(100dvh - 100px)); }
</style>
