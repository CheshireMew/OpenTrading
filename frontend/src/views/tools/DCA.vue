<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <header class="app-workspace-header"><h1 class="app-title">{{ $t('nav.dca') }}</h1></header>
      <div class="dca-workspace">
        <aside class="dca-configuration min-w-0 space-y-6">
          <form class="app-panel p-5" @submit.prevent="runSimulation">
            <h2 class="app-section-title mb-5">{{ $t('dca.config') }}</h2>
            <div class="dca-primary-fields">
              <div><label class="label">{{ $t('dca.pair') }}</label><SymbolSearchBox v-model="config.symbol" :aria-label="$t('dca.pair')" /></div>
              <label><span class="label">{{ config.strategy === 'value_averaging' ? $t('dca.dailyTarget', { currency: displayCurrency }) : $t('dca.dailyBase', { currency: displayCurrency }) }}</span><input id="dca-amount" v-model.number="displayAmount" type="number" min="0" step="any" class="app-control w-full" /></label>
              <div><AppDateField v-model="config.start_date" :label="$t('dca.startDate')" :min="dcaStartMin" :max="dcaStartMax" input-class="app-control w-full" label-class="label" /><p class="app-muted mt-1 text-xs">{{ $t('dca.startDateHint') }}</p></div>
              <label><span class="label">{{ $t('dca.strategy') }}</span><select id="dca-strategy" v-model="config.strategy" class="app-control w-full"><option value="standard">{{ $t('dca.strategies.standard') }}</option><option value="ema_deviation">{{ $t('dca.strategies.ema20') }}</option><option value="rsi_dynamic">{{ $t('dca.strategies.rsi') }}</option><option v-if="!isIndexSelected" value="ahr999">{{ $t('dca.strategies.ahr999') }}</option><option v-if="!isIndexSelected" value="fear_greed">{{ $t('dca.strategies.fg') }}</option><option value="value_averaging">{{ $t('dca.strategies.va') }}</option></select></label>
              <label v-if="config.strategy !== 'standard' && config.strategy !== 'value_averaging'"><span class="label">{{ $t('dca.strength') }}</span><input id="dca-strength" v-model.number="config.strategy_params.multiplier" type="number" min="0" step="0.1" class="app-control w-full" /></label>
            </div>
            <details class="dca-execution-settings"><summary>{{ $t('ui.executionSettings') }}</summary><div class="mt-4 grid gap-4 sm:grid-cols-2"><label><span class="label">{{ $t('dca.investTime') }}</span><select id="dca-investment-time" v-model="config.investment_time" class="app-control w-full"><option v-for="time in ['00:00','02:00','04:00','06:00','08:00','10:00','12:00','14:00','16:00','18:00','20:00','22:00','23:00']" :key="time" :value="time">{{ time }}</option></select></label><label><span class="label">{{ $t('dca.timezone') }}</span><AppTimezoneSelect id="dca-timezone" :aria-label="$t('dca.timezone')" /></label></div></details>
            <div v-if="errorMessage" role="alert" class="app-inline-note mt-4 text-rose-700 dark:text-rose-300">{{ errorMessage }}</div>
            <button type="submit" :disabled="loading || !canRunSimulation" class="app-button-primary mt-5 w-full"><ArrowPathIcon v-if="loading" class="h-4 w-4 animate-spin" aria-hidden="true" />{{ loading ? $t('dca.calculating') : $t('dca.calculate') }}</button>
          </form>
          <section class="dca-market-context">
            <div class="mb-4 flex items-center justify-between gap-3"><h2 class="app-section-title">{{ $t('dca.market') }}</h2><button type="button" class="text-xs underline underline-offset-4 app-muted" :disabled="marketData.loading" @click="fetchMarketIndicators">{{ marketData.loading ? $t('dca.marketLoading') : $t('dca.refreshMarket') }}</button></div>
            <div v-if="marketData.error" role="alert" class="app-inline-note mb-4 text-amber-800 dark:text-amber-200">{{ marketData.error }}</div>
            <dl class="dca-context-values"><div><dt>{{ $t('dca.currentPrice') }}</dt><dd>{{ result ? formatMoney(result.current_price, result.pricing_currency || 'USDT') : marketData.currentPrice != null ? formatMoney(marketData.currentPrice, marketData.pricingCurrency) : '—' }}</dd><span v-if="result?.pricing_symbol || marketData.pricingSymbol" class="app-muted text-xs">{{ result?.pricing_symbol || marketData.pricingSymbol }}</span></div><div><dt>{{ $t('dca.rsi14') }}</dt><dd>{{ marketData.rsi ?? '—' }}</dd></div><div><dt>{{ $t('dca.fgIndex') }}</dt><dd :class="marketData.sentiment != null ? sentimentClass : 'app-muted'">{{ marketData.sentiment ?? $t('ui.unavailable') }}</dd><span v-if="marketData.sentimentLabel" class="app-muted text-xs">{{ marketData.sentimentLabel }}</span></div></dl>
            <p v-if="marketData.updatedAt" class="app-muted mt-4 text-xs">{{ $t('dca.marketUpdated', { time: new Date(marketData.updatedAt).toLocaleString() }) }}</p>
          </section>
        </aside>
        <section class="dca-results min-w-0 space-y-5" :aria-label="$t('dca.asset')" :aria-busy="loading">
          <div v-if="result?.data_quality === 'synthetic_and_exchange_proxy'" role="note" class="app-inline-note text-amber-800 dark:text-amber-200">{{ $t('dca.syntheticHistoryWarning') }}</div>
          <template v-if="result">
            <dl class="dca-output-values app-metric-strip">
              <div><dt>{{ $t('dca.roi') }}</dt><dd :class="isPositiveRoi ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300'">{{ (result.roi || 0).toFixed(2) }}%</dd></div>
              <div><dt>{{ $t('dca.currentValue') }}</dt><dd>{{ formatMoney(result.final_value, result.pricing_currency || 'USDT') }}</dd></div>
              <div><dt>{{ $t('dca.totalInvested') }}</dt><dd>{{ formatMoney(result.total_invested, result.pricing_currency || 'USDT') }}</dd></div>
              <div><dt>{{ $t('dca.avgCost') }}</dt><dd>{{ formatMoney(result.average_cost, result.pricing_currency || 'USDT') }}</dd></div>
              <div><dt>{{ $t('dca.holdings') }}</dt><dd>{{ (result.total_coins || 0).toFixed(6) }}</dd></div>
              <div><dt>{{ $t('dca.dcaDays') }}</dt><dd>{{ result.total_days || 0 }}</dd></div>
            </dl>
            <section class="app-panel p-5"><h2 class="app-section-title mb-4">{{ $t('dca.roiTrend') }}</h2><div class="h-80"><canvas ref="roiChartCanvas" role="img" :aria-label="$t('dca.roiTrend')" /></div></section>
            <div class="dca-supporting-charts"><section class="app-panel p-5"><h2 class="app-section-title mb-4">{{ $t('dca.priceVsCost') }}</h2><div class="h-64"><canvas ref="priceChartCanvas" role="img" :aria-label="$t('dca.priceVsCost')" /></div></section><section class="app-panel p-5"><h2 class="app-section-title mb-4">{{ $t('dca.dailyAmount') }}</h2><div class="h-64"><canvas ref="investmentChartCanvas" role="img" :aria-label="$t('dca.dailyAmount')" /></div></section></div>
          </template>
          <div v-else-if="loading" class="app-panel"><AppLoadingState :label="$t('dca.calculating')" :rows="6" /></div>
          <div v-else class="dca-empty"><AppEmptyState :title="$t('dca.emptyResultTitle')" :description="$t('ui.dcaEmptyHint')" :icon="PresentationChartLineIcon" /></div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ArrowPathIcon, PresentationChartLineIcon } from '@heroicons/vue/24/outline'
