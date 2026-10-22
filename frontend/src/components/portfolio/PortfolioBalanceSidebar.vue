<template>
  <aside class="min-w-0 space-y-6">
    <section class="app-panel p-5">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold text-stone-950 dark:text-white">{{ $t('portfolioBalance.title') }}</h1>
        </div>
        <button
          type="button"
          class="inline-flex h-11 w-11 items-center justify-center border border-[#b8d2c4] bg-[#edf3ee] text-[#0f6b4f] transition hover:bg-[#e1ece4] dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:hover:bg-emerald-900/50"
          :disabled="!storageReady || storageLoading || storageSaving"
          :aria-label="$t('portfolioBalance.createPortfolio')"
          :title="$t('portfolioBalance.createPortfolio')"
          @click="$emit('create')"
        >
          <PlusIcon class="h-5 w-5" />
        </button>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-2">
        <button type="button" class="app-button-secondary inline-flex items-center justify-center px-3 py-2 text-sm" :disabled="!storageReady || storageLoading || storageSaving" @click="openImportPicker">
          <ArrowUpTrayIcon class="mr-2 h-4 w-4" />
          {{ $t('portfolioBalance.importBackup') }}
        </button>
        <button type="button" class="app-button-secondary inline-flex items-center justify-center px-3 py-2 text-sm" :disabled="!storageReady || storageLoading || storageSaving" @click="$emit('export')">
          <ArrowDownTrayIcon class="mr-2 h-4 w-4" />
          {{ $t('portfolioBalance.exportBackup') }}
        </button>
        <input ref="importInput" type="file" accept="application/json,.json" class="hidden" @change="handleImportFile" />
      </div>

      <div v-if="storageLoading" class="mt-4 text-sm text-stone-500 dark:text-slate-400">{{ $t('portfolioBalance.loadingSavedPortfolios') }}</div>
      <div v-else-if="storageSaving" class="mt-4 text-sm text-stone-500 dark:text-slate-400">{{ $t('portfolioBalance.saving') }}</div>
      <div v-if="storageError || portfolioFileError" role="alert" class="mt-4 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-200">
        <div>{{ portfolioFileError || storageError }}</div>
        <button v-if="storageError" type="button" class="mt-2 font-semibold underline" :disabled="storageLoading" @click="$emit('reload')">{{ $t('portfolioBalance.reload') }}</button>
      </div>

      <div v-if="storageReady && !storageLoading" class="mt-5 space-y-3">
        <div
          v-for="portfolio in portfolios"
          :key="portfolio.id"
          class="w-full border px-4 py-4 text-left transition"
          :class="portfolio.id === activePortfolioId ? 'border-[#b8d2c4] bg-[#edf3ee] dark:border-emerald-700 dark:bg-emerald-950/30' : 'border-stone-200 bg-[#fbfaf7] hover:border-stone-300 dark:border-slate-700 dark:bg-slate-900/60 dark:hover:border-slate-600'"
        >
          <div class="flex items-start justify-between gap-3">
            <button type="button" class="min-w-0 flex-1 text-left" @click="$emit('select', portfolio.id)"><div class="truncate text-base font-semibold text-slate-900 dark:text-white">{{ portfolio.name }}</div></button>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center border border-transparent text-slate-400 transition hover:border-[#b8d2c4] hover:text-[#0f6b4f] dark:hover:border-emerald-800 dark:hover:text-emerald-300" :aria-label="$t('portfolioBalance.copyPortfolio')" :title="$t('portfolioBalance.copyPortfolio')" :disabled="storageSaving" @click.stop="$emit('copy', portfolio.id)"><DocumentDuplicateIcon class="h-4 w-4" /></button>
            <button type="button" class="inline-flex h-8 w-8 items-center justify-center border border-transparent text-slate-400 transition hover:border-rose-200 hover:text-rose-600 dark:hover:border-rose-800 dark:hover:text-rose-300" :aria-label="$t('portfolioBalance.deletePortfolio')" :title="$t('portfolioBalance.deletePortfolio')" :disabled="storageSaving" @click.stop="$emit('delete', portfolio.id)"><TrashIcon class="h-4 w-4" /></button>
          </div>
        </div>
      </div>

      <div v-if="storageReady && deletedPortfolios.length" class="mt-6 border-t border-stone-200 pt-4 dark:border-slate-700">
        <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-stone-500 dark:text-slate-400"><ArchiveBoxIcon class="h-4 w-4" />{{ $t('portfolioBalance.recycleBin') }}</div>
        <div class="mt-3 space-y-2">
          <div v-for="portfolio in deletedPortfolios" :key="portfolio.id" class="flex items-center justify-between gap-3 border border-stone-200 bg-[#fbfaf7] px-3 py-2 dark:border-slate-700 dark:bg-slate-900/60">
            <span class="min-w-0 truncate text-sm text-slate-700 dark:text-slate-200">{{ portfolio.name }}</span>
            <button type="button" class="text-sm font-medium text-[#0f6b4f] hover:underline disabled:opacity-50 dark:text-emerald-300" :disabled="storageSaving" @click="$emit('restore', portfolio.id)">{{ $t('portfolioBalance.restore') }}</button>
          </div>
          <button
            v-if="hasMoreDeletedPortfolios"
            type="button"
            class="app-button-secondary w-full px-3 py-2 text-sm"
            :disabled="storageSaving"
            @click="$emit('load-more-deleted')"
          >
            {{ $t('portfolioBalance.loadMoreDeleted') }}
          </button>
        </div>
      </div>
    </section>

    <section v-if="storageReady && portfolios.length" class="app-panel p-5">
      <h2 class="app-section-title">{{ $t('portfolioBalance.strategyTitle') }}</h2>
      <div class="mt-4 space-y-3">
        <div class="px-4 py-4" :class="strategyCardClass(plan.suggestedAction)">
          <div class="text-xs font-semibold uppercase tracking-wide">{{ $t('portfolioBalance.nextAction') }}</div>
          <div class="mt-2 text-lg font-semibold">{{ $t(`portfolioBalance.suggestedActions.${plan.suggestedAction}`) }}</div>
          <div class="mt-1 text-sm opacity-80">{{ $t(`portfolioBalance.reasons.${plan.suggestedReason}`) }}</div>
        </div>
        <div class="grid grid-cols-2 gap-3 text-sm">
          <div class="border border-stone-200 bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/60"><div class="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.nextReviewDate') }}</div><div class="mt-1 font-semibold text-slate-900 dark:text-white">{{ formatDate(plan.nextReviewDate) }}</div></div>
          <div class="border border-stone-200 bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/60"><div class="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.daysUntilReview') }}</div><div class="mt-1 font-semibold text-slate-900 dark:text-white">{{ plan.daysUntilReview }}</div></div>
        </div>
      </div>
    </section>
  </aside>
</template>

<script setup>
import { ref } from 'vue'
import { ArchiveBoxIcon, ArrowDownTrayIcon, ArrowUpTrayIcon, DocumentDuplicateIcon, PlusIcon, TrashIcon } from '@heroicons/vue/24/outline'
import { formatDate } from '@/modules/format'

defineProps({
  portfolios: { type: Array, required: true },
  deletedPortfolios: { type: Array, required: true },
  hasMoreDeletedPortfolios: Boolean,
  activePortfolioId: { type: String, default: '' },
  plan: { type: Object, required: true },
  storageReady: Boolean,
  storageLoading: Boolean,
  storageSaving: Boolean,
  storageError: { type: String, default: '' },
  portfolioFileError: { type: String, default: '' },
})
const emit = defineEmits(['create', 'export', 'import-file', 'reload', 'select', 'copy', 'delete', 'restore', 'load-more-deleted'])
const importInput = ref(null)
const openImportPicker = () => importInput.value?.click()
const handleImportFile = (event) => {
  const input = event?.target
  const file = input?.files?.[0]
  if (file) emit('import-file', file)
  if (input) input.value = ''
}
const strategyCardClass = (action) => {
  if (action === 'full') return 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-200'
  if (action === 'cashflow') return 'bg-[#edf3ee] text-[#0f6b4f] dark:bg-emerald-950/40 dark:text-emerald-200'
  return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200'
}
</script>
