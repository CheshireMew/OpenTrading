<template>
  <div v-if="panel.selectedRun" class="app-panel flex min-h-[500px] flex-1 flex-col space-y-6 p-6 transition-colors">
    <BacktestResultOverview :panel="panel" />
    <BacktestResearchSection v-if="!panel.isPaperRun" :panel="panel" />
    <BacktestCompareSection v-if="!panel.isPaperRun" :panel="panel" />
    <BacktestTradeReview :panel="panel" />
  </div>
</template>

<script setup lang="ts">
import BacktestCompareSection from '@/components/backtest/BacktestCompareSection.vue'
import BacktestResearchSection from '@/components/backtest/BacktestResearchSection.vue'
import BacktestResultOverview from '@/components/backtest/BacktestResultOverview.vue'
import BacktestTradeReview from '@/components/backtest/BacktestTradeReview.vue'
import type { BacktestResultPanelView } from '@/modules/backtest/viewTypes'

const props = defineProps<{ panel: BacktestResultPanelView }>()
const panel = props.panel
</script>
