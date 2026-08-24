<template>
  <div ref="chartContainer" class="relative h-full w-full">
    <div
      v-if="tradeOverlay && tradeSetup"
      class="pointer-events-none absolute inset-0 z-10 text-xs font-semibold"
    >
      <div class="absolute rounded border border-emerald-400/50 bg-emerald-400/20" :style="tradeOverlay.rewardBox" />
      <div class="absolute rounded border border-rose-400/50 bg-rose-400/20" :style="tradeOverlay.riskBox" />
      <div class="absolute rounded bg-gray-900 px-2 py-1 text-white shadow dark:bg-white dark:text-gray-900" :style="tradeOverlay.entryLabel">
        {{ t('dashboard.entry') }} {{ chartPriceText(tradeSetup.entry) }}
      </div>
      <div class="absolute rounded bg-emerald-600 px-2 py-1 text-white shadow" :style="tradeOverlay.targetLabel">
        {{ t('dashboard.target') }} {{ chartPriceText(tradeSetup.target) }}
      </div>
      <div class="absolute rounded bg-rose-600 px-2 py-1 text-white shadow" :style="tradeOverlay.stopLabel">
        {{ t('dashboard.stop') }} {{ chartPriceText(tradeSetup.stop) }}
      </div>
      <div class="absolute rounded bg-gray-900 px-2 py-1 text-white shadow dark:bg-white dark:text-gray-900" :style="tradeOverlay.ratioLabel">
        {{ t('dashboard.riskReward') }} {{ tradeSetup.risk_reward.toFixed(2) }}
      </div>
    </div>
  </div>
</template>

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
  tradeSetup: null,
  strategyMarkers: () => [],
})

const emit = defineEmits<{ 'load-more': [] }>()
const { t } = useI18n()
const { chartContainer, tradeOverlay, chartPriceText, getChart } = useTradingViewChart(props, emit, t)

defineExpose({
  get chart() { return getChart() },
})
</script>
