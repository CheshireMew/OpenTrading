<template>
  <div ref="chartContainer" class="h-full w-full"></div>
</template>

<script setup>
import { watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { categoryAxis, chartGrid, chartTextColor, valueAxis } from '@/components/chartOptions'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  categories: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  dark: { type: Boolean, default: false },
  yAxisLabel: { type: String, default: '' },
})

const { chartContainer, renderChart } = useEcharts(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      top: 0,
      textStyle: { color: props.dark ? '#d1d5db' : '#374151' },
    },
    grid: chartGrid({ top: 40 }),
    xAxis: categoryAxis(props.dark, props.categories, { hideOverlap: true }),
    yAxis: {
      ...valueAxis(props.dark),
      name: props.yAxisLabel,
      nameTextStyle: { color: chartTextColor(props.dark), padding: [0, 0, 0, 8] },
    },
    series: props.series.map((item) => ({
      type: 'line',
      name: item.name,
      data: item.data,
      smooth: true,
      showSymbol: false,
      lineStyle: { color: item.color, width: 2 },
      itemStyle: { color: item.color },
      areaStyle: item.area ? { color: item.area } : undefined,
    })),
  }))

watch(() => [props.categories, props.series, props.dark, props.yAxisLabel], renderChart, { deep: true })
</script>
