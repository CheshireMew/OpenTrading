<template>
  <div class="app-page">
    <div class="app-page-inner-wide flex flex-col space-y-4">
    <!-- Configuration -->
    <div class="app-hero-panel transition-colors">
      <h2 class="app-section-title mb-4 flex items-center">
        <BanknotesIcon class="mr-2 h-6 w-6 text-[#0f6b4f] dark:text-green-400" />
        {{ $t('dca.config') }}
      </h2>
      
      <div class="dca-config-grid grid gap-4 items-end">
        <div>
          <label class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('dca.pair') }}</label>
          <SymbolSearchBox v-model="config.symbol" :aria-label="$t('dca.pair')" />
        </div>
        <div>
          <AppDateField
            v-model="config.start_date"
            :label="$t('dca.startDate')"
            :min="dcaStartMin"
            :max="dcaStartMax"
            input-class="app-control w-full"
            label-class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400"
          />
          <p class="mt-1 text-xs text-stone-500 dark:text-slate-400">{{ $t('dca.startDateHint') }}</p>
        </div>
        <div>
          <label for="dca-investment-time" class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('dca.investTime') }}</label>
          <select id="dca-investment-time" v-model="config.investment_time" class="app-control w-full">
            <option value="00:00">00:00</option>
            <option value="02:00">02:00</option>
            <option value="04:00">04:00</option>
            <option value="06:00">06:00</option>
            <option value="08:00">08:00</option>
            <option value="10:00">10:00</option>
            <option value="12:00">12:00</option>
            <option value="14:00">14:00</option>
            <option value="16:00">16:00</option>
            <option value="18:00">18:00</option>
            <option value="20:00">20:00</option>
            <option value="22:00">22:00</option>
            <option value="23:00">23:00</option>
          </select>
        </div>
        
        <!-- Strategy Selector -->
        <div>
           <label for="dca-strategy" class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('dca.strategy') }}</label>
           <select id="dca-strategy" v-model="config.strategy" class="app-control w-full">
             <option value="standard">{{ $t('dca.strategies.standard') }}</option>
             <option value="ema_deviation">{{ $t('dca.strategies.ema20') }}</option>
             <option value="rsi_dynamic">{{ $t('dca.strategies.rsi') }}</option>
             <option v-if="!isIndexSelected" value="ahr999">{{ $t('dca.strategies.ahr999') }}</option>
             <option v-if="!isIndexSelected" value="fear_greed">{{ $t('dca.strategies.fg') }}</option>
             <option value="value_averaging">{{ $t('dca.strategies.va') }}</option>
           </select>
        </div>

        <div>
           <label for="dca-timezone" class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('dca.timezone') }}</label>
           <AppTimezoneSelect id="dca-timezone" :aria-label="$t('dca.timezone')" />
        </div>

        <div>
          <label for="dca-amount" class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">
              {{ config.strategy === 'value_averaging' ? $t('dca.dailyTarget', { currency: displayCurrency }) : $t('dca.dailyBase', { currency: displayCurrency }) }}
          </label>
          <input id="dca-amount" v-model.number="displayAmount" type="number" min="0" class="app-control w-full" />
        </div>

        <!-- Strategy Params (Conditional) -->
        <div v-if="config.strategy !== 'standard' && config.strategy !== 'value_averaging'">
           <label for="dca-strength" class="mb-1 flex justify-between text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">
              <span>{{ $t('dca.strength') }}</span>
              <span class="text-gray-500 font-normal">
                  {{
                      config.strategy === 'ema_deviation' ? `${$t('dca.recommended')}: 2.0 - 5.0` :
                      config.strategy === 'rsi_dynamic' ? `${$t('dca.recommended')}: 1.0 - 3.0` :
                      config.strategy === 'ahr999' ? `${$t('dca.recommended')}: 0.5 - 2.0` :
                      config.strategy === 'fear_greed' ? `${$t('dca.recommended')}: 1.0 - 3.0` : ''
                  }}
              </span>
           </label>
           <input id="dca-strength" v-model.number="config.strategy_params.multiplier" type="number" min="0" step="0.1" class="app-control w-full" />
        </div>
        
        <button type="button" @click="runSimulation" :disabled="loading || !canRunSimulation" class="dca-config-submit app-button-primary app-touch-target flex items-center justify-center px-6 py-2">
          <span v-if="loading" class="mr-2 animate-spin">⟳</span>
          {{ $t('dca.calculate') }}
        </button>
      </div>
    </div>

    <div v-if="errorMessage" role="alert" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
      {{ errorMessage }}
    </div>

    <div v-if="result?.data_quality === 'synthetic_and_exchange_proxy'" role="note" class="border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
      {{ $t('dca.syntheticHistoryWarning') }}
    </div>

    <!-- Market Indicators Card -->
    <div class="app-panel p-4 transition-colors">
       <div class="mb-3 flex flex-wrap items-start justify-between gap-3">
       <h3 class="flex items-center text-sm font-bold text-stone-950 dark:text-white">
         <ChartBarIcon class="mr-1.5 h-5 w-5 text-[#0f6b4f] dark:text-emerald-300" />
         {{ $t('dca.market') }}
       </h3>
       <button type="button" class="app-button-secondary app-touch-target" :disabled="marketData.loading" @click="fetchMarketIndicators">{{ marketData.loading ? $t('dca.marketLoading') : $t('dca.refreshMarket') }}</button>
       </div>
       <div v-if="marketData.error" role="alert" class="mb-4 border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">{{ marketData.error }}</div>
       
       <div class="dca-market-grid grid gap-4">
          <!-- 当前币价 -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.currentPrice') }}</div>
             <div class="text-2xl font-bold text-[#0f6b4f] dark:text-emerald-300">{{ result ? formatMoney(result.current_price, result.pricing_currency || 'USDT') : marketData.currentPrice != null ? formatMoney(marketData.currentPrice, marketData.pricingCurrency) : '--' }}</div>
             <div v-if="result?.pricing_symbol || marketData.pricingSymbol" class="text-xs text-gray-500 mt-0.5">{{ result?.pricing_symbol || marketData.pricingSymbol }}</div>
          </div>
          
          <!-- RSI -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.rsi14') }}</div>
             <div class="text-2xl font-bold text-[#8a6a24] dark:text-purple-400">{{ marketData.rsi || '--' }}</div>
          </div>
          
          <!-- 恐惧贪婪指数 -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.fgIndex') }}</div>
             <div class="text-2xl font-bold" :class="sentimentClass">
               {{ marketData.sentiment ?? '--' }}
             </div>
             <div class="text-xs text-gray-500 mt-0.5">{{ marketData.sentimentLabel || '' }}</div>
          </div>
       </div>
       <p v-if="marketData.updatedAt" class="mt-4 text-right text-xs text-stone-500 dark:text-slate-400">{{ $t('dca.marketUpdated', { time: new Date(marketData.updatedAt).toLocaleString() }) }}</p>
    </div>

    <template v-if="result">
    <div class="app-panel p-4 transition-colors">
       <h3 class="mb-3 flex items-center border-b border-stone-200 pb-2 text-sm font-bold text-stone-950 dark:border-slate-700 dark:text-white">
         <WalletIcon class="mr-1.5 h-5 w-5 text-[#8a6a24] dark:text-yellow-400" />
         {{ $t('dca.asset') }}
       </h3>
       
       <div class="dca-result-metrics grid gap-4">
          <!-- 1. 平均成本 -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.avgCost') }}</div>
             <div class="text-xl font-bold text-yellow-600 dark:text-yellow-400">{{ formatMoney(result.average_cost, result.pricing_currency || 'USDT') }}</div>
          </div>
          
          <!-- 2. ROI -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.roi') }}</div>
             <div class="text-xl font-bold" :class="isPositiveRoi ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">
               {{ (result.roi || 0).toFixed(2) }}%
             </div>
          </div>
          
          <!-- 3. 总投入 -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.totalInvested') }}</div>
             <div class="text-xl font-bold text-gray-900 dark:text-white">{{ formatMoney(result.total_invested, result.pricing_currency || 'USDT') }}</div>
          </div>
          
          <!-- 4. 当前价值 -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.currentValue') }}</div>
             <div class="text-xl font-bold text-gray-900 dark:text-white">{{ formatMoney(result.final_value, result.pricing_currency || 'USDT') }}</div>
          </div>
          
          <!-- 5. 持仓数量 -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.holdings') }}</div>
             <div class="text-xl font-bold text-gray-900 dark:text-white">{{ (result.total_coins || 0).toFixed(6) }}</div>
          </div>
          
          <!-- 6. 定投天数 -->
          <div class="text-center">
             <div class="mb-1 text-xs uppercase text-stone-500 dark:text-slate-400">{{ $t('dca.dcaDays') }}</div>
             <div class="text-xl font-bold text-gray-700 dark:text-gray-300">{{ result.total_days || 0 }}</div>
          </div>
       </div>
    </div>

    <!-- Charts Area - 3 Charts Layout (Always visible) -->
    <div class="dca-chart-grid grid gap-4">
        <!-- 1. ROI Trend Chart -->
        <div class="app-panel p-3 transition-colors">
            <h3 class="mb-2 text-xs font-bold text-stone-500 dark:text-slate-400">{{ $t('dca.roiTrend') }}</h3>
            <div class="h-72">
                <canvas ref="roiChartCanvas" role="img" :aria-label="$t('dca.roiTrend')"></canvas>
            </div>
        </div>
        
        <!-- 2. Price vs Avg Cost Chart -->
        <div class="app-panel p-3 transition-colors">
            <h3 class="mb-2 text-xs font-bold text-stone-500 dark:text-slate-400">{{ $t('dca.priceVsCost') }}</h3>
            <div class="h-72">
                <canvas ref="priceChartCanvas" role="img" :aria-label="$t('dca.priceVsCost')"></canvas>
            </div>
        </div>
        
        <!-- 3. Daily Investment Amount Chart -->
        <div class="app-panel p-3 transition-colors">
            <h3 class="mb-2 text-xs font-bold text-stone-500 dark:text-slate-400">{{ $t('dca.dailyAmount') }}</h3>
            <div class="h-72">
                <canvas ref="investmentChartCanvas" role="img" :aria-label="$t('dca.dailyAmount')"></canvas>
            </div>
        </div>
    </div>
    </template>
    <div v-else class="app-panel flex min-h-[18rem] items-center justify-center p-8 text-center">
      <div class="max-w-md"><h3 class="app-section-title">{{ $t('dca.emptyResultTitle') }}</h3><p class="app-subtitle mt-2">{{ $t('dca.emptyResultDescription') }}</p></div>
    </div>

    </div>
  </div>
</template>

<script setup>
import { BanknotesIcon, ChartBarIcon, WalletIcon } from '@heroicons/vue/24/outline'
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
