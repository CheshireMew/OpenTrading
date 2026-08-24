<template>
  <div class="app-page">
    <div class="app-page-inner-wide flex flex-col space-y-6">
    <section class="app-hero-panel px-6 py-6">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <button class="app-button-secondary inline-flex items-center px-3 py-1 text-xs" @click="page.hero.goBackToCenter">
            {{ $t('backtest.backToCenter') }}
          </button>
          <div class="app-eyebrow mt-4">{{ $t('backtest.detailEyebrow') }}</div>
          <h1 class="app-title mt-3">{{ $t('backtest.detailTitle') }}</h1>
          <p class="app-subtitle mt-2 max-w-3xl">{{ $t('backtest.detailSubtitle') }}</p>
        </div>
        <div v-if="page.hero.selectedRun" class="grid grid-cols-2 gap-3 border border-stone-200 bg-[#fbfaf7] p-4 text-sm text-stone-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100/90">
          <div>
            <div class="text-xs uppercase tracking-wide text-gray-400 dark:text-slate-400">{{ $t('backtest.runMode') }}</div>
            <div class="mt-1 font-semibold">{{ page.hero.isPaperRun ? $t('backtest.paperRunShort') : $t('backtest.runShort') }}</div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wide text-gray-400 dark:text-slate-400">{{ $t('backtest.runStatus') }}</div>
            <div class="mt-1 font-semibold">{{ page.hero.runStatusLabel(page.hero.selectedRun) }}</div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wide text-gray-400 dark:text-slate-400">{{ $t('backtest.symbols') }}</div>
            <div class="mt-1 font-semibold">{{ page.hero.portfolioLabel(page.hero.selectedRun) }}</div>
          </div>
          <div>
            <div class="text-xs uppercase tracking-wide text-gray-400 dark:text-slate-400">{{ $t('backtest.version') }}</div>
            <div class="mt-1 font-semibold">v{{ page.hero.selectedRun?.metadata?.strategy_version || '-' }}</div>
          </div>
        </div>
      </div>
    </section>

    <div v-if="page.hero.selectedRun" class="grid grid-cols-1 2xl:grid-cols-[360px_minmax(0,1fr)] gap-6">
      <BacktestHistoryPanel :panel="page.historyPanel" />
      <BacktestResultPanel :panel="page.resultPanel" />
    </div>

    <section v-else class="border border-dashed border-stone-300 bg-white/70 px-8 py-14 text-center dark:border-gray-700 dark:bg-gray-800/70">
      <h2 class="text-xl font-semibold text-stone-950 dark:text-white">{{ $t('backtest.detailEmptyTitle') }}</h2>
      <p class="mt-3 text-sm text-stone-500 dark:text-gray-400">{{ $t('backtest.detailEmptySubtitle') }}</p>
      <button class="app-button-primary mt-6 inline-flex items-center px-4 py-2" @click="page.hero.goBackToCenter">
        {{ $t('backtest.backToCenter') }}
      </button>
    </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import BacktestHistoryPanel from '@/components/backtest/BacktestHistoryPanel.vue'
import BacktestResultPanel from '@/components/backtest/BacktestResultPanel.vue'
import { useBacktestDetailPage } from '@/modules/backtest/useBacktestDetailPage'

const page = useBacktestDetailPage()
</script>
