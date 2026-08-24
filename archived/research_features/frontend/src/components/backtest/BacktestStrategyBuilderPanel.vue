<template>
  <div v-if="panel.editorContract && panel.versionDraft.config && (panel.editorTemplate || panel.useGlobalIndicatorCatalog)" class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
    <div class="space-y-4">
      <div class="editor-section">
        <div class="section-title">{{ $t('backtest.executionConfig') }}</div>
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <label class="label">{{ $t('backtest.marketType') }}</label>
            <select v-model="panel.versionDraft.config.execution.market_type" class="input" @change="panel.syncExecutionConfig">
              <option v-for="item in panel.editorContract.market_type_options" :key="item.key" :value="item.key">
                {{ item.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="label">{{ $t('backtest.positionDirection') }}</label>
            <select v-model="panel.versionDraft.config.execution.direction" class="input" :disabled="panel.versionDraft.config.execution.market_type === 'spot'">
              <option v-for="item in panel.editorContract.direction_options" :key="item.key" :value="item.key">
                {{ item.label }}
              </option>
            </select>
          </div>
        </div>
        <p class="text-xs text-gray-500 dark:text-gray-400">{{ $t('backtest.executionConfigHint') }}</p>
      </div>

      <div class="editor-section">
        <div class="flex items-center justify-between gap-3">
          <div class="section-title">{{ $t('backtest.indicatorConfig') }}</div>
          <div class="flex gap-2">
            <select v-model="panel.newIndicatorType" class="input !w-[180px]">
              <option v-for="indicator in panel.availableIndicators" :key="indicator?.key ?? String(indicator)" :value="indicator?.key">
                {{ indicator?.name ?? indicator?.key ?? '-' }}
              </option>
            </select>
            <button class="btn-secondary px-3" @click="panel.addIndicator">{{ $t('backtest.addIndicator') }}</button>
          </div>
        </div>
        <div v-for="indicator in panel.indicatorCards" :key="indicator.id" class="editor-card space-y-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="font-semibold text-gray-900 dark:text-white">{{ indicator.label }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ indicator.typeLabel }} · {{ indicator.timeframeLabel }}</div>
            </div>
            <button class="btn-danger" @click="panel.removeIndicator(indicator.id)">{{ $t('backtest.remove') }}</button>
          </div>
          <div>
            <label class="label">{{ $t('backtest.indicatorTimeframe') }}</label>
            <select v-model="panel.versionDraft.config.indicators[indicator.id].timeframe" class="input">
              <option v-for="item in panel.editorContract.timeframe_options" :key="item.key" :value="item.key">
                {{ item.label }}
              </option>
            </select>
          </div>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div v-for="param in indicator.params" :key="param?.key ?? String(param)">
              <label v-if="param.type !== 'bool'" class="label">{{ param.label }}</label>
              <input
                v-if="param.type !== 'bool'"
                v-model.number="panel.versionDraft.config.indicators[indicator.id].params[param.key]"
                class="input"
                type="number"
                :min="param.min ?? undefined"
                :max="param.max ?? undefined"
                :step="param.step ?? undefined"
              />
              <label v-else class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
                <input v-model="panel.versionDraft.config.indicators[indicator.id].params[param.key]" type="checkbox" />
                <span>{{ param.label }}</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="border border-[#e4ded3] bg-white p-3 dark:border-gray-700 dark:bg-gray-900/50">
        <div class="text-xs font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ $t('backtest.templateRules') }}</div>
        <div class="mt-2 text-sm text-gray-700 dark:text-gray-200">
          <div class="font-semibold">{{ $t('backtest.availableIndicators') }}</div>
          <div class="mt-1">{{ panel.availableIndicators.map((item) => item?.name || item?.key || '-').join(' / ') || '-' }}</div>
        </div>
        <div class="mt-3 text-sm text-gray-700 dark:text-gray-200">
          <div class="font-semibold">{{ $t('backtest.availableOperators') }}</div>
          <div class="mt-1">{{ panel.operatorOptions.map((item) => item?.label || item?.key || '-').join(' / ') || '-' }}</div>
        </div>
        <div class="mt-3 text-sm text-gray-700 dark:text-gray-200">
          <div class="font-semibold">{{ $t('backtest.groupLogic') }}</div>
          <div class="mt-1">{{ panel.groupLogicOptions.map((item) => item?.label || item?.key || '-').join(' / ') || '-' }}</div>
        </div>
      </div>
    </div>

    <div class="space-y-4">
      <div class="editor-section space-y-4">
        <div class="section-title">{{ $t('backtest.regimeBuilder') }}</div>

        <BacktestBranchRuleEditor
          :branch="panel.versionDraft.config.trend"
          :title="$t('backtest.trendBranch')"
          :hint="$t('backtest.trendBranchHint')"
          :enabled-label="$t('backtest.enabled')"
          :long-short="panel.versionDraft.config.execution.direction === 'long_short'"
          :rule-titles="ruleTitles"
          :editor-contract="panel.editorContract"
          :source-options="panel.sourceOptions"
          :indicator-source-options="panel.indicatorSourceOptions"
          :operator-options="panel.operatorOptions"
          :group-logic-options="panel.groupLogicOptions"
        />

        <BacktestBranchRuleEditor
          :branch="panel.versionDraft.config.range"
          :title="$t('backtest.rangeBranch')"
          :hint="$t('backtest.rangeBranchHint')"
          :enabled-label="$t('backtest.enabled')"
          :long-short="panel.versionDraft.config.execution.direction === 'long_short'"
          :rule-titles="ruleTitles"
          :editor-contract="panel.editorContract"
          :source-options="panel.sourceOptions"
          :indicator-source-options="panel.indicatorSourceOptions"
          :operator-options="panel.operatorOptions"
          :group-logic-options="panel.groupLogicOptions"
        />
      </div>
      <div class="editor-section">
        <div class="section-title">{{ $t('backtest.riskPanel') }}</div>
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <label class="label">{{ $t('backtest.stoplossLabel') }}</label>
            <input v-model.number="panel.versionDraft.config.risk.stoploss" class="input" type="number" step="0.001" />
          </div>
          <div class="editor-card space-y-2">
            <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
              <input v-model="panel.versionDraft.config.risk.trailing.enabled" type="checkbox" />
              <span>{{ $t('backtest.trailingStop') }}</span>
            </label>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="label">{{ $t('backtest.trailingPositive') }}</label>
                <input v-model.number="panel.versionDraft.config.risk.trailing.positive" class="input" type="number" step="0.001" />
              </div>
              <div>
                <label class="label">{{ $t('backtest.trailingOffset') }}</label>
                <input v-model.number="panel.versionDraft.config.risk.trailing.offset" class="input" type="number" step="0.001" />
              </div>
            </div>
            <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
              <input v-model="panel.versionDraft.config.risk.trailing.only_offset_reached" type="checkbox" />
              <span>{{ $t('backtest.trailingOffsetOnly') }}</span>
            </label>
          </div>
        </div>
        <div class="editor-card space-y-3">
          <div class="flex items-center justify-between gap-3">
            <div class="font-semibold text-gray-900 dark:text-white">{{ $t('backtest.roiTargets') }}</div>
            <button class="btn-secondary px-3" @click="panel.addRoiTarget">{{ $t('backtest.addRoiTarget') }}</button>
          </div>
          <div v-for="target in panel.versionDraft.config.risk.roi_targets" :key="target.id" class="grid grid-cols-[1fr_1fr_auto] gap-2">
            <input v-model.number="target.minutes" class="input" type="number" min="0" step="1" />
            <input v-model.number="target.profit" class="input" type="number" step="0.001" />
            <button class="btn-danger" @click="panel.removeRoiTarget(target.id)">{{ $t('backtest.remove') }}</button>
          </div>
        </div>
        <div class="editor-card space-y-3">
          <div class="flex items-center justify-between gap-3">
            <div class="font-semibold text-gray-900 dark:text-white">{{ $t('backtest.partialExits') }}</div>
            <button class="btn-secondary px-3" @click="panel.addPartialExit">{{ $t('backtest.addPartialExit') }}</button>
          </div>
          <div v-for="item in panel.versionDraft.config.risk.partial_exits" :key="item.id" class="grid grid-cols-[1fr_1fr_auto] gap-2">
            <input v-model.number="item.profit" class="input" type="number" step="0.001" />
            <input v-model.number="item.size_pct" class="input" type="number" min="1" max="100" step="1" />
            <button class="btn-danger" @click="panel.removePartialExit(item.id)">{{ $t('backtest.remove') }}</button>
          </div>
        </div>
      </div>

      <div class="editor-section">
        <div class="text-xs font-bold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ $t('backtest.parameterSpacePanel') }}</div>
        <div v-for="field in panel.optimizableTargets" :key="field.path">
          <label class="label">{{ field.label }}</label>
          <input v-model="panel.versionDraft.parameterSpaceValues[field.path]" class="input" type="text" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import BacktestBranchRuleEditor from '@/components/backtest/BacktestBranchRuleEditor.vue'
import type { BacktestStrategyBuilderPanel } from '@/modules/backtest/editorViewTypes'

const props = defineProps<{ panel: BacktestStrategyBuilderPanel }>()
const panel = props.panel
const { t } = useI18n()

const ruleTitles = computed(() => ({
  regime: t('backtest.regimeRules'),
  longEntry: t('backtest.longEntryRules'),
  longExit: t('backtest.longExitRules'),
  shortEntry: t('backtest.shortEntryRules'),
  shortExit: t('backtest.shortExitRules'),
}))
</script>

