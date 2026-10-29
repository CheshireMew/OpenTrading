<template>
  <nav class="research-navigation" :aria-label="t('nav.researchSection')">
    <RouterLink v-for="item in items" :key="item.path" :to="item.path">{{ t(item.label) }}</RouterLink>
  </nav>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
const items = [
  { path: '/research', label: 'nav.research' },
  { path: '/research/signals', label: 'nav.signalReview' },
  { path: '/research/screeners', label: 'nav.screeners' },
  { path: '/research/reports', label: 'nav.reports' },
  { path: '/research/backtests', label: 'nav.localBacktests' },
  { path: '/research/parameter-sweeps', label: 'nav.parameterSweeps' },
  { path: '/research/results', label: 'nav.researchResults' },
]
</script>
<style scoped>
.research-navigation { display: flex; gap: 4px; padding: 12px 32px 0; overflow-x: auto; border-bottom: 1px solid var(--ui-border); scrollbar-width: thin; }
a { display: inline-flex; flex: 0 0 auto; align-items: center; min-height: 44px; padding: 8px 12px 12px; border-bottom: 2px solid transparent; font-size: 13px; color: var(--ui-muted); }
a:hover { color: var(--ui-title); }
a.router-link-exact-active { border-bottom-color: var(--ui-accent); color: var(--ui-accent); font-weight: 600; }
@media (max-width: 767px) { .research-navigation { padding: 0 12px; } }
</style>
