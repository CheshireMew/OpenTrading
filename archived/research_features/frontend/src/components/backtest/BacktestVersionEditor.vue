<template>
  <div v-if="panel.showVersionEditor && panel.versionDraft.config" class="space-y-4 border border-[#e4ded3] bg-[#fbfaf7] p-4 dark:border-gray-700 dark:bg-gray-900/40">
    <BacktestVersionMetaPanel :panel="panel.metaPanel" />
    <BacktestIndicatorCreatorPanel :panel="panel.indicatorCreatorPanel" />
    <BacktestTemplateCreatorPanel :panel="panel.templateCreatorPanel" />
    <BacktestStrategyBuilderPanel :panel="panel.strategyBuilderPanel" />

    <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
      <input v-model="panel.versionDraft.make_default" type="checkbox" />
      <span>{{ $t('backtest.makeDefault') }}</span>
    </label>
    <button class="btn-primary w-full" @click="panel.createStrategyVersion">{{ $t('backtest.saveVersion') }}</button>
  </div>
</template>

<script setup lang="ts">
import BacktestIndicatorCreatorPanel from '@/components/backtest/BacktestIndicatorCreatorPanel.vue'
import BacktestStrategyBuilderPanel from '@/components/backtest/BacktestStrategyBuilderPanel.vue'
import BacktestTemplateCreatorPanel from '@/components/backtest/BacktestTemplateCreatorPanel.vue'
import BacktestVersionMetaPanel from '@/components/backtest/BacktestVersionMetaPanel.vue'
import type { BacktestVersionEditorPanel } from '@/modules/backtest/editorViewTypes'

const props = defineProps<{ panel: BacktestVersionEditorPanel }>()
const panel = props.panel
</script>

