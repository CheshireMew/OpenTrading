<template>
  <div class="app-page">
    <div class="app-page-inner-wide flex min-h-full flex-col">
    <!-- Configuration Panel -->
    <div class="app-hero-panel flex flex-wrap items-end gap-4 transition-colors">
      <div class="flex-1 min-w-[200px]">
        <label class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('compare.symbolA') }}</label>
        <SymbolSearchBox v-model="config.symbolA" :aria-label="$t('compare.symbolA')" output-mode="base" @select="handleSymbolSelect" />
      </div>

      <div class="flex items-center justify-center p-2">
         <span class="text-stone-400 dark:text-slate-500 font-bold text-xl">VS</span>
      </div>

      <div class="flex-1 min-w-[200px]">
        <label class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('compare.symbolB') }}</label>
        <SymbolSearchBox v-model="config.symbolB" :aria-label="$t('compare.symbolB')" output-mode="base" @select="handleSymbolSelect" />
      </div>

      <div class="w-32">
        <label for="compare-timeframe" class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('compare.timeframe') }}</label>
        <select id="compare-timeframe" v-model="config.timeframe" class="app-control w-full">
          <option value="5m">{{ $t('compare.tf.5m') }}</option>
          <option value="15m">{{ $t('compare.tf.15m') }}</option>
          <option value="1h">{{ $t('compare.tf.1h') }}</option>
          <option value="4h">{{ $t('compare.tf.4h') }}</option>
          <option value="1d">{{ $t('compare.tf.1d') }}</option>
          <option value="1w">{{ $t('compare.tf.1w') }}</option>
          <option value="1M">{{ $t('compare.tf.1M') }}</option>
        </select>
      </div>

      <div class="w-32">
        <label for="compare-days" class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-slate-400">{{ $t('compare.days') }}</label>
        <input id="compare-days" v-model.number="config.days" type="number" min="1" max="90" class="app-control w-full" />
      </div>

      <button @click="fetchComparisonData" :disabled="loading || !canCompare" class="app-button-primary flex items-center px-6 py-2">
        <span v-if="loading" class="mr-2 animate-spin">&#10227;</span>
        {{ loading ? $t('compare.analyzing') : $t('compare.compare') }}
      </button>
    </div>

    <div v-if="errorMessage" role="alert" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
      {{ errorMessage }}
    </div>

    <!-- Charts Grid -->
    <div class="grid min-h-[600px] flex-1 grid-cols-1 gap-4 lg:grid-cols-2 lg:grid-rows-2">

      <!-- Chart A -->
      <div class="app-panel relative flex flex-col overflow-hidden transition-colors">
        <div class="absolute top-2 left-2 z-10 border border-[#b8d2c4] bg-white/90 px-2 py-1 text-sm font-bold text-[#0f6b4f] dark:border-emerald-500/30 dark:bg-gray-900/80 dark:text-emerald-300">
          {{ symbolLabel(config.symbolA) }}
        </div>
        <TradingViewChart
          ref="chartARef"
          :data="dataA"
          :colors="{ ...chartColors, upColor: '#3b82f6', downColor: '#1d4ed8' }"
        />
      </div>

      <!-- Chart B -->
      <div class="app-panel relative flex flex-col overflow-hidden transition-colors">
        <div class="absolute top-2 left-2 z-10 border border-[#efc4b5] bg-white/90 px-2 py-1 text-sm font-bold text-[#c84c28] dark:border-purple-500/30 dark:bg-gray-900/80 dark:text-purple-400">
          {{ symbolLabel(config.symbolB) }}
        </div>
        <TradingViewChart
          ref="chartBRef"
          :data="dataB"
          :colors="{ ...chartColors, upColor: '#a855f7', downColor: '#7e22ce' }"
        />
      </div>

      <!-- Ratio Chart (Full Width) -->
      <div class="app-panel relative flex flex-col overflow-hidden transition-colors lg:col-span-2">
        <div class="absolute top-2 left-2 z-10 border border-[#b8d2c4] bg-white/90 px-2 py-1 text-sm font-bold text-[#0f6b4f] dark:border-green-500/30 dark:bg-gray-900/80 dark:text-green-400">
          {{ $t('compare.ratio') }}: {{ config.symbolA }} / {{ config.symbolB }}
        </div>
        <TradingViewChart
          ref="chartRatioRef"
          :data="dataRatio"
          chart-type="area"
          :colors="chartColors"
        />
      </div>

    </div>
    </div>
  </div>
</template>

<script setup>
import TradingViewChart from '@/components/TradingViewChart.vue'
import SymbolSearchBox from '@/components/SymbolSearchBox.vue'
import { useComparePage } from '@/modules/tools'

const {
  chartColors,
  config,
  loading,
  errorMessage,
  dataA,
  dataB,
  dataRatio,
  chartARef,
  chartBRef,
  chartRatioRef,
  fetchComparisonData,
  handleSymbolSelect,
  symbolLabel,
  canCompare,
} = useComparePage()
</script>
