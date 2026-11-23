<template><div ref="chartContainer" class="trading-chart relative h-full w-full min-h-0 min-w-0" /></template>

<script setup lang="ts">
import { DARK_CHART_COLORS } from '@/theme/palette.mjs'
import { useI18n } from 'vue-i18n'

import { useTradingViewChart, type TradingViewChartProps } from './useTradingViewChart'

const props = withDefaults(defineProps<Partial<TradingViewChartProps>>(), {
  data: () => [],
  volumeData: () => [],
  chartType: 'candlestick',
  autoResize: true,
  colors: () => ({ ...DARK_CHART_COLORS }),
  strategyMarkers: () => [],
})

const emit = defineEmits<{ 'load-more': [] }>()
const { t } = useI18n()
const { chartContainer, getChart, isVisible, isResizing, setVisibleLogicalRange } = useTradingViewChart(props, emit, t)

defineExpose({
  get chart() { return getChart() },
  isVisible,
  isResizing,
  setVisibleLogicalRange,
})
</script>
