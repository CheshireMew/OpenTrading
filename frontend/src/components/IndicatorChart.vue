<template>
  <div class="w-full" :class="height" ref="chartContainer"></div>
</template>

<script setup>
import { DARK_PALETTE } from '@/theme/palette.mjs'
import { watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { useTheme } from '@/composables/useTheme'
import { useDateTime } from '@/composables/useDateTime'
import { formatIndicatorAxisValue } from '@/modules/market/indicatorDisplay'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  indicator: {
    type: Object,
    required: true
  },
  height: {
    type: String,
    default: 'h-48'
  }
})

const { theme } = useTheme()
const { timezone, formatDate } = useDateTime()

const getChartOption = (indicator, isDark) => {
  const textColor = isDark ? DARK_PALETTE.muted : '#4b5563'
  const lineColor = isDark ? DARK_PALETTE.blue : '#1d6fba'
  const areaColor = isDark ? 'rgba(59, 130, 246, 0.2)' : 'rgba(29, 111, 186, 0.18)'
  const splitLineColor = isDark ? DARK_PALETTE.grid : '#e5e7eb'

  const dataDates = indicator.history.map(item => formatDate(item.date))
  const dataValues = indicator.history.map(item => item.value)

  return {
    tooltip: {
      trigger: 'axis',
       backgroundColor: isDark ? DARK_PALETTE.elevated : 'rgba(255, 255, 255, 0.9)',
      borderColor: isDark ? DARK_PALETTE.border : '#e5e7eb',
      textStyle: {
        color: isDark ? DARK_PALETTE.text : '#111827'
      },
      formatter: function (params) {
        return `${params[0].axisValue}<br/><b>${formatIndicatorAxisValue(indicator, Number(params[0].data))}</b>`
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dataDates,
      axisLabel: { color: textColor },
      axisLine: { lineStyle: { color: splitLineColor } },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        color: textColor,
        formatter: (value) => formatIndicatorAxisValue(indicator, Number(value))
      },
      splitLine: { 
        show: true,
        lineStyle: {
          color: splitLineColor,
          type: 'dashed'
        }
      }
    },
    series: [
      {
        name: indicator.name,
        type: 'line',
        smooth: true,
        symbol: 'none',
        sampling: 'lttb', // downsample large datasets
        itemStyle: { color: lineColor },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: areaColor },
            { offset: 1, color: isDark ? 'rgba(59, 130, 246, 0)' : 'rgba(29, 111, 186, 0)' }
          ])
        },
        data: dataValues
      }
    ]
  }
}

const { chartContainer, renderChart } = useEcharts(() => (
  props.indicator?.history ? getChartOption(props.indicator, theme.value === 'dark') : {}
))

watch(() => props.indicator, () => {
  renderChart()
}, { deep: true })

watch(theme, () => {
  renderChart()
})

watch(timezone, () => {
  renderChart()
})
</script>
