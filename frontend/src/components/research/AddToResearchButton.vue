<template>
  <button type="button" class="app-button-secondary inline-flex items-center justify-center gap-2" @click="openDialog">
    <BookmarkSquareIcon class="h-4 w-4" />
    {{ t('research.addToResearch') }}
  </button>

  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-sm" @click.self="closeDialog">
      <section ref="dialogRef" role="dialog" aria-modal="true" aria-labelledby="add-research-title" tabindex="-1" class="w-full max-w-xl border border-[#d8d1c5] bg-[#fbfaf7] p-5 shadow-2xl outline-none dark:border-slate-700 dark:bg-slate-800 sm:p-6">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 id="add-research-title" class="text-xl font-semibold text-stone-950 dark:text-white">{{ t('research.addSymbolTitle', { symbol: displayName || symbol }) }}</h2>
          </div>
          <button type="button" class="p-2 app-muted" :aria-label="t('common.close')" @click="closeDialog"><XMarkIcon class="h-5 w-5" /></button>
        </div>

        <div v-if="loading" class="mt-6 text-sm app-muted">{{ t('research.loading') }}</div>
        <form v-else class="mt-6 space-y-4" @submit.prevent="submit">
          <template v-if="activeLists.length">
            <label class="block space-y-1">
              <span class="label">{{ t('research.watchlists') }}</span>
              <select v-model="watchlistId" class="app-control w-full">
                <option v-for="list in activeLists" :key="list.id" :value="list.id">{{ list.name }}</option>
              </select>
            </label>
          </template>
          <template v-else>
            <p class="text-sm app-muted">{{ t('research.createListBeforeAdding') }}</p>
            <input v-model.trim="newListName" class="app-control w-full" :placeholder="t('research.watchlistName')" maxlength="160" />
          </template>
          <label class="block space-y-1">
            <span class="label">{{ t('research.initialThesis') }}</span>
            <textarea v-model.trim="thesis" class="app-control min-h-28 w-full" maxlength="20000" />
          </label>
          <label class="block space-y-1">
            <span class="label">{{ t('research.tags') }}</span>
            <input v-model.trim="tags" class="app-control w-full" :placeholder="t('research.tagsPlaceholder')" />
          </label>
          <div v-if="error" role="alert" class="border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">{{ error }}</div>
          <div class="flex justify-end gap-2">
            <button type="button" class="app-button-secondary" @click="closeDialog">{{ t('research.cancel') }}</button>
            <button type="submit" class="app-button-primary" :disabled="saving || (!watchlistId && !newListName)">{{ saving ? t('research.saving') : t('research.add') }}</button>
          </div>
        </form>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BookmarkSquareIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { apiErrorMessage } from '@/api/request'
import { useModalDialog } from '@/composables/useModalDialog'
import { researchApi } from '@/modules/research'
import type { ResearchWatchItemCreateCommand, ResearchWorkbenchResponse } from '@/modules/research/contracts'

const props = withDefaults(defineProps<{
  symbol: string
  assetClass?: 'crypto' | 'index' | 'cash' | 'web3'
  displayName?: string
  sourceContext?: ResearchWatchItemCreateCommand['sourceContext']
}>(), {
  assetClass: 'crypto',
  displayName: '',
  sourceContext: () => ({}),
})

const emit = defineEmits<{ added: [symbol: string] }>()
const { t } = useI18n()
const open = ref(false)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const data = ref<ResearchWorkbenchResponse>({ watchlists: [], items: [], notes: [], alerts: [], events: [], unacknowledgedEventCount: 0 })
const watchlistId = ref('')
const newListName = ref('')
const thesis = ref('')
const tags = ref('')
const { dialogRef } = useModalDialog(open, closeDialog)
const activeLists = computed(() => (data.value.watchlists || []).filter((list) => !list.archivedAt))

const openDialog = async () => {
  open.value = true
  loading.value = true
  error.value = ''
  try {
    data.value = await researchApi.getWorkbench(20, 20)
    watchlistId.value = activeLists.value[0]?.id || ''
  } catch (cause) {
    error.value = apiErrorMessage(cause, t('research.loadFailed'))
  } finally {
    loading.value = false
  }
}

function closeDialog() {
  open.value = false
  error.value = ''
}

const submit = async () => {
  saving.value = true
  error.value = ''
  try {
    let targetListId = watchlistId.value
    if (!targetListId) {
      const list = await researchApi.createWatchlist({ name: newListName.value, description: '' })
      targetListId = list.id
    }
    await researchApi.createItem({
      watchlistId: targetListId,
      symbol: props.symbol,
      assetClass: props.assetClass,
      displayName: props.displayName,
      thesis: thesis.value,
      tags: tags.value.split(/[,，]/).map((value) => value.trim()).filter(Boolean),
      sourceContext: props.sourceContext,
    })
    emit('added', props.symbol)
    closeDialog()
  } catch (cause) {
    error.value = apiErrorMessage(cause, t('research.addFailed'))
  } finally {
    saving.value = false
  }
}
</script>
