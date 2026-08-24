<template>
  <div class="app-page">
    <div class="app-page-inner-wide flex flex-col space-y-6">
    <section class="app-hero-panel px-6 py-7">
      <div class="app-eyebrow">{{ $t('backtest.centerEyebrow') }}</div>
      <div class="mt-3 flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 class="app-title">{{ $t('backtest.centerTitle') }}</h1>
          <p class="app-subtitle mt-2 max-w-3xl">{{ $t('backtest.centerSubtitle') }}</p>
        </div>
        <div class="border border-stone-200 bg-[#fbfaf7] px-4 py-3 text-sm text-stone-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
          {{ $t('backtest.centerHint') }}
        </div>
      </div>
    </section>

    <div v-if="page.ready" class="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_420px] gap-6 items-start">
      <BacktestControlPanel :panel="page.controlPanel" />
      <BacktestHistoryPanel :panel="page.historyPanel" />
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import BacktestControlPanel from '@/components/backtest/BacktestControlPanel.vue'
import BacktestHistoryPanel from '@/components/backtest/BacktestHistoryPanel.vue'
import { useBacktestPage } from '@/modules/backtest/useBacktestPage'

const page = useBacktestPage()
</script>
