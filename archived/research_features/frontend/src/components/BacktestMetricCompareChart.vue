<template>
  <div ref="chartContainer" class="h-full w-full"></div>
</template>

<script setup>
import { watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { categoryAxis, chartGrid, valueAxis } from '@/components/chartOptions'

echarts.use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  categories: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  dark: { type: Boolean, default: false },
})

const { chartContainer, renderChart } = useEcharts(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: {
      top: 0,
      textStyle: { color: props.dark ? '#d1d5db' : '#374151' },
    },
    grid: chartGrid({ top: 36 }),
    xAxis: categoryAxis(props.dark, props.categories),
    yAxis: valueAxis(props.dark),
    series: props.series.map((item) => ({
      type: 'bar',
      name: item.name,
      data: item.data,
      itemStyle: { color: item.color },
      barMaxWidth: 26,
    })),
  }))

watch(() => [props.categories, props.series, props.dark], renderChart, { deep: true })
</script>
