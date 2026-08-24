<template>
  <section class="space-y-6">
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <div class="app-card">
        <div class="text-sm font-bold text-gray-900 dark:text-white mb-3">{{ $t('backtest.researchSummary') }}</div>
        <div class="space-y-2 text-sm text-gray-600 dark:text-gray-300">
          <div class="config-row"><span>{{ $t('backtest.optimizeMetric') }}</span><strong>{{ panel.selectedRun.report?.research?.optimization?.metric || '-' }}</strong></div>
          <div class="config-row"><span>{{ $t('backtest.selectedConfig') }}</span><strong>{{ panel.configLabel(panel.selectedRun.report?.research?.selected_config) }}</strong></div>
          <div class="config-row"><span>In Sample</span><strong>{{ formatPercent(panel.selectedRun.report?.research?.in_sample?.report?.profit_pct) }}</strong></div>
          <div class="config-row"><span>Out Sample</span><strong>{{ formatPercent(panel.selectedRun.report?.research?.out_of_sample?.report?.profit_pct) }}</strong></div>
        </div>
        <div class="mt-4 flex flex-wrap items-center gap-3">
          <button
            class="bg-[#0f6b4f] px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#0b5a41] disabled:cursor-not-allowed disabled:bg-gray-400"
            :disabled="panel.evolutionLoading"
            @click="panel.evolveStrategy"
          >
            {{ panel.evolutionLoading ? '进化中...' : '诊断并进化策略' }}
          </button>
          <span v-if="panel.evolutionResult" class="text-xs text-gray-500 dark:text-gray-400">
            {{ panel.evolutionResult.message }}
          </span>
        </div>
        <div v-if="panel.evolutionResult" class="mt-4 space-y-3">
          <div v-if="(panel.evolutionResult.defects || []).length" class="space-y-2">
            <div v-for="defect in (panel.evolutionResult.defects || [])" :key="defect.key" class="border border-[#e4ded3] bg-[#fbfaf7] px-3 py-2 text-xs dark:border-gray-700 dark:bg-gray-900/40">
              <div class="font-semibold text-gray-900 dark:text-white">{{ defect.title }}</div>
              <div class="mt-1 text-gray-500 dark:text-gray-400">{{ defect.recommendation }}</div>
            </div>
          </div>
          <div v-if="(panel.evolutionResult.changes || []).length" class="text-xs text-gray-600 dark:text-gray-300">
            <span class="font-semibold text-gray-900 dark:text-white">变更</span>
            <span class="ml-2">{{ (panel.evolutionResult.changes || []).map((item) => item.path).join(', ') }}</span>
          </div>
        </div>
      </div>
      <div class="app-card">
        <div class="text-sm font-bold text-gray-900 dark:text-white mb-3">{{ $t('backtest.pairBreakdown') }}</div>
        <div v-if="panel.pairBreakdown.length" class="space-y-2">
          <div v-for="item in panel.pairBreakdown" :key="item.pair" class="pair-card">
            <div class="font-semibold text-gray-900 dark:text-white">{{ item.pair }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400">{{ formatNumber(item.trades) }} {{ $t('backtest.totalTrades') }}</div>
            <div class="text-sm mt-1" :class="panel.profitColorClass(item.profit_pct)">{{ formatPercent(item.profit_pct) }} / {{ formatMoney(item.profit_abs) }}</div>
          </div>
        </div>
        <div v-else class="text-sm text-gray-500 dark:text-gray-400">{{ $t('common.noData') }}</div>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <div class="app-card">
        <div class="text-sm font-bold text-gray-900 dark:text-white mb-3">{{ $t('backtest.optimizationTrials') }}</div>
        <div v-if="panel.optimizationTrials.length" class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <th class="py-2 pr-4">{{ $t('backtest.trial') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.score') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.totalReturn') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.maxDrawdown') }}</th>
                <th class="py-2">{{ $t('backtest.selectedConfig') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="trial in panel.optimizationTrials" :key="trial.trial" class="border-b border-gray-100 dark:border-gray-800 text-gray-700 dark:text-gray-200">
                <td class="py-2 pr-4">{{ trial.trial }}</td>
                <td class="py-2 pr-4">{{ formatMetric(trial.score) }}</td>
                <td class="py-2 pr-4" :class="panel.profitColorClass(trial.report?.profit_pct)">{{ formatPercent(trial.report?.profit_pct) }}</td>
                <td class="py-2 pr-4 text-red-600 dark:text-red-400">{{ formatPercent(trial.report?.max_drawdown_pct) }}</td>
                <td class="py-2">{{ panel.configLabel(trial.config) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="text-sm text-gray-500 dark:text-gray-400">{{ $t('common.noData') }}</div>
      </div>

      <div class="app-card">
        <div class="text-sm font-bold text-gray-900 dark:text-white mb-3">{{ $t('backtest.rollingWindowReport') }}</div>
        <div v-if="panel.rollingWindows.length" class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <th class="py-2 pr-4">{{ $t('backtest.window') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.trainRange') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.testRange') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.totalReturn') }}</th>
                <th class="py-2">{{ $t('backtest.maxDrawdown') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in panel.rollingWindows" :key="item.index" class="border-b border-gray-100 dark:border-gray-800 text-gray-700 dark:text-gray-200">
                <td class="py-2 pr-4">{{ item.index }}</td>
                <td class="py-2 pr-4 whitespace-nowrap">{{ formatRange(item.train) }}</td>
                <td class="py-2 pr-4 whitespace-nowrap">{{ formatRange(item.test) }}</td>
                <td class="py-2 pr-4" :class="panel.profitColorClass(item.report?.profit_pct)">{{ formatPercent(item.report?.profit_pct) }}</td>
                <td class="py-2 text-red-600 dark:text-red-400">{{ formatPercent(item.report?.max_drawdown_pct) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="text-sm text-gray-500 dark:text-gray-400">{{ $t('common.noData') }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { formatMetric, formatMoney, formatNumber, formatPercent, formatRange } from '@/modules/format'
import type { BacktestResultPanelView } from '@/modules/backtest/viewTypes'

const props = defineProps<{ panel: BacktestResultPanelView }>()
const panel = props.panel
</script>

<style scoped>
.config-row { @apply flex items-center justify-between gap-3 text-sm text-gray-600 dark:text-gray-300; }
.pair-card { @apply border px-3 py-3 dark:border-gray-700 dark:bg-gray-900/40; border-color: #e4ded3; background: #fbfaf7; }
</style>
