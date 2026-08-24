<template>
  <div v-if="panel.show" class="editor-section">
    <div class="section-title">{{ $t('backtest.indicatorRegistry') }}</div>
    <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
      <div>
        <label class="label">{{ $t('backtest.indicatorKey') }}</label>
        <input v-model="panel.indicatorDraft.key" class="input" type="text" />
      </div>
      <div>
        <label class="label">{{ $t('backtest.indicatorName') }}</label>
        <input v-model="panel.indicatorDraft.name" class="input" type="text" />
      </div>
    </div>
    <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
      <div>
        <label class="label">{{ $t('backtest.indicatorEngine') }}</label>
        <select v-model="panel.indicatorDraft.engine_key" class="input" @change="panel.syncIndicatorDraftEngine">
          <option v-for="engine in panel.indicatorEngines" :key="engine?.key ?? String(engine)" :value="engine?.key">
            {{ engine?.name ?? engine?.key ?? '-' }}
          </option>
        </select>
      </div>
      <div>
        <label class="label">{{ $t('backtest.description') }}</label>
        <input v-model="panel.indicatorDraft.description" class="input" type="text" />
      </div>
    </div>
    <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
      <div v-for="param in panel.indicatorDraft.params" :key="param?.key ?? String(param)" class="editor-card space-y-2">
        <div class="font-semibold text-gray-900 dark:text-white">{{ param.label }}</div>
        <input v-model="param.label" class="input" type="text" />
        <div class="grid grid-cols-2 gap-2">
          <input v-model.number="param.default" class="input" type="number" step="0.1" />
          <input v-model.number="param.step" class="input" type="number" step="0.1" />
        </div>
        <div class="grid grid-cols-2 gap-2">
          <input v-model.number="param.min" class="input" type="number" step="0.1" />
          <input v-model.number="param.max" class="input" type="number" step="0.1" />
        </div>
      </div>
    </div>
    <button class="btn-primary w-full" @click="panel.createIndicator">{{ $t('backtest.saveIndicator') }}</button>
  </div>
</template>

<script setup lang="ts">
import type { BacktestIndicatorCreatorPanel } from '@/modules/backtest/editorViewTypes'

const props = defineProps<{ panel: BacktestIndicatorCreatorPanel }>()
const panel = props.panel
</script>

