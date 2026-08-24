<template>
  <section class="space-y-5">
    <section class="space-y-3">
      <div>
        <label class="label">{{ $t('backtest.symbols') }}</label>
        <SymbolSearchBox
          v-model="selectedSymbols"
          multiple
          :allowed-classes="['crypto']"
          trigger-class="!bg-white dark:!bg-gray-900"
        />
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">{{ $t('compare.timeframe') }}</label>
          <select v-model="panel.config.timeframe" class="input">
            <option v-for="tf in panel.timeframes" :key="tf" :value="tf">{{ $t(`compare.tf.${tf}`) }}</option>
          </select>
        </div>
        <AppDateField
          v-model="panel.config.start_date"
          :label="$t('backtest.startDate')"
          :max="panel.config.end_date || panel.today"
          label-class="label"
          input-class="input"
        />
      </div>
      <div class="grid grid-cols-2 gap-3">
        <AppDateField
          v-model="panel.config.end_date"
          :label="$t('backtest.endDate')"
          :min="panel.config.start_date"
          :max="panel.today"
          label-class="label"
          input-class="input"
        />
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">{{ $t('backtest.initialCash') }} ({{ displayCurrency }})</label>
          <input v-model.number="displayInitialCash" class="input" type="number" min="1" step="1000" />
        </div>
        <div>
          <label class="label">{{ $t('backtest.feeRate') }}</label>
          <input v-model.number="panel.config.fee_rate" class="input" type="number" min="0" max="100" step="0.01" />
        </div>
      </div>
    </section>

    <section class="space-y-3">
      <div class="section-title">{{ $t('backtest.portfolioSection') }}</div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">{{ $t('backtest.maxOpenTrades') }}</label>
          <input v-model.number="panel.config.portfolio.max_open_trades" class="input" type="number" min="1" max="50" />
        </div>
        <div>
          <label class="label">{{ $t('backtest.positionSize') }}</label>
          <input v-model.number="panel.config.portfolio.position_size_pct" class="input" type="number" min="0.1" max="100" step="0.1" />
        </div>
      </div>
      <div>
        <label class="label">{{ $t('backtest.stakeMode') }}</label>
        <select v-model="panel.config.portfolio.stake_mode" class="input">
          <option value="fixed">{{ $t('backtest.stakeModeFixed') }}</option>
          <option value="unlimited">{{ $t('backtest.stakeModeUnlimited') }}</option>
        </select>
      </div>
    </section>

    <section class="space-y-3">
      <div class="section-title">{{ $t('backtest.researchSection') }}</div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">{{ $t('backtest.slippage') }}</label>
          <input v-model.number="panel.config.research.slippage_bps" class="input" type="number" min="0" step="1" />
        </div>
        <div>
          <label class="label">{{ $t('backtest.fundingRate') }}</label>
          <input v-model.number="panel.config.research.funding_rate_daily" class="input" type="number" step="0.01" />
        </div>
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">{{ $t('backtest.inSampleRatio') }}</label>
          <input v-model.number="panel.config.research.in_sample_ratio" class="input" type="number" min="50" max="100" step="1" />
        </div>
        <div>
          <label class="label">{{ $t('backtest.optimizeTrials') }}</label>
          <input v-model.number="panel.config.research.optimize_trials" class="input" type="number" min="0" step="1" />
        </div>
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="label">{{ $t('backtest.optimizeMetric') }}</label>
          <select v-model="panel.config.research.optimize_metric" class="input">
            <option v-for="metric in panel.optimizeMetrics" :key="metric" :value="metric">{{ metric }}</option>
          </select>
        </div>
        <div>
          <label class="label">{{ $t('backtest.rollingWindows') }}</label>
          <input v-model.number="panel.config.research.rolling_windows" class="input" type="number" min="0" step="1" />
        </div>
      </div>
    </section>

    <div class="border border-[#b8d2c4] bg-[#edf3ee] px-3 py-2 text-xs text-[#0f6b4f] dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
      {{ $t('backtest.previewHint') }}
    </div>
    <div class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
      {{ $t('backtest.paperHint') }}
    </div>
    <div class="grid grid-cols-3 gap-3">
      <button :disabled="panel.isBusy || !panel.strategies.length" class="btn-secondary" @click="panel.previewBacktest">
        {{ panel.previewLoading ? $t('backtest.previewing') : $t('backtest.preview') }}
      </button>
      <button :disabled="panel.isBusy || !panel.strategies.length || !panel.strategyPreview" class="btn-primary" @click="panel.startBacktest">
        {{ panel.backtestLoading ? $t('backtest.running') : $t('backtest.confirmRun') }}
      </button>
      <button :disabled="panel.isBusy || !panel.strategies.length || !panel.canStartPaperRun" class="btn-paper" @click="panel.startPaperRun">
        {{ panel.paperLoading ? $t('backtest.running') : $t('backtest.paperRun') }}
      </button>
    </div>

    <section v-if="panel.strategyPreview" class="space-y-3 border border-stone-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
      <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div class="section-title">{{ $t('backtest.previewChart') }}</div>
          <div class="text-xs text-stone-500 dark:text-gray-400">
            {{ panel.strategyPreview.strategy_name }} v{{ panel.strategyPreview.strategy_version }} · {{ panel.strategyPreview.timeframe }}
          </div>
        </div>
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
          <select :value="panel.config.timeframe" class="input max-w-[180px]" :disabled="panel.isBusy" @change="changePreviewTimeframe">
            <option v-for="tf in panel.timeframes" :key="tf" :value="tf">{{ $t(`compare.tf.${tf}`) }}</option>
          </select>
          <select v-if="panel.previewSymbols.length > 1" v-model="panel.previewSymbol" class="input max-w-[180px]">
            <option v-for="symbol in panel.previewSymbols" :key="symbol" :value="symbol">{{ symbol }}</option>
          </select>
        </div>
      </div>
      <div class="h-[420px] overflow-hidden border border-stone-200 dark:border-gray-700">
        <TradingViewChart
          :data="panel.previewChartData.candles"
          :volume-data="panel.previewChartData.volume"
          :strategy-markers="panel.previewChartData.markers"
          :colors="chartColors"
        />
      </div>
      <div class="grid grid-cols-2 gap-3 text-xs text-stone-600 dark:text-gray-300 md:grid-cols-4">
        <div class="border border-stone-200 px-3 py-2 dark:border-gray-700">
          <div class="text-stone-400">{{ $t('backtest.previewSignals') }}</div>
          <div class="mt-1 font-semibold text-stone-950 dark:text-white">{{ panel.previewMarkers.length }}</div>
        </div>
        <div class="border border-stone-200 px-3 py-2 dark:border-gray-700">
          <div class="text-stone-400">{{ $t('backtest.previewFingerprint') }}</div>
          <div class="mt-1 truncate font-mono text-[11px] text-stone-950 dark:text-white">{{ panel.strategyPreview.fingerprint }}</div>
        </div>
      </div>
      <div v-if="panel.strategyPreview.diagnostics?.length" class="space-y-2">
        <div
          v-for="item in panel.strategyPreview.diagnostics"
          :key="`${item.severity}-${item.title}`"
          class="border px-3 py-2 text-xs"
          :class="item.severity === 'critical'
            ? 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-300'
            : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300'"
        >
          <div class="font-semibold">{{ item.title }}</div>
          <div class="mt-1">{{ item.message }}</div>
        </div>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick } from 'vue'
