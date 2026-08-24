<template>
  <div class="editor-card space-y-3">
    <div class="flex items-center justify-between gap-3">
      <div>
        <div class="font-semibold text-gray-900 dark:text-white">{{ branch.label || title }}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">{{ hint }}</div>
      </div>
      <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
        <input v-model="branch.enabled" type="checkbox" />
        <span>{{ enabledLabel }}</span>
      </label>
    </div>
    <RuleTreeEditor
      v-for="section in visibleRuleSections"
      :key="section.key"
      :editor-contract="editorContract"
      :node="section.node"
      :title="section.title"
      :source-options="sourceOptions"
      :indicator-source-options="indicatorSourceOptions"
      :operator-options="operatorOptions"
      :group-logic-options="groupLogicOptions"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import RuleTreeEditor from '@/components/RuleTreeEditor.vue'
import type {
  StrategyEditorContractResponse,
  StrategyGroupLogicResponse,
  StrategyOperatorResponse,
  StrategyStateBranchResponse,
} from '@/modules/backtest/contracts'
import type { SourceOption } from '@/modules/backtest/editorTypes'

const props = defineProps<{
  branch: StrategyStateBranchResponse
  title: string
  hint: string
  enabledLabel: string
  longShort: boolean
  ruleTitles: {
    regime: string
    longEntry: string
    longExit: string
    shortEntry: string
    shortExit: string
  }
  editorContract: StrategyEditorContractResponse | null
  sourceOptions: SourceOption[]
  indicatorSourceOptions: SourceOption[]
  operatorOptions: StrategyOperatorResponse[]
  groupLogicOptions: StrategyGroupLogicResponse[]
}>()

const visibleRuleSections = computed(() => [
  { key: 'regime', title: props.ruleTitles.regime, node: props.branch.regime, shortOnly: false },
  { key: 'long_entry', title: props.ruleTitles.longEntry, node: props.branch.long_entry, shortOnly: false },
  { key: 'long_exit', title: props.ruleTitles.longExit, node: props.branch.long_exit, shortOnly: false },
  { key: 'short_entry', title: props.ruleTitles.shortEntry, node: props.branch.short_entry, shortOnly: true },
  { key: 'short_exit', title: props.ruleTitles.shortExit, node: props.branch.short_exit, shortOnly: true },
].filter((section) => props.longShort || !section.shortOnly))
</script>
