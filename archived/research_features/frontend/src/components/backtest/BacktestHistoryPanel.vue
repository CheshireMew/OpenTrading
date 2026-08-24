<template>
  <div class="app-panel flex min-h-[320px] max-w-[440px] flex-col overflow-hidden p-5 transition-colors">
    <div class="flex items-center justify-between gap-3 mb-4">
      <div>
        <h2 class="text-xl font-semibold text-stone-950 dark:text-white">
          {{ panel.historyMode === 'paper' ? $t('backtest.paperRecent') : $t('backtest.recent') }}
        </h2>
        <div class="text-xs text-stone-500 dark:text-gray-400">
          {{ panel.historyMode === 'paper' ? $t('backtest.paperRecentHint') : (panel.enableHistoryCompare ? $t('backtest.selectForCompareHint') : $t('backtest.historyBrowseHint')) }}
        </div>
      </div>
      <div class="inline-flex border border-stone-200 bg-white p-1 dark:border-gray-700 dark:bg-gray-900/40">
        <button
          class="tab-btn"
          :class="{ active: panel.historyMode === 'backtest' }"
          @click="panel.historyMode = 'backtest'"
        >
          {{ $t('backtest.recent') }}
        </button>
        <button
          class="tab-btn"
          :class="{ active: panel.historyMode === 'paper' }"
          @click="panel.historyMode = 'paper'"
        >
          {{ $t('backtest.paperRecent') }}
        </button>
      </div>
    </div>
    <div class="overflow-y-auto flex-1 space-y-2">
      <div
        v-for="run in panel.visibleHistory"
        :key="run?.id ?? String(run)"
        class="group flex cursor-pointer items-start justify-between gap-3 border border-stone-200 bg-[#fbfaf7] p-3 transition hover:bg-stone-100 dark:border-gray-800 dark:bg-gray-900 dark:hover:bg-gray-700"
        @click="panel.openRunDetail(run, panel.historyMode)"
      >
        <div class="flex min-w-0 gap-3">
          <label v-if="panel.enableHistoryCompare && panel.historyMode === 'backtest' && run?.id" class="pt-1" @click.stop>
            <input :checked="panel.compareRunIds.includes(run.id)" type="checkbox" @change="panel.toggleCompareRun(run.id)" />
          </label>
          <div class="min-w-0">
            <div class="truncate font-bold text-[#0f6b4f] dark:text-emerald-300">{{ panel.portfolioLabel(run) }}</div>
            <div class="mt-1 truncate text-xs text-gray-500">
              {{ run?.metadata?.strategy_name || '-' }} · v{{ run?.metadata?.strategy_version || '-' }} · {{ run?.timeframe || '-' }}
            </div>
            <div class="mt-1 text-xs text-gray-400">
              {{ formatDateTime(run?.created_at) }} · {{ panel.runStatusLabel(run) }}
            </div>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="text-sm font-bold" :class="panel.profitColorClass(run?.report?.profit_pct)">{{ formatPercent(run?.report?.profit_pct) }}</div>
          <div class="text-xs text-gray-500">
            {{ formatNumber(run?.report?.total_trades ?? run?.metrics?.total_signals) }} {{ $t('backtest.totalTrades') }}
          </div>
          <div class="text-xs text-gray-500">{{ formatPercent(run?.report?.max_drawdown_pct) }}</div>
          <div class="mt-2 flex items-center justify-end gap-2 opacity-100 transition group-hover:opacity-100">
            <button
              v-if="panel.historyMode === 'paper' && run?.status === 'running' && run?.id"
              class="inline-flex items-center rounded-md bg-red-50 px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-100 dark:bg-red-950/40 dark:text-red-300"
              @click.stop="panel.stopPaperRun(run.id)"
            >
              {{ $t('backtest.paperStop') }}
            </button>
            <button
              v-if="run?.id"
              class="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-semibold text-gray-600 hover:bg-red-50 hover:text-red-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-red-950/40 dark:hover:text-red-300"
              @click.stop="panel.deleteRun(run.id, panel.historyMode)"
            >
              {{ $t('backtest.remove') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatDateTime, formatNumber, formatPercent } from '@/modules/format'
import type { BacktestHistoryPanelView } from '@/modules/backtest/viewTypes'

const props = defineProps<{ panel: BacktestHistoryPanelView }>()
const panel = props.panel
</script>

<style scoped>
.tab-btn { @apply px-3 py-1.5 text-xs font-semibold text-stone-500 transition dark:text-gray-400; }
.tab-btn.active { @apply bg-[#edf3ee] text-[#0f6b4f] dark:bg-gray-800 dark:text-white; }
</style>
