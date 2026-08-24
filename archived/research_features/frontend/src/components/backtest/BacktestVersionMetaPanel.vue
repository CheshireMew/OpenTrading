<template>
  <section class="space-y-4">
    <div class="section-title">{{ $t('backtest.versionEditor') }}</div>
    <div class="grid grid-cols-2 gap-3">
      <div>
        <label class="label">{{ $t('backtest.strategyKey') }}</label>
        <input v-model="panel.versionDraft.key" class="input" type="text" />
      </div>
      <div>
        <label class="label">{{ $t('backtest.versionName') }}</label>
        <input v-model="panel.versionDraft.name" class="input" type="text" />
      </div>
    </div>
    <div class="grid grid-cols-2 gap-3">
      <div>
        <label class="label">{{ $t('backtest.template') }}</label>
        <select v-model="panel.versionDraft.template" class="input" @change="panel.syncVersionDraftTemplate">
          <option value="">{{ $t('backtest.customTemplateMode') }}</option>
          <option v-for="item in panel.templates" :key="item?.template ?? String(item)" :value="item?.template">
            {{ item?.name ?? item?.template ?? '-' }}
          </option>
        </select>
      </div>
      <div>
        <label class="label">{{ $t('backtest.category') }}</label>
        <input :value="panel.categoryLabel(panel.versionDraft.category)" class="input" type="text" readonly />
      </div>
    </div>
    <div>
      <label class="label">{{ $t('backtest.description') }}</label>
      <input v-model="panel.versionDraft.description" class="input" type="text" />
    </div>
    <div>
      <label class="label">{{ $t('backtest.notes') }}</label>
      <input v-model="panel.versionDraft.notes" class="input" type="text" />
    </div>

    <div class="flex flex-wrap gap-2">
      <button class="btn-secondary px-3" @click="panel.startBlankBuilder">{{ $t('backtest.startBlankBuilder') }}</button>
      <button class="btn-secondary px-3" @click="panel.toggleIndicatorCreator">{{ $t('backtest.indicatorRegistry') }}</button>
      <button class="btn-secondary px-3" @click="panel.toggleTemplateCreator">{{ $t('backtest.templateCreator') }}</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { BacktestVersionMetaPanel } from '@/modules/backtest/editorViewTypes'

const props = defineProps<{ panel: BacktestVersionMetaPanel }>()
const panel = props.panel
</script>

