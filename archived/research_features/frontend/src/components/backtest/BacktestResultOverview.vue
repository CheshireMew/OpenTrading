<template>
  <section class="space-y-6">
    <div class="flex flex-col xl:flex-row xl:items-end xl:justify-between gap-3">
      <div>
        <h3 class="text-xl font-bold text-gray-900 dark:text-white">{{ $t('backtest.result') }}: #{{ panel.selectedRun?.id ?? '-' }}</h3>
        <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {{ panel.portfolioLabel(panel.selectedRun) }} · {{ panel.selectedRun?.metadata?.strategy_name || '-' }} · v{{ panel.selectedRun?.metadata?.strategy_version || '-' }}
        </div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div class="stat-badge">{{ $t('backtest.buy') }}: {{ panel.selectedRun?.metrics?.buy_signals ?? 0 }}</div>
        <div class="stat-badge">{{ $t('backtest.sell') }}: {{ panel.selectedRun?.metrics?.sell_signals ?? 0 }}</div>
        <div class="stat-badge">{{ $t('backtest.runMode') }}: {{ panel.isPaperRun ? $t('backtest.paperRunShort') : $t('backtest.runShort') }}</div>
        <div class="stat-badge">{{ $t('backtest.runStatus') }}: {{ panel.runStatusLabel(panel.selectedRun) }}</div>
      </div>
    </div>

    <div class="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
      <div class="summary-card">
        <div class="summary-label">{{ $t('backtest.totalReturn') }}</div>
        <div class="summary-value" :class="panel.profitColorClass(panel.selectedRun.report?.profit_pct)">{{ formatPercent(panel.selectedRun.report?.profit_pct) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">{{ $t('backtest.finalBalance') }}</div>
        <div class="summary-value">{{ formatMoney(panel.selectedRun.report?.final_balance) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">{{ $t('backtest.maxDrawdown') }}</div>
        <div class="summary-value text-red-600 dark:text-red-400">{{ formatPercent(panel.selectedRun.report?.max_drawdown_pct) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">{{ $t('backtest.sharpe') }}</div>
        <div class="summary-value">{{ formatMetric(panel.selectedRun.report?.sharpe) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">{{ $t('backtest.winRate') }}</div>
        <div class="summary-value">{{ formatPercent(panel.selectedRun.report?.win_rate) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">{{ $t('backtest.profitFactor') }}</div>
        <div class="summary-value">{{ formatMetric(panel.selectedRun.report?.profit_factor) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">{{ $t('backtest.avgTrade') }}</div>
        <div class="summary-value">{{ formatPercent(panel.selectedRun.report?.avg_trade_pct) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">{{ $t('backtest.totalTrades') }}</div>
        <div class="summary-value">{{ formatNumber(panel.selectedRun.report?.total_trades) }}</div>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)] gap-6">
      <div class="space-y-3 border border-[#e4ded3] bg-[#fbfaf7] p-4 dark:border-gray-700 dark:bg-gray-900/40">
        <h4 class="text-sm font-bold text-gray-900 dark:text-white">{{ $t('backtest.config') }}</h4>
        <div class="config-row"><span>{{ $t('backtest.symbols') }}</span><strong>{{ panel.joinSymbols(panel.selectedRun.metadata?.symbols) }}</strong></div>
        <div class="config-row"><span>{{ $t('compare.timeframe') }}</span><strong>{{ panel.selectedRun.timeframe }}</strong></div>
        <div class="config-row"><span>{{ $t('backtest.initialCash') }}</span><strong>{{ formatMoney(panel.selectedRun.metadata?.initial_cash) }}</strong></div>
        <div class="config-row"><span>{{ $t('backtest.feeRate') }}</span><strong>{{ formatPercent(panel.selectedRun.metadata?.fee_rate) }}</strong></div>
        <div class="config-row"><span>{{ $t('backtest.maxOpenTrades') }}</span><strong>{{ panel.selectedRun.report?.portfolio?.max_open_trades ?? '-' }}</strong></div>
        <div class="config-row"><span>{{ $t('backtest.positionSize') }}</span><strong>{{ formatPercent(panel.selectedRun.report?.portfolio?.position_size_pct) }}</strong></div>
        <div class="config-row"><span>{{ $t('backtest.stakeMode') }}</span><strong>{{ panel.selectedRun.report?.portfolio?.stake_mode || '-' }}</strong></div>
        <div v-if="!panel.isPaperRun" class="config-row"><span>{{ $t('backtest.slippage') }}</span><strong>{{ formatMetric(panel.selectedRun.report?.research?.slippage_bps) }} bps</strong></div>
        <div v-if="!panel.isPaperRun" class="config-row"><span>{{ $t('backtest.fundingRate') }}</span><strong>{{ formatPercent(panel.selectedRun.report?.research?.funding_rate_daily) }}</strong></div>
        <div v-if="!panel.isPaperRun" class="config-row"><span>{{ $t('backtest.inSampleRatio') }}</span><strong>{{ formatPercent(panel.selectedRun.report?.research?.in_sample_ratio) }}</strong></div>
        <div v-if="panel.isPaperRun" class="config-row">
          <span>{{ $t('backtest.paperOpenPositions') }}</span>
          <strong>{{ panel.selectedRun.metadata?.paper_live?.open_positions ?? 0 }}</strong>
        </div>
        <div v-if="panel.isPaperRun" class="config-row">
          <span>{{ $t('backtest.paperCash') }}</span>
          <strong>{{ formatMoney(panel.selectedRun.metadata?.paper_live?.cash_balance) }}</strong>
        </div>
      </div>

      <div class="app-card">
        <div class="text-sm font-bold text-gray-900 dark:text-white mb-3">{{ $t('backtest.equityCurve') }}</div>
        <div class="h-[320px]">
          <BacktestEquityChart :points="panel.selectedRun.equity_curve || []" />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import BacktestEquityChart from '@/components/BacktestEquityChart.vue'
import { formatMetric, formatMoney, formatNumber, formatPercent } from '@/modules/format'
import type { BacktestResultPanelView } from '@/modules/backtest/viewTypes'

const props = defineProps<{ panel: BacktestResultPanelView }>()
const panel = props.panel
</script>

<style scoped>
.stat-badge { @apply px-3 py-2 text-sm font-bold border dark:border-gray-700 dark:bg-gray-900/40 text-gray-700 dark:text-gray-200; border-color: #e4ded3; background: #fbfaf7; }
.summary-card { @apply border px-4 py-3 dark:border-gray-700 dark:bg-gray-900/40; border-color: #e4ded3; background: #fbfaf7; }
.summary-label { @apply text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400; }
.summary-value { @apply mt-2 text-lg font-bold text-gray-900 dark:text-white; }
.config-row { @apply flex items-center justify-between gap-3 text-sm text-gray-600 dark:text-gray-300; }
</style>
