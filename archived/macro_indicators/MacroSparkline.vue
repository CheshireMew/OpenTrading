<template>
  <div ref="chartContainer" class="macro-sparkline" :style="{ height }"></div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { useTheme } from '@/composables/useTheme'

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, CanvasRenderer])

interface SparklinePoint {
  date: string
  value: number
}

const props = withDefaults(defineProps<{
  history?: SparklinePoint[]
  color?: string
  height?: string
  mode?: 'line' | 'bar'
}>(), {
  history: () => [],
  color: '#22d3ee',
  height: '92px',
  mode: 'line',
})

const points = computed(() => props.history.filter((item) => typeof item.value === 'number'))
const { theme } = useTheme()

const option = () => {
  const labels = points.value.map((item) => item.date.slice(0, 10))
  const values = points.value.map((item) => item.value)
  const isDark = theme.value === 'dark'
  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      backgroundColor: isDark ? 'rgba(3, 7, 18, 0.95)' : 'rgba(255, 255, 255, 0.98)',
      borderColor: isDark ? 'rgba(148, 163, 184, 0.3)' : 'rgba(203, 213, 225, 0.95)',
      textStyle: { color: isDark ? '#e5e7eb' : '#0f172a', fontSize: 11 },
      valueFormatter: (value: number) => Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 }),
    },
    grid: { left: 2, right: 2, top: 6, bottom: 2 },
    xAxis: {
      type: 'category',
      data: labels,
      boundaryGap: props.mode === 'bar',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: true, lineStyle: { color: isDark ? 'rgba(51, 65, 85, 0.45)' : 'rgba(203, 213, 225, 0.72)' } },
    },
    series: [{
      type: props.mode,
      data: values,
      smooth: true,
      showSymbol: false,
      barWidth: '55%',
      itemStyle: { color: props.color },
      lineStyle: { width: 2, color: props.color },
      areaStyle: props.mode === 'line' ? {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: `${props.color}55` },
          { offset: 1, color: `${props.color}00` },
        ]),
      } : undefined,
    }],
  }
}

const { chartContainer, renderChart } = useEcharts(option)

watch(() => [props.history, props.color, props.mode, theme.value], () => {
  renderChart()
}, { deep: true })
</script>

<style scoped>
.macro-sparkline {
  width: 100%;
  min-width: 0;
}
</style>
