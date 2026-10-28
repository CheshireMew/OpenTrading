<template>
  <div class="app-page">
    <div class="app-page-inner-wide flex flex-col gap-6">
      <div>
        <h1 class="app-title">{{ $t('settings.title') }}</h1>
      </div>

      <section class="app-panel p-6">
        <div class="grid gap-4 md:grid-cols-3">
          <label class="block">
            <span class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-gray-400">{{ $t('settings.language') }}</span>
            <AppLanguageSelect />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-gray-400">{{ $t('settings.timezone') }}</span>
            <AppTimezoneSelect />
          </label>
          <label class="block">
            <span class="mb-1 block text-xs font-bold uppercase tracking-wide text-stone-500 dark:text-gray-400">{{ $t('settings.currency') }}</span>
            <AppCurrencySelect />
          </label>
        </div>
        <div class="mt-4 text-sm text-gray-500 dark:text-gray-400">
          {{ $t('settings.currencyRate') }}: {{ ratesAreFallback ? $t('settings.currencyFallback') : formatDateTime(ratesUpdatedAt, { hour12: false }) }}
        </div>
      </section>

      <section class="app-panel p-6">
        <div v-if="llmLoading" role="status" aria-live="polite" class="py-12 text-center app-muted">{{ $t('settings.loading') }}</div>
        <div v-else-if="llmLoadError" role="alert" class="flex flex-wrap items-center justify-between gap-3 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200"><span>{{ llmLoadError }}</span><button type="button" class="app-button-secondary app-touch-target" @click="loadLlmConfig">{{ $t('common.retry') }}</button></div>
        <template v-else>
        <div class="mb-6 flex items-center justify-between gap-4">
          <div>
            <h3 class="app-section-title">{{ $t('settings.llmProvider') }}</h3>
          </div>
          <span
            class="px-3 py-1 text-xs font-semibold"
            :class="form.apiKeySet ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300' : 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300'"
          >
            {{ form.apiKeySet ? $t('settings.apiKeySet') : $t('settings.apiKeyUnset') }}
          </span>
        </div>

        <div class="grid gap-5 md:grid-cols-2">
          <label class="space-y-2">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">{{ $t('settings.provider') }}</span>
            <select v-model="form.provider" class="input" @change="handleProviderChange">
              <option v-for="preset in presets" :key="preset.id" :value="preset.id">
                {{ preset.label }}
              </option>
            </select>
          </label>

          <label class="space-y-2">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">API Key</span>
            <input
              v-model.trim="apiKeyDraft"
              class="input"
              type="password"
              autocomplete="off"
              :placeholder="form.apiKeyPreview || $t('settings.apiKeyPlaceholder')"
            />
          </label>

          <label class="space-y-2">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">Base URL</span>
            <input
              v-model.trim="form.baseUrl"
              class="input"
              type="text"
              :disabled="!isCustomProvider"
            />
          </label>

          <label class="space-y-2">
            <span class="text-sm font-medium text-gray-700 dark:text-gray-300">Model ID</span>
            <input
              v-model.trim="form.modelId"
              class="input"
              type="text"
              :disabled="!isCustomProvider"
            />
          </label>
        </div>

        <label v-if="form.provider === 'deepseek'" class="mt-5 flex items-center justify-between border border-[#e4ded3] px-4 py-3 dark:border-gray-700">
          <span>
            <span class="block text-sm font-medium text-gray-900 dark:text-white">{{ $t('settings.reasoningMode') }}</span>
            <span class="block text-xs text-gray-500 dark:text-gray-400">
              {{ form.reasoningEnabled ? 'deepseek-reasoner' : 'deepseek-chat' }}
            </span>
          </span>
          <input v-model="form.reasoningEnabled" class="h-5 w-5" type="checkbox" @change="applyProviderPreset" />
        </label>

        <div class="mt-6 flex flex-wrap items-center gap-3">
          <button
            type="button"
            class="app-button-primary app-touch-target px-4 py-2"
            :disabled="saving || !canSave"
            @click="saveConfig"
          >
            {{ saving ? $t('settings.saving') : $t('settings.saveConfig') }}
          </button>
          <button v-if="form.apiKeySet" type="button" class="app-button-secondary app-touch-target px-4 py-2 text-rose-600 dark:text-rose-300" :disabled="saving" @click="clearLlmApiKey">
            {{ $t('settings.clearKey') }}
          </button>
          <span v-if="message" role="status" aria-live="polite" class="text-sm text-emerald-600 dark:text-emerald-300">{{ message }}</span>
          <span v-if="error" role="alert" class="text-sm text-rose-600 dark:text-rose-300">{{ error }}</span>
        </div>
        </template>
      </section>

      <section class="app-panel p-6">
        <div v-if="systemLoading" role="status" aria-live="polite" class="py-8 text-center app-muted">{{ $t('settings.loading') }}</div>
        <div v-else-if="systemLoadError" role="alert" class="flex flex-wrap items-center justify-between gap-3 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200"><span>{{ systemLoadError }}</span><button type="button" class="app-button-secondary app-touch-target" @click="loadSystemConfig">{{ $t('common.retry') }}</button></div>
        <div v-else class="grid gap-3 text-sm text-stone-600 dark:text-gray-400 md:grid-cols-2">
          <div>{{ $t('settings.env') }}: {{ $t('settings.production') }}</div>
          <div>{{ $t('settings.version') }}: {{ systemConfig?.version || '-' }} (Vue + FastAPI)</div>
          <div>{{ $t('settings.db') }}: {{ systemConfig?.runtime?.database_engine || '-' }}</div>
          <div>{{ $t('settings.cache') }}: {{ systemConfig?.runtime?.cache_backend ? $t(`settings.cacheBackends.${systemConfig.runtime.cache_backend}`, systemConfig.runtime.cache_backend) : '-' }}</div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'Settings' })

import AppCurrencySelect from '@/components/AppCurrencySelect.vue'
import AppLanguageSelect from '@/components/AppLanguageSelect.vue'
import AppTimezoneSelect from '@/components/AppTimezoneSelect.vue'
import { useDateTime } from '@/composables/useDateTime'
import { useMoney } from '@/composables/useMoney'
import { useSystemSettingsPage } from '@/modules/system'

const { ratesAreFallback, ratesUpdatedAt } = useMoney()
const { formatDateTime } = useDateTime()
const {
  systemConfig,
  presets,
  apiKeyDraft,
  saving,
  message,
  error,
  systemLoading,
  llmLoading,
  systemLoadError,
  llmLoadError,
  form,
  isCustomProvider,
  canSave,
  applyProviderPreset,
  handleProviderChange,
  saveConfig,
  clearLlmApiKey,
  loadSystemConfig,
  loadLlmConfig,
} = useSystemSettingsPage()
</script>

<style scoped>
.input {
  @apply w-full border bg-white px-3 py-2 text-sm font-semibold text-stone-900 outline-none transition focus:border-emerald-700 disabled:cursor-not-allowed disabled:bg-stone-100 disabled:text-stone-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white dark:disabled:bg-gray-950 dark:disabled:text-gray-500;
  border-color: #e4ded3;
}
</style>
