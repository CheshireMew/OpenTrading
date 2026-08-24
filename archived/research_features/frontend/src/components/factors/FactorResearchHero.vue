<template>
  <section class="panel p-6">
    <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div class="max-w-4xl">
        <div class="app-eyebrow">{{ $t('factorResearch.eyebrow') }}</div>
        <h1 class="app-title mt-3">{{ $t('factorResearch.title') }}</h1>
        <p class="app-subtitle mt-3">{{ $t('factorResearch.subtitle') }}</p>
      </div>
      <div class="border border-stone-200 bg-[#fbfaf7] px-4 py-3 text-sm text-stone-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
        {{ $t('factorResearch.hint') }}
        <div class="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {{ $t('factorResearch.forwardHorizons') }}: {{ panel.catalog.forward_horizons.length ? panel.catalog.forward_horizons.join(' / ') : '--' }}
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { FactorResearchHeroView } from '@/modules/factors/viewTypes'

const props = defineProps<{ panel: FactorResearchHeroView }>()
const panel = props.panel
</script>

<style scoped>
.panel {
  border: 1px solid #e4ded3;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}

:global(.dark) .panel {
  border-color: #334155;
  background: #1e293b;
}
</style>
