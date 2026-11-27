<template>
  <div class="app-appearance-controls">
    <button type="button" @click="toggleTheme" :aria-label="themeLabel" :title="themeLabel" data-app-action="theme">
      <SunIcon v-if="theme==='dark'" aria-hidden="true" /><MoonIcon v-else aria-hidden="true" />
    </button>
    <button type="button" @click="toggleLocale" :aria-label="t('lang.toggle')" :title="t('lang.toggle')" data-app-action="language">
      <LanguageIcon aria-hidden="true" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { LanguageIcon, MoonIcon, SunIcon } from '@heroicons/vue/24/outline'
import { useTheme } from '@/composables/useTheme'
import { setAppLocale, toggleAppLocale } from '@/i18n/config'

const { theme, toggleTheme } = useTheme(), { locale, t } = useI18n()
const themeLabel = computed(() => t(theme.value==='dark' ? 'theme.light' : 'theme.dark'))
const toggleLocale = () => setAppLocale(locale, toggleAppLocale(locale.value))
</script>

<style scoped>
.app-appearance-controls{display:flex;align-items:center;gap:12px;flex-shrink:0}
.app-appearance-controls>button{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;min-height:32px;padding:6px;border:0;border-radius:4px;color:var(--ui-text);background:transparent;cursor:pointer}
.app-appearance-controls>button:hover{background:var(--ui-hover)}
.app-appearance-controls>button:focus-visible{outline:2px solid var(--ui-accent);outline-offset:1px}
svg{width:18px;height:18px;stroke-width:1.25}
@media(pointer:coarse){.app-appearance-controls>button{width:44px;height:44px;min-height:44px}}
</style>
