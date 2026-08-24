<template>
  <div ref="chartContainer" class="h-full w-full"></div>
</template>

<script setup>
import { watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { categoryAxis, chartGrid, valueAxis } from '@/components/chartOptions'

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  categories: { type: Array, default: () => [] },
  values: { type: Array, default: () => [] },
  dark: { type: Boolean, default: false },
  positiveColor: { type: String, default: '#10b981' },
  negativeColor: { type: String, default: '#ef4444' },
})

const { chartContainer, renderChart } = useEcharts(() => ({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: chartGrid(),
    xAxis: categoryAxis(props.dark, props.categories),
    yAxis: valueAxis(props.dark),
    series: [
      {
        type: 'bar',
        data: props.values.map((value) => ({
          value,
          itemStyle: { color: value >= 0 ? props.positiveColor : props.negativeColor },
        })),
        barMaxWidth: 32,
      },
    ],
  }))

watch(() => [props.categories, props.values, props.dark], renderChart, { deep: true })
</script>
