<template>
  <section class="macro-signals">
    <header class="macro-header">
      <h1 class="app-title">{{ t('nav.macroSignals') }}</h1>
      <nav class="macro-sections" :aria-label="t('macroSignals.sections')">
        <RouterLink v-for="section in MACRO_SECTIONS" :key="section.id" :to="{ name: section.name }">{{ t(section.label) }}</RouterLink>
      </nav>
    </header>
    <RouterView v-slot="{ Component }">
      <KeepAlive><component :is="Component" embedded /></KeepAlive>
    </RouterView>
  </section>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { MACRO_SECTIONS, rememberMacroSection } from '@/modules/market/macroSections'

const { t } = useI18n()
const route = useRoute()
watch(() => route.name, rememberMacroSection, { immediate: true })
</script>

<style scoped>
.macro-signals { min-height: 100%; background: var(--ui-canvas); }
.macro-header { display: flex; align-items: center; flex-wrap: wrap; gap: 16px 28px; padding: 24px 24px 16px; border-bottom: 1px solid var(--ui-border); background: var(--ui-panel); }
.macro-header h1 { flex: 0 0 auto; }
.macro-sections { display: flex; gap: 4px; min-width: 0; max-width: 100%; overflow-x: auto; scrollbar-width: thin; }
.macro-sections a { display: inline-flex; flex: 0 0 auto; align-items: center; justify-content: center; min-height: 36px; padding: 7px 14px; border-radius: 4px; color: var(--ui-muted); font-size: 14px; font-weight: 500; white-space: nowrap; }
.macro-sections a:hover { color: var(--ui-title); background: var(--ui-hover); }
.macro-sections a.router-link-exact-active { color: var(--ui-title); background: var(--ui-elevated); font-weight: 600; }
@media (max-width: 767px) { .macro-header { align-items: flex-start; flex-direction: column; gap: 12px; padding: 20px 16px 12px; } .macro-sections { width: 100%; } .macro-sections a { min-height: 40px; } }
</style>
