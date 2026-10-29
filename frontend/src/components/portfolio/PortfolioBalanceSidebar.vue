<template>
  <div class="portfolio-switcher space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex min-w-0 flex-wrap items-center gap-3">
        <label class="min-w-0"><span class="sr-only">{{ $t('portfolioBalance.title') }}</span><select :value="activePortfolioId" class="app-control portfolio-select" :disabled="!storageReady || storageLoading || storageSaving || !portfolios.length" @change="$emit('select', $event.target.value)"><option v-if="!portfolios.length" value="">{{ $t('portfolioBalance.emptyTitle') }}</option><option v-for="portfolio in portfolios" :key="portfolio.id" :value="portfolio.id">{{ portfolio.name }}</option></select></label>
        <span v-if="storageLoading || storageSaving" role="status" class="app-muted text-xs">{{ storageLoading ? $t('portfolioBalance.loadingSavedPortfolios') : $t('portfolioBalance.saving') }}</span>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="app-button-secondary" :disabled="!storageReady || storageLoading || storageSaving" @click="$emit('create')"><PlusIcon class="h-4 w-4" />{{ $t('portfolioBalance.createPortfolio') }}</button>
        <details class="portfolio-management">
          <summary class="app-button-secondary">{{ $t('ui.managePortfolios') }}</summary>
          <div class="portfolio-management-content">
            <div class="flex flex-wrap gap-2"><button type="button" class="app-button-secondary" :disabled="!storageReady || storageLoading || storageSaving" @click="openImportPicker"><ArrowUpTrayIcon class="h-4 w-4" />{{ $t('portfolioBalance.importBackup') }}</button><button type="button" class="app-button-secondary" :disabled="!storageReady || storageLoading || storageSaving" @click="$emit('export')"><ArrowDownTrayIcon class="h-4 w-4" />{{ $t('portfolioBalance.exportBackup') }}</button></div>
            <div v-for="portfolio in portfolios" :key="portfolio.id" class="portfolio-management-row"><span class="min-w-0 truncate text-sm font-medium">{{ portfolio.name }}</span><div class="flex gap-2"><button type="button" class="app-icon-button" :aria-label="$t('portfolioBalance.copyPortfolio') + ': ' + portfolio.name" :title="$t('portfolioBalance.copyPortfolio')" :disabled="storageSaving" @click="$emit('copy', portfolio.id)"><DocumentDuplicateIcon class="h-4 w-4" /></button><button type="button" class="app-icon-button" :aria-label="$t('portfolioBalance.deletePortfolio') + ': ' + portfolio.name" :title="$t('portfolioBalance.deletePortfolio')" :disabled="storageSaving" @click="$emit('delete', portfolio.id)"><TrashIcon class="h-4 w-4" /></button></div></div>
            <div v-if="deletedPortfolios.length" class="space-y-3 border-t pt-3" style="border-color:var(--ui-border)"><h2 class="app-section-title">{{ $t('portfolioBalance.recycleBin') }}</h2><div v-for="portfolio in deletedPortfolios" :key="portfolio.id" class="flex items-center justify-between gap-3"><span class="truncate text-sm">{{ portfolio.name }}</span><button type="button" class="text-sm underline app-muted" :disabled="storageSaving" @click="$emit('restore', portfolio.id)">{{ $t('portfolioBalance.restore') }}</button></div><button v-if="hasMoreDeletedPortfolios" type="button" class="app-button-secondary" :disabled="storageSaving" @click="$emit('load-more-deleted')">{{ $t('portfolioBalance.loadMoreDeleted') }}</button></div>
          </div>
        </details>
        <input ref="importInput" type="file" accept="application/json,.json" class="hidden" @change="handleImportFile" />
      </div>
    </div>
    <div v-if="storageError || portfolioFileError" role="alert" class="app-inline-note text-rose-700 dark:text-rose-300">{{ portfolioFileError || storageError }}<button v-if="storageError" type="button" class="ml-3 underline" :disabled="storageLoading" @click="$emit('reload')">{{ $t('portfolioBalance.reload') }}</button></div>
    <div v-if="showStrategy && storageReady && portfolios.length" class="portfolio-strategy-note app-inline-note"><div><strong>{{ $t('portfolioBalance.suggestedActions.' + plan.suggestedAction) }}</strong><span class="ml-3 app-muted">{{ $t('portfolioBalance.reasons.' + plan.suggestedReason) }}</span></div><span class="shrink-0 app-muted">{{ $t('portfolioBalance.nextReviewDate') }} · {{ formatDate(plan.nextReviewDate) }}</span></div>
  </div>
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
  showStrategy: Boolean,
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

<style scoped>
.portfolio-select { width: min(100%, 320px); min-width: 220px; font-weight: 600; }
.portfolio-management[open] { display: contents; }
.portfolio-management-content { order: 3; flex: 1 0 100%; margin-top: 12px; padding: 20px; border: 1px solid var(--ui-border); background: var(--ui-panel); border-radius: 8px; }
.portfolio-management-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding-block: 8px; border-bottom: 1px solid var(--ui-border); }
.portfolio-management-row:last-of-type { border-bottom: 0; }
.portfolio-strategy-note { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
@container app-content (max-width: 34rem) { .portfolio-select { width: 100%; } .portfolio-switcher > div > div:first-child { width: 100%; } }
</style>
