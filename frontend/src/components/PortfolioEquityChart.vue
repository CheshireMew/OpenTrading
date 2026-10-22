<template>
  <div class="w-full h-full" ref="chartContainer"></div>
</template>

<script setup>
import { DARK_PALETTE } from '@/theme/palette.mjs'
import { watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEcharts } from '@/composables/useEcharts'
import { useTheme } from '@/composables/useTheme'
import { useMoney } from '@/composables/useMoney'
import { useDateTime } from '@/composables/useDateTime'
import { useI18n } from 'vue-i18n'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  points: {
    type: Array,
    default: () => [],
  },
})

const { theme } = useTheme()
const { displayCurrency, toDisplayAmount, formatMoney } = useMoney()
const { timezone, formatDateTime } = useDateTime()
const { t, locale } = useI18n()

const getOption = () => {
  const isDark = theme.value === 'dark'
  const axisColor = isDark ? DARK_PALETTE.muted : '#4b5563'
  const splitLineColor = isDark ? DARK_PALETTE.grid : '#e5e7eb'
  const equityColor = isDark ? '#60a5fa' : '#2563eb'
  const drawdownColor = isDark ? '#fca5a5' : '#dc2626'
  const data = props.points || []
  const equityLabel = t('portfolioBalance.equity')
  const drawdownLabel = t('portfolioBalance.drawdown')

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      backgroundColor: isDark ? DARK_PALETTE.elevated : 'rgba(255, 255, 255, 0.95)',
      borderColor: isDark ? DARK_PALETTE.border : '#e5e7eb',
      textStyle: {
        color: isDark ? DARK_PALETTE.text : '#111827',
      },
      formatter(params) {
        const point = data[params[0]?.dataIndex ?? 0]
        if (!point) return ''
        return [
          formatDateTime(point.timestamp, { hour12: false }),
          `${equityLabel}: ${formatMoney(point.equity, 'USDT')}`,
          `${t('portfolioBalance.pnlAbs')}: ${formatMoney(point.pnl_abs, 'USDT')}`,
          `${drawdownLabel}: ${point.drawdown_pct.toFixed(2)}%`,
        ].join('<br/>')
      },
    },
    legend: {
      top: 0,
      data: [equityLabel, drawdownLabel],
      textStyle: { color: axisColor },
    },
    grid: {
      left: '4%',
      right: '4%',
      top: '12%',
      bottom: '6%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: data.map((item) => formatDateTime(item.timestamp, { hour12: false })),
      axisLabel: { color: axisColor },
      axisLine: { lineStyle: { color: splitLineColor } },
    },
    yAxis: [
      {
        type: 'value',
        scale: true,
        axisLabel: { color: axisColor, formatter: (value) => formatMoney(value, displayCurrency.value, { maximumFractionDigits: 0 }) },
        splitLine: {
          lineStyle: {
            color: splitLineColor,
            type: 'dashed',
          },
        },
      },
      {
        type: 'value',
        scale: true,
        axisLabel: { color: axisColor, formatter: '{value}%' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: equityLabel,
        color: equityColor,
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: data.map((item) => toDisplayAmount(item.equity, 'USDT') ?? 0),
        lineStyle: { color: equityColor, width: 2 },
        itemStyle: { color: equityColor },
        areaStyle: {
          color: isDark ? 'rgba(96, 165, 250, 0.18)' : 'rgba(37, 99, 235, 0.12)',
        },
      },
      {
        name: drawdownLabel,
        color: drawdownColor,
        type: 'line',
        smooth: true,
        symbol: 'none',
        yAxisIndex: 1,
        data: data.map((item) => item.drawdown_pct),
        lineStyle: { color: drawdownColor, width: 2 },
        itemStyle: { color: drawdownColor },
      },
    ],
  }
}

const { chartContainer, renderChart } = useEcharts(getOption)

watch(
  () => props.points,
  () => {
    renderChart()
  },
  { deep: true },
)

watch(theme, () => {
  renderChart()
})

watch(locale, () => {
  renderChart()
})

watch(timezone, () => {
  renderChart()
})

watch(displayCurrency, () => {
  renderChart()
})
</script>
