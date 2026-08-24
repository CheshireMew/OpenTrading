<template>
  <div class="app-page">
    <div class="app-page-inner-wide flex flex-col space-y-6">
    <section class="app-hero-panel px-6 py-7">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <button class="app-button-secondary inline-flex items-center px-3 py-1 text-xs" @click="page.seedPanel.goBackToCenter">
            {{ $t('backtest.backToCenter') }}
          </button>
          <div class="app-eyebrow mt-4">{{ $t('backtest.editorEyebrow') }}</div>
          <h1 class="app-title mt-3">{{ $t('backtest.editorTitle') }}</h1>
          <p class="app-subtitle mt-2 max-w-3xl">{{ $t('backtest.editorSubtitle') }}</p>
        </div>
        <div class="border border-stone-200 bg-[#fbfaf7] px-4 py-3 text-sm text-stone-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
          {{ $t('backtest.editorHint') }}
        </div>
      </div>
    </section>

    <div class="grid grid-cols-1 2xl:grid-cols-[340px_minmax(0,1fr)] gap-6">
      <aside class="app-panel space-y-5 p-6">
        <div>
          <div class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-400 dark:text-gray-500">{{ $t('backtest.editorSeed') }}</div>
          <h2 class="mt-2 text-xl font-semibold text-stone-950 dark:text-white">{{ $t('backtest.editorSeedTitle') }}</h2>
          <p class="mt-2 text-sm leading-6 text-stone-500 dark:text-gray-400">{{ $t('backtest.editorSeedSubtitle') }}</p>
        </div>

        <div class="space-y-3">
          <div>
            <label class="label">{{ $t('backtest.strategy') }}</label>
            <select v-model="page.seedPanel.config.strategy_key" class="input" @change="page.seedPanel.syncStrategyVersion">
              <option v-for="item in page.seedPanel.strategies" :key="item.key" :value="item.key">{{ item.name }}</option>
            </select>
          </div>
          <div>
            <label class="label">{{ $t('backtest.version') }}</label>
            <select v-model="page.seedPanel.config.strategy_version" class="input">
              <option v-for="item in page.seedPanel.selectedStrategyVersions" :key="item?.version ?? String(item)" :value="item?.version">
                v{{ item?.version ?? '-' }} · {{ item?.name ?? '-' }}
              </option>
            </select>
          </div>
        </div>

        <div v-if="page.seedPanel.selectedStrategy" class="border border-stone-200 bg-[#fbfaf7] px-4 py-4 text-sm text-stone-600 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300">
          <div class="font-semibold text-stone-950 dark:text-white">{{ page.seedPanel.selectedStrategy.name }}</div>
          <div class="mt-2">{{ page.seedPanel.selectedStrategy.description || '-' }}</div>
          <div class="mt-3 text-xs text-gray-500 dark:text-gray-400">
            {{ $t('backtest.selectedVersion') }}: v{{ page.seedPanel.config.strategy_version }} · {{ page.seedPanel.selectedVersion?.name || '-' }}
          </div>
          <div v-if="page.seedPanel.strategyCapabilityHint" class="mt-2 text-xs text-amber-600 dark:text-amber-300">
            {{ page.seedPanel.strategyCapabilityHint }}
          </div>
        </div>

        <div class="space-y-3">
          <button class="btn-primary w-full" :disabled="!page.seedPanel.canCopyCurrentStrategy" @click="page.seedPanel.openCopySeed">{{ $t('backtest.fillFromCurrent') }}</button>
          <button class="btn-secondary w-full" @click="page.seedPanel.openBlankSeed">{{ $t('backtest.startBlankBuilder') }}</button>
        </div>
      </aside>

      <BacktestVersionEditor :panel="page.editorPanel" />
    </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import BacktestVersionEditor from '@/components/backtest/BacktestVersionEditor.vue'
import { useBacktestEditorPage } from '@/modules/backtest/useBacktestEditorPage'

const page = useBacktestEditorPage()
</script>

<style scoped>
.btn-primary { @apply app-button-primary py-2.5; }
.btn-secondary { @apply app-button-secondary py-2.5; }
</style>
