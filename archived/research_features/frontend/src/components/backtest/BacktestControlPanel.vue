<template>
  <div class="app-panel p-6 transition-colors">
    <h2 class="mb-4 text-xl font-semibold text-stone-950 dark:text-white">{{ $t('backtest.new') }}</h2>
    <div class="space-y-5">
      <section class="space-y-3">
        <div>
          <label class="label">{{ $t('backtest.strategy') }}</label>
          <select v-model="panel.config.strategy_key" class="input" @change="panel.syncStrategyVersion">
            <option v-for="item in panel.strategies" :key="item.key" :value="item.key">{{ item.name }}</option>
          </select>
        </div>
        <div>
          <label class="label">{{ $t('backtest.version') }}</label>
          <select v-model="panel.config.strategy_version" class="input">
            <option v-for="item in panel.selectedStrategyVersions" :key="item?.version ?? String(item)" :value="item?.version">
              v{{ item?.version ?? '-' }} · {{ item?.name ?? '-' }}
            </option>
          </select>
        </div>
        <div
          v-if="panel.selectedStrategy"
          class="border border-stone-200 bg-[#fbfaf7] px-3 py-3 text-sm text-stone-600 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300"
        >
          <div class="font-semibold text-stone-950 dark:text-white">{{ panel.selectedStrategy.name }}</div>
          <div class="mt-1">{{ panel.selectedStrategy.description || '-' }}</div>
          <div class="mt-2 text-xs text-gray-500 dark:text-gray-400">
            {{ $t('backtest.selectedVersion') }}: v{{ panel.config.strategy_version }} · {{ panel.selectedVersion?.name || '-' }}
          </div>
          <div v-if="panel.strategyCapabilityHint" class="mt-2 text-xs text-amber-600 dark:text-amber-300">
            {{ panel.strategyCapabilityHint }}
          </div>
        </div>
        <div class="flex gap-2">
          <button class="btn-secondary flex-1" :disabled="!panel.canCopyCurrentStrategy" @click="panel.openCopyEditor">{{ $t('backtest.fillFromCurrent') }}</button>
          <button class="btn-secondary flex-1" @click="panel.openBlankEditor">{{ $t('backtest.startBlankBuilder') }}</button>
        </div>
      </section>

      <BacktestRunForm :panel="panel" />
    </div>
  </div>
</template>

<script setup lang="ts">
import BacktestRunForm from '@/components/backtest/BacktestRunForm.vue'
import type { BacktestControlPanelView } from '@/modules/backtest/viewTypes'

const props = defineProps<{ panel: BacktestControlPanelView }>()
const panel = props.panel
</script>

