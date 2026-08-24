<template>
  <section class="grid grid-cols-1 xl:grid-cols-2 gap-6">
    <div class="app-card space-y-4">
      <div class="flex items-center justify-between gap-3">
        <div class="text-sm font-bold text-gray-900 dark:text-white">{{ $t('backtest.runCompare') }}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">{{ $t('backtest.selectForCompareHint') }}</div>
      </div>
      <template v-if="panel.selectedCompareRuns.length">
        <div class="h-[260px]">
          <BacktestMetricCompareChart :categories="panel.recentRunCompare.performance.categories" :series="panel.recentRunCompare.performance.series" :dark="panel.isDark" />
        </div>
        <div class="h-[260px]">
          <BacktestMetricCompareChart :categories="panel.recentRunCompare.quality.categories" :series="panel.recentRunCompare.quality.series" :dark="panel.isDark" />
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <th class="py-2 pr-4">{{ $t('backtest.runLabel') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.totalReturn') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.maxDrawdown') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.sharpe') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.winRate') }}</th>
                <th class="py-2">{{ $t('backtest.totalTrades') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in panel.selectedCompareRuns" :key="run.id" class="border-b border-gray-100 dark:border-gray-800 text-gray-700 dark:text-gray-200">
                <td class="py-2 pr-4">{{ panel.compareRunLabel(run) }}</td>
                <td class="py-2 pr-4" :class="panel.profitColorClass(run.report?.profit_pct)">{{ formatPercent(run.report?.profit_pct) }}</td>
                <td class="py-2 pr-4 text-red-600 dark:text-red-400">{{ formatPercent(run.report?.max_drawdown_pct) }}</td>
                <td class="py-2 pr-4">{{ formatMetric(run.report?.sharpe) }}</td>
                <td class="py-2 pr-4">{{ formatPercent(run.report?.win_rate) }}</td>
                <td class="py-2">{{ formatNumber(run.report?.total_trades) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
      <div v-else class="text-sm text-gray-500 dark:text-gray-400">{{ $t('backtest.noCompareSelection') }}</div>
    </div>

    <div class="app-card space-y-4">
      <div class="flex items-center justify-between gap-3">
        <div class="text-sm font-bold text-gray-900 dark:text-white">{{ $t('backtest.versionCompare') }}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">{{ $t('backtest.versionCompareHint') }}</div>
      </div>
      <div v-if="panel.versionCompareOptions.length" class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <label
          v-for="item in panel.versionCompareOptions"
          :key="item.version"
          class="flex items-center justify-between gap-3 border border-[#e4ded3] bg-[#fbfaf7] px-3 py-2 dark:border-gray-700 dark:bg-gray-900/40"
        >
          <div class="flex items-center gap-2">
            <input :checked="panel.versionCompareSelections.includes(item.version)" type="checkbox" @change="panel.toggleVersionCompare(item.version)" />
            <span class="font-semibold text-gray-900 dark:text-white">v{{ item.version }}</span>
          </div>
          <div class="text-right">
            <div class="text-xs text-gray-500 dark:text-gray-400">{{ item.name }}</div>
            <div class="text-xs" :class="panel.profitColorClass(item.run.report?.profit_pct)">{{ formatPercent(item.run.report?.profit_pct) }}</div>
          </div>
        </label>
      </div>
      <template v-if="panel.selectedVersionCompareRuns.length">
        <div class="h-[260px]">
          <BacktestMetricCompareChart :categories="panel.versionRunCompare.performance.categories" :series="panel.versionRunCompare.performance.series" :dark="panel.isDark" />
        </div>
        <div class="h-[260px]">
          <BacktestMetricCompareChart :categories="panel.versionRunCompare.quality.categories" :series="panel.versionRunCompare.quality.series" :dark="panel.isDark" />
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <th class="py-2 pr-4">{{ $t('backtest.version') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.latestVersionRun') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.totalReturn') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.maxDrawdown') }}</th>
                <th class="py-2 pr-4">{{ $t('backtest.sharpe') }}</th>
                <th class="py-2">{{ $t('backtest.totalTrades') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in panel.selectedVersionCompareRuns" :key="run.id" class="border-b border-gray-100 dark:border-gray-800 text-gray-700 dark:text-gray-200">
                <td class="py-2 pr-4">v{{ run.metadata?.strategy_version || '-' }}</td>
                <td class="py-2 pr-4">{{ formatDateTime(run.created_at) }}</td>
                <td class="py-2 pr-4" :class="panel.profitColorClass(run.report?.profit_pct)">{{ formatPercent(run.report?.profit_pct) }}</td>
                <td class="py-2 pr-4 text-red-600 dark:text-red-400">{{ formatPercent(run.report?.max_drawdown_pct) }}</td>
                <td class="py-2 pr-4">{{ formatMetric(run.report?.sharpe) }}</td>
                <td class="py-2">{{ formatNumber(run.report?.total_trades) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
      <div v-else class="text-sm text-gray-500 dark:text-gray-400">{{ $t('backtest.noVersionCompareData') }}</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import BacktestMetricCompareChart from '@/components/BacktestMetricCompareChart.vue'
import { formatDateTime, formatMetric, formatNumber, formatPercent } from '@/modules/format'
import type { BacktestResultPanelView } from '@/modules/backtest/viewTypes'

const props = defineProps<{ panel: BacktestResultPanelView }>()
const panel = props.panel
</script>
