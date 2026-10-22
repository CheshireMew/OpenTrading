<template>
  <div class="app-page">
    <div class="app-page-inner-wide space-y-6">
    <!-- Summary Cards -->
    <div class="halving-summary-grid grid gap-6">
      <!-- Card 1: Countdown -->
      <div class="app-card relative overflow-hidden transition-all">
        <h3 class="text-sm font-medium text-stone-500 dark:text-slate-400">{{ $t('halving.nextHalvingEstimate') }}</h3>
        <p class="mt-2 text-3xl font-semibold text-stone-950 dark:text-white">{{ $t('halving.estimatedDate', { date: nextHalvingDate }) }}</p>
        <div class="mt-2 flex items-center text-sm font-medium text-[#0f6b4f] dark:text-emerald-300">
          <ClockIcon class="w-4 h-4 mr-1" />
          <span>{{ daysToHalving }} {{ $t('halving.daysLeft') }}</span>
        </div>
        <p class="mt-3 text-xs leading-5 text-stone-500 dark:text-slate-400">{{ $t('halving.estimateNotice') }}</p>
      </div>

      <!-- Card 2: Price -->
      <div class="app-card relative overflow-hidden transition-all">
        <h3 class="text-sm font-medium text-stone-500 dark:text-slate-400">{{ $t('halving.currentPrice') }}</h3>
        <p class="mt-2 text-3xl font-semibold text-stone-950 dark:text-white">
          {{ formatPrice(currentPrice) }}
        </p>
        <p class="mt-1 text-xs text-stone-500">BTC/USDT</p>
        <p v-if="currentPriceUpdatedAt" class="mt-1 text-xs text-stone-500 dark:text-slate-400">{{ $t('halving.updatedAt', { time: new Date(currentPriceUpdatedAt).toLocaleString() }) }}</p>
      </div>

      <!-- Card 3: Cycle Progress -->
      <div class="halving-progress-card app-card relative overflow-hidden">
        <h3 class="mb-4 text-sm font-medium text-stone-500 dark:text-slate-400">{{ $t('halving.cycleProgress') }}</h3>
        <div class="relative pt-1">
          <div class="mb-2 flex items-center justify-end">
            <div class="text-right">
              <span class="inline-block text-xs font-semibold text-[#0f6b4f] dark:text-emerald-300">
                {{ cycleProgress }}%
              </span>
            </div>
          </div>
          <div class="mb-4 flex h-3 overflow-hidden bg-stone-200 text-xs dark:bg-gray-700">
            <div :style="{ width: cycleProgress + '%' }" class="flex flex-col justify-center whitespace-nowrap bg-[#0f6b4f] text-center text-white shadow-none transition-all duration-1000 ease-out dark:bg-emerald-500"></div>
          </div>
          <div class="flex justify-between text-xs text-stone-400">
            <span>2024-04-20</span>
            <span>Est. 2028-04-17</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="error" role="alert" class="flex flex-col gap-3 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200 sm:flex-row sm:items-center sm:justify-between">
      <span>{{ error }}</span>
      <button type="button" class="app-button-secondary app-touch-target flex-shrink-0" @click="retry">{{ $t('halving.retry') }}</button>
    </div>

    <!-- Main Chart -->
    <div class="app-panel p-6">
      <div class="mb-6 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div>
           <h2 class="flex items-center text-xl font-semibold text-stone-950 dark:text-white">
             <ChartBarIcon class="mr-2 h-6 w-6 text-[#0f6b4f]" />
             {{ $t('halving.chartTitle') }}
           </h2>
           <div v-if="showPhases" class="mt-2 flex flex-wrap items-center gap-2 text-xs text-stone-500 dark:text-slate-400">
                <span class="w-3 h-3 rounded-sm bg-green-500/20 border border-green-500/50"></span>
                <span>{{ $t('halving.accumulation') }}</span>
                <span class="w-3 h-3 rounded-sm bg-orange-500/20 border border-orange-500/50"></span>
                <span>{{ $t('halving.bullRun') }}</span>
           </div>
        </div>

        <div class="flex w-full flex-wrap items-center gap-4 sm:mt-0 sm:w-auto">
           <!-- Scale Toggle -->
           <div class="flex border border-stone-200 bg-white p-1 dark:border-slate-700 dark:bg-gray-700">
               <button 
                  type="button"
                  @click="scaleType = 'logarithmic'" 
                  class="app-touch-target px-3 py-1 text-xs font-medium transition-all"
                  :class="scaleType === 'logarithmic' ? 'bg-[#edf3ee] text-[#0f6b4f] dark:bg-emerald-950/40 dark:text-emerald-300' : 'text-stone-500 hover:text-stone-700 dark:text-gray-400 dark:hover:text-gray-200'"
               >
                  {{ $t('halving.log') }}
               </button>
               <button 
                  type="button"
                  @click="scaleType = 'linear'" 
                  class="app-touch-target px-3 py-1 text-xs font-medium transition-all"
                  :class="scaleType === 'linear' ? 'bg-[#edf3ee] text-[#0f6b4f] dark:bg-emerald-950/40 dark:text-emerald-300' : 'text-stone-500 hover:text-stone-700 dark:text-gray-400 dark:hover:text-gray-200'"
               >
                  {{ $t('halving.linear') }}
               </button>
           </div>

           <!-- Phases Toggle -->
           <label class="inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="showPhases" class="sr-only peer">
              <div class="peer relative h-6 w-11 bg-stone-200 peer-checked:bg-[#0f6b4f] peer-focus:outline-none dark:bg-gray-700 dark:peer-checked:bg-emerald-500 after:absolute after:start-[2px] after:top-[2px] after:h-5 after:w-5 after:border after:border-gray-300 after:bg-white after:transition-all after:content-[''] peer-checked:after:translate-x-full peer-checked:after:border-white rtl:peer-checked:after:-translate-x-full dark:border-gray-600"></div>
              <span class="ms-3 text-sm font-medium text-stone-900 dark:text-gray-300">{{ $t('halving.phases') }}</span>
            </label>
        </div>
      </div>
      
      <div class="app-chart-frame relative h-[420px] w-full sm:h-[520px] lg:h-[600px]">
        <canvas ref="chartCanvas" role="img" :aria-label="$t('halving.chartTitle')"></canvas>
        <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-[#f7f4ed]/80 backdrop-blur-sm dark:bg-gray-900/80">
          <div class="flex flex-col items-center">
             <div class="h-12 w-12 animate-spin rounded-full border-4 border-[#0f6b4f] border-t-transparent"></div>
             <span class="mt-3 text-sm font-medium text-stone-500">{{ $t('halving.loading') }}</span>
          </div>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup>
import { ClockIcon, ChartBarIcon } from '@heroicons/vue/24/outline'
import { useHalvingPage } from '@/modules/market'

const {
  loading,
  error,
  retry,
  chartCanvas,
  currentPrice,
  currentPriceUpdatedAt,
  showPhases,
  scaleType,
  nextHalvingDate,
  daysToHalving,
  cycleProgress,
  formatPrice,
} = useHalvingPage()
</script>