import AppDateField from '@/components/AppDateField.vue'
import SymbolSearchBox from '@/components/SymbolSearchBox.vue'
import TradingViewChart from '@/components/TradingViewChart.vue'
import { useMoney } from '@/composables/useMoney'
import type { BacktestControlPanelView } from '@/modules/backtest/viewTypes'

const props = defineProps<{ panel: BacktestControlPanelView }>()
const panel = props.panel
const { displayCurrency, formatDisplayNumber, fromDisplayAmount } = useMoney()
const chartColors = {
  bg: '#ffffff',
  grid: '#e5e7eb',
  text: '#4b5563',
  upColor: '#10b981',
  downColor: '#ef4444',
}
const selectedSymbols = computed({
  get: () => panel.symbolsText.split(',').map((item) => item.trim()).filter(Boolean),
  set: (value: string[]) => {
    panel.symbolsText = value.join(', ')
  },
})
const displayInitialCash = computed({
  get: () => formatDisplayNumber(panel.config.initial_cash, 'USDT', 2),
  set: (value: number | string) => {
    panel.config.initial_cash = fromDisplayAmount(value, 'USDT') ?? panel.config.initial_cash
  },
})

const changePreviewTimeframe = async (event: Event) => {
  const target = event.target as HTMLSelectElement | null
  const timeframe = target?.value || ''
  if (!timeframe || timeframe === panel.config.timeframe) return
  panel.config.timeframe = timeframe
  await nextTick()
  await panel.previewBacktest()
}
</script>

<style scoped>
.btn-paper { @apply app-button-primary py-2; }
</style>
