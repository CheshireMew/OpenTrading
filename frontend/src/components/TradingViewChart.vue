<template><div ref="chartContainer" class="relative h-full w-full" /></template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { useTradingViewChart, type TradingViewChartProps } from './useTradingViewChart'

const props = withDefaults(defineProps<Partial<TradingViewChartProps>>(), {
  data: () => [],
  volumeData: () => [],
  chartType: 'candlestick',
  autoResize: true,
  colors: () => ({
    upColor: '#26a69a',
    downColor: '#ef5350',
    bg: '#1f2937',
    text: '#9ca3af',
    grid: '#374151',
  }),
  strategyMarkers: () => [],
})

const emit = defineEmits<{ 'load-more': [] }>()
const { t } = useI18n()
const { chartContainer, getChart } = useTradingViewChart(props, emit, t)

defineExpose({
  get chart() { return getChart() },
})
</script>