import AppEmptyState from '@/components/AppEmptyState.vue'
import AppLoadingState from '@/components/AppLoadingState.vue'
import AppDateField from '@/components/AppDateField.vue'
import AppTimezoneSelect from '@/components/AppTimezoneSelect.vue'
import SymbolSearchBox from '@/components/SymbolSearchBox.vue'
import { useDcaPage } from '@/modules/tools'

const {
  config,
  displayAmount,
  loading,
  errorMessage,
  result,
  marketData,
  fetchMarketIndicators,
  roiChartCanvas,
  priceChartCanvas,
  investmentChartCanvas,
  runSimulation,
  isPositiveRoi,
  isIndexSelected,
  dcaStartMin,
  dcaStartMax,
  canRunSimulation,
  sentimentClass,
  displayCurrency,
  formatMoney,
} = useDcaPage()
</script>

<style scoped>
.dca-workspace { display: grid; grid-template-columns: minmax(0, 1fr); gap: 28px; align-items: start; }
.dca-primary-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.dca-execution-settings { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--ui-border); }
.dca-execution-settings summary { cursor: pointer; font-size: 13px; color: var(--ui-muted); }
.dca-context-values { display: grid; grid-template-columns: 1.5fr 1fr 1fr; gap: 16px; }
.dca-context-values dt { color: var(--ui-muted); font-size: 12px; }
.dca-context-values dd { margin-top: 6px; font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.dca-output-values { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.dca-output-values > * { padding: 16px 12px; }
.dca-output-values > :nth-child(3n + 1) { padding-left: 0; }
.dca-output-values dd { font-size: 22px; }
.dca-supporting-charts { display: grid; gap: 20px; }
.dca-empty { border-block: 1px solid var(--ui-border); background: var(--ui-toolbar); }
@container app-content (min-width: 68rem) {
  .dca-workspace { grid-template-columns: 320px minmax(0, 1fr); }
  .dca-primary-fields { grid-template-columns: minmax(0, 1fr); }
  .dca-configuration { position: sticky; top: 24px; }
  .dca-context-values { grid-template-columns: 1fr 1fr; }
  .dca-context-values > :first-child { grid-column: 1 / -1; }
  .dca-supporting-charts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dca-empty { min-height: 400px; display: grid; align-items: center; }
}
@container app-content (max-width: 34rem) {
  .dca-primary-fields { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .dca-output-values { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dca-output-values > * { padding: 14px 8px; }
  .dca-output-values dd { font-size: 19px; }
  .dca-context-values { gap: 12px; }
  .dca-context-values dd { font-size: 16px; }
}
</style>
