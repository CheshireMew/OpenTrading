<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <section class="app-page-header flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 class="app-title">{{ t('research.title') }}</h1>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="app-button-secondary" :disabled="loading" @click="load">
            {{ loading ? t('research.loading') : t('research.refresh') }}
          </button>
          <button v-if="activeTab === 'alerts' && activeItem" type="button" class="app-button-secondary" @click="enableDesktopNotifications">
            {{ t('research.enableDesktopNotifications') }}
          </button>
          <button type="button" class="app-button-primary" @click="showNewList = true">
            {{ t('research.newWatchlist') }}
          </button>
        </div>
      </section>

      <div v-if="error" role="alert" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
        {{ error }}
      </div>
      <div v-if="feedback" role="status" class="border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200">
        {{ feedback }}
      </div>

      <section v-if="showNewList" class="app-panel p-5">
        <h2 class="app-section-title">{{ t('research.createWatchlist') }}</h2>
        <div class="mt-4 grid gap-3 md:grid-cols-[minmax(12rem,18rem)_minmax(0,1fr)_auto]">
          <label class="block min-w-0"><span class="label">{{ t('research.watchlistName') }}</span><input v-model.trim="newListName" class="app-control" :aria-label="t('research.watchlistName')" :placeholder="t('research.watchlistName')" maxlength="160" /></label>
          <label class="block min-w-0"><span class="label">{{ t('ui.description') }}</span><input v-model.trim="newListDescription" class="app-control" :aria-label="t('research.watchlistDescription')" :placeholder="t('research.watchlistDescription')" maxlength="4000" @keydown.enter.prevent="submitWatchlist" /></label>
          <div class="flex gap-2">
            <button type="button" class="app-button-primary" :disabled="saving || !newListName" @click="submitWatchlist">{{ t('research.create') }}</button>
            <button type="button" class="app-button-secondary" @click="showNewList = false">{{ t('research.cancel') }}</button>
          </div>
        </div>
      </section>

      <AppLoadingState v-if="loading && !activeWatchlists.length" :label="t('research.loading')" />
      <AppEmptyState v-else-if="!activeWatchlists.length && !archivedWatchlists.length && !showNewList" :title="t('ui.researchEmptyTitle')" :description="t('ui.researchEmptyHint')" :icon="BookmarkSquareIcon"><button type="button" class="app-button-primary" @click="showNewList = true">{{ t('research.newWatchlist') }}</button></AppEmptyState>
      <div v-if="activeWatchlists.length || archivedWatchlists.length" class="research-workspace" :class="{ 'has-detail': activeItem }">
        <aside class="research-list-pane min-w-0">
          <div class="app-panel-header flex items-center justify-between">
            <div>
              <h2 class="app-section-title">{{ t('research.watchlists') }}</h2>
              <p class="mt-1 text-xs app-muted">{{ t('research.watchlistCount', { count: activeWatchlists.length }) }}</p>
            </div>
          </div>
          <div class="p-3">
            <button
              v-for="list in activeWatchlists"
              :key="list.id"
              type="button"
              class="mb-2 w-full border-l-2 px-3 py-3 text-left transition"
              :class="activeWatchlistId === list.id ? 'border-emerald-700 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-100' : 'border-transparent text-stone-700 hover:bg-stone-50 dark:text-slate-200 dark:hover:bg-slate-700/40'"
              @click="selectWatchlist(list.id)"
            >
              <span class="block truncate font-semibold">{{ list.name }}</span>
              <span v-if="list.description" class="mt-1 block line-clamp-2 text-xs opacity-70">{{ list.description }}</span>
            </button>
            <p v-if="!activeWatchlists.length" class="p-4 text-sm app-muted">{{ t('research.noWatchlists') }}</p>
          </div>
          <details v-if="archivedWatchlists.length" class="border-t px-4 py-3 dark:border-slate-700" style="border-color:var(--app-border)">
            <summary class="cursor-pointer text-sm font-semibold app-muted">{{ t('research.archivedWatchlists', { count: archivedWatchlists.length }) }}</summary>
            <div class="mt-3 space-y-2">
              <div v-for="list in archivedWatchlists" :key="list.id" class="flex items-center justify-between gap-2 text-sm">
                <span class="truncate">{{ list.name }}</span>
                <button type="button" class="text-emerald-700 underline dark:text-emerald-300" :disabled="saving" @click="setWatchlistArchived(list, false)">{{ t('research.restore') }}</button>
              </div>
            </div>
          </details>
        </aside>

        <section class="app-panel min-w-0 research-assets-pane">
          <template v-if="activeWatchlist">
            <div class="app-panel-header">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h2 class="truncate text-xl font-semibold text-stone-950 dark:text-white">{{ activeWatchlist.name }}</h2>
                  <p v-if="activeWatchlist.description" class="mt-1 text-sm app-muted">{{ activeWatchlist.description }}</p>
                </div>
                <button type="button" class="shrink-0 text-sm text-rose-600 underline dark:text-rose-300" :disabled="saving" @click="setWatchlistArchived(activeWatchlist, true)">{{ t('research.archive') }}</button>
              </div>
              <button type="button" class="app-button-primary mt-4 w-full" @click="showNewItem = !showNewItem">{{ t('research.addAsset') }}</button>
            </div>

            <form v-if="showNewItem" class="space-y-3 border-b p-4 dark:border-slate-700" style="border-color:var(--app-border)" @submit.prevent="submitItem">
              <SymbolSearchBox
                v-model="itemForm.symbol"
                :allowed-classes="['crypto', 'index']"
                :aria-label="t('research.selectAsset')"
                :placeholder="t('research.selectAsset')"
                @select="onCatalogSelect"
              />
              <label class="block min-w-0"><span class="label">{{ t('research.thesis') }}</span><textarea v-model.trim="itemForm.thesis" class="app-control min-h-24 w-full" :aria-label="t('research.initialThesis')" :placeholder="t('research.initialThesis')" maxlength="20000" /></label>
              <div class="grid grid-cols-2 gap-3">
                <label class="block min-w-0"><span class="label">{{ t('research.targetPrice') }}</span><input v-model="itemForm.targetPrice" class="app-control" inputmode="decimal" :aria-label="t('research.targetPrice')" :placeholder="t('research.targetPrice')" /></label>
                <label class="block min-w-0"><span class="label">{{ t('research.invalidationPrice') }}</span><input v-model="itemForm.invalidationPrice" class="app-control" inputmode="decimal" :aria-label="t('research.invalidationPrice')" :placeholder="t('research.invalidationPrice')" /></label>
              </div>
              <label class="block min-w-0"><span class="label">{{ t('research.tags') }}</span><input v-model.trim="itemForm.tags" class="app-control w-full" :aria-label="t('research.tagsPlaceholder')" :placeholder="t('research.tagsPlaceholder')" /></label>
              <div class="flex gap-2">
                <button type="submit" class="app-button-primary flex-1" :disabled="saving || !itemForm.symbol">{{ t('research.add') }}</button>
                <button type="button" class="app-button-secondary" @click="showNewItem = false">{{ t('research.cancel') }}</button>
              </div>
            </form>

            <div class="research-asset-list p-3">
              <button
                v-for="item in activeItems"
                :key="item.id"
                type="button"
                class="mb-3 w-full border p-4 text-left transition dark:border-slate-700"
                :class="activeItemId === item.id ? 'border-emerald-700 bg-emerald-50/70 dark:bg-emerald-950/20' : 'border-stone-200 bg-white hover:bg-stone-50 dark:bg-slate-800 dark:hover:bg-slate-700/50'"
                @click="activeItemId = item.id"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <span class="font-semibold text-emerald-700 dark:text-emerald-300">{{ item.symbol }}</span>
                    <p class="mt-1 text-xs app-muted">{{ item.displayName || item.assetClass }}</p>
                  </div>
                  <span class="app-chip">{{ item.tags?.length || 0 }} {{ t('research.tags') }}</span>
                </div>
                <p v-if="item.thesis" class="mt-3 line-clamp-3 text-sm leading-6 text-stone-600 dark:text-slate-300">{{ item.thesis }}</p>
                <div v-if="item.targetPrice || item.invalidationPrice" class="mt-3 flex gap-4 text-xs app-muted">
                  <span>{{ t('research.targetShort') }} {{ item.targetPrice ?? '--' }}</span>
                  <span>{{ t('research.invalidationShort') }} {{ item.invalidationPrice ?? '--' }}</span>
                </div>
              </button>
              <AppEmptyState v-if="!activeItems.length" :title="t('research.noAssets')" :description="t('ui.researchAssetHint')"><button type="button" class="app-button-secondary" @click="showNewItem = true">{{ t('research.addAsset') }}</button></AppEmptyState>
            </div>

            <details v-if="archivedItems.length" class="border-t px-4 py-3 dark:border-slate-700" style="border-color:var(--app-border)">
              <summary class="cursor-pointer text-sm font-semibold app-muted">{{ t('research.archivedAssets', { count: archivedItems.length }) }}</summary>
              <div class="mt-3 space-y-2">
                <div v-for="item in archivedItems" :key="item.id" class="flex items-center justify-between gap-2 text-sm">
                  <span>{{ item.symbol }}</span>
                  <button type="button" class="text-emerald-700 underline dark:text-emerald-300" :disabled="saving" @click="setItemArchived(item, false)">{{ t('research.restore') }}</button>
                </div>
              </div>
            </details>
          </template>
          <div v-else class="flex min-h-[28rem] items-center justify-center p-8 text-center app-muted">
            <p>{{ t('research.chooseOrCreateWatchlist') }}</p>
          </div>
        </section>

        <section v-if="activeItem" class="app-panel min-w-0 research-detail-pane">
          <template v-if="activeItem">
            <div class="app-panel-header">
              <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>

                  <h2 class="mt-1 text-2xl font-semibold text-stone-950 dark:text-white"><router-link :to="`/research/assets/${encodeURIComponent(activeItem.symbol)}`" class="hover:underline underline-offset-4">{{ activeItem.symbol }}</router-link></h2>
                  <p class="mt-1 text-sm app-muted">{{ activeItem.displayName }}</p>
                </div>
                <button type="button" class="text-sm text-rose-600 underline dark:text-rose-300" :disabled="saving" @click="setItemArchived(activeItem, true)">{{ t('research.archiveAsset') }}</button>
              </div>

              <form class="mt-5 space-y-3" @submit.prevent="saveActiveItem">
                <label class="block min-w-0"><span class="label">{{ t('research.thesis') }}</span><textarea v-model.trim="editItem.thesis" class="app-control min-h-28 w-full" :aria-label="t('research.thesis')" :placeholder="t('research.thesis')" maxlength="20000" /></label>
                <div class="grid gap-3 sm:grid-cols-3">
                  <label class="block min-w-0"><span class="label">{{ t('research.targetPrice') }}</span><input v-model="editItem.targetPrice" class="app-control" inputmode="decimal" :aria-label="t('research.targetPrice')" :placeholder="t('research.targetPrice')" /></label>
                  <label class="block min-w-0"><span class="label">{{ t('research.invalidationPrice') }}</span><input v-model="editItem.invalidationPrice" class="app-control" inputmode="decimal" :aria-label="t('research.invalidationPrice')" :placeholder="t('research.invalidationPrice')" /></label>
                  <label class="block min-w-0"><span class="label">{{ t('research.tags') }}</span><input v-model.trim="editItem.tags" class="app-control" :aria-label="t('research.tagsPlaceholder')" :placeholder="t('research.tagsPlaceholder')" /></label>
                </div>
                <button type="submit" class="app-button-primary" :disabled="saving">{{ saving ? t('research.saving') : t('research.saveThesis') }}</button>
              </form>
            </div>

            <div class="flex overflow-x-auto border-b px-4 dark:border-slate-700" style="border-color:var(--app-border)">
              <button v-for="tab in tabs" :key="tab" type="button" class="border-b-2 px-4 py-3 text-sm font-semibold" :class="activeTab === tab ? 'border-emerald-700 text-emerald-800 dark:text-emerald-300' : 'border-transparent app-muted'" @click="activeTab = tab">
                {{ t(`research.tabs.${tab}`) }}
                <span v-if="tab === 'timeline' && workbench.unacknowledgedEventCount" class="ml-1 bg-rose-600 px-1.5 py-0.5 text-[10px] text-white">{{ workbench.unacknowledgedEventCount }}</span>
              </button>
            </div>

            <div v-if="activeTab === 'journal'" class="space-y-5 p-5">
              <form class="space-y-3 border p-4 dark:border-slate-700" style="border-color:var(--app-border)" @submit.prevent="submitNote">
                <div class="grid gap-3 sm:grid-cols-[10rem_minmax(0,1fr)]">
                  <select :aria-label="t('ui.noteType')" v-model="noteForm.kind" class="app-control">
                    <option value="thesis">{{ t('research.noteKinds.thesis') }}</option>
                    <option value="update">{{ t('research.noteKinds.update') }}</option>
                    <option value="review">{{ t('research.noteKinds.review') }}</option>
                    <option value="decision">{{ t('research.noteKinds.decision') }}</option>
                  </select>
                  <label class="block min-w-0"><span class="label">{{ t('research.noteTitle') }}</span><input v-model.trim="noteForm.title" class="app-control" :aria-label="t('research.noteTitle')" :placeholder="t('research.noteTitle')" maxlength="240" /></label>
                </div>
                <label class="block min-w-0"><span class="label">{{ t('ui.noteBody') }}</span><textarea v-model.trim="noteForm.content" class="app-control min-h-28 w-full" :aria-label="t('research.noteContent')" :placeholder="t('research.noteContent')" maxlength="100000" /></label>
                <button type="submit" class="app-button-primary" :disabled="saving || !noteForm.title">{{ t('research.addNote') }}</button>
              </form>
              <article v-for="note in itemNotes" :key="note.id" class="border p-4 dark:border-slate-700" style="border-color:var(--app-border)">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <span class="app-chip">{{ t(`research.noteKinds.${note.kind}`) }}</span>
                    <h3 class="mt-3 font-semibold text-stone-950 dark:text-white">{{ note.title }}</h3>
                  </div>
                  <button type="button" class="text-xs text-rose-600 underline dark:text-rose-300" @click="setNoteArchived(note, true)">{{ t('research.archive') }}</button>
                </div>
                <p class="mt-3 whitespace-pre-wrap text-sm leading-6 text-stone-600 dark:text-slate-300">{{ note.content }}</p>
                <p class="mt-3 text-xs app-muted">{{ formatDateTime(note.occurredAt) }}</p>
              </article>
              <p v-if="!itemNotes.length" class="py-8 text-center text-sm app-muted">{{ t('research.noNotes') }}</p>
              <details v-if="archivedNotes.length">
                <summary class="cursor-pointer text-sm font-semibold app-muted">{{ t('research.archivedNotes', { count: archivedNotes.length }) }}</summary>
                <div class="mt-3 space-y-2">
                  <div v-for="note in archivedNotes" :key="note.id" class="flex items-center justify-between border p-3 text-sm dark:border-slate-700">
                    <span>{{ note.title }}</span>
                    <button type="button" class="text-emerald-700 underline dark:text-emerald-300" @click="setNoteArchived(note, false)">{{ t('research.restore') }}</button>
                  </div>
                </div>
              </details>
            </div>

            <div v-else-if="activeTab === 'alerts'" class="space-y-5 p-5">
              <div class="flex items-center justify-between gap-3">
                <p class="text-sm app-muted">{{ t('research.alertRuntimeHint') }}</p>
                <button type="button" class="app-button-secondary shrink-0" :disabled="saving" @click="evaluateNow">{{ t('research.evaluateNow') }}</button>
              </div>
              <form class="space-y-3 border p-4 dark:border-slate-700" style="border-color:var(--app-border)" @submit.prevent="submitAlert">
                <label class="block min-w-0"><span class="label">{{ t('research.alertName') }}</span><input v-model.trim="alertForm.name" class="app-control w-full" :aria-label="t('research.alertName')" :placeholder="t('research.alertName')" maxlength="200" /></label>
                <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <select :aria-label="t('ui.alertMetric')" v-model="alertForm.metric" class="app-control">
                    <option v-for="metric in alertMetrics" :key="metric" :value="metric">{{ t(`research.alertMetrics.${metric}`) }}</option>
                  </select>
                  <select :aria-label="t('ui.alertCondition')" v-model="alertForm.operator" class="app-control">
                    <option v-for="operator in alertOperators" :key="operator" :value="operator">{{ t(`research.alertOperators.${operator}`) }}</option>
                  </select>
                  <label class="block min-w-0"><span class="label">{{ t('research.threshold') }}</span><input v-model="alertForm.threshold" class="app-control" inputmode="decimal" :aria-label="t('research.threshold')" :placeholder="t('research.threshold')" /></label>
                  <label v-if="['between', 'outside'].includes(alertForm.operator)" class="block min-w-0"><span class="label">{{ t('research.secondaryThreshold') }}</span><input v-model="alertForm.secondaryThreshold" class="app-control" inputmode="decimal" :aria-label="t('research.secondaryThreshold')" :placeholder="t('research.secondaryThreshold')" /></label>
                </div>
                <div class="flex flex-wrap items-center gap-5 text-sm text-stone-600 dark:text-slate-300">
                  <label class="flex items-center gap-2"><input v-model="alertForm.windows" type="checkbox" /> {{ t('research.windowsNotification') }}</label>
                  <label class="flex items-center gap-2">{{ t('research.cooldown') }} <input v-model.number="alertForm.cooldownMinutes" type="number" min="0" max="43200" class="app-control w-24" /></label>
                </div>
                <button type="submit" class="app-button-primary" :disabled="saving || !alertForm.name || alertForm.threshold === ''">{{ t('research.addAlert') }}</button>
              </form>
              <article v-for="alert in itemAlerts" :key="alert.id" class="border p-4 dark:border-slate-700" style="border-color:var(--app-border)">
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <h3 class="font-semibold text-stone-950 dark:text-white">{{ alert.name }}</h3>
                    <p class="mt-2 text-sm app-muted">{{ t(`research.alertMetrics.${alert.metric}`, alert.metric) }} · {{ t(`research.alertOperators.${alert.operator}`) }} · {{ alert.threshold }}<template v-if="alert.secondaryThreshold != null"> — {{ alert.secondaryThreshold }}</template></p>
                  </div>
                  <div class="flex items-center gap-3">
                    <span class="app-chip">{{ alert.enabled ? t('research.enabled') : t('research.disabled') }}</span>
                    <button type="button" class="text-xs text-rose-600 underline dark:text-rose-300" @click="setAlertArchived(alert, true)">{{ t('research.archive') }}</button>
                  </div>
                </div>
                <p class="mt-3 text-xs app-muted">{{ t('research.lastValue') }} {{ alert.lastValue ?? '--' }} · {{ t('research.lastTriggered') }} {{ formatDateTime(alert.lastTriggeredAt) }}</p>
              </article>
              <p v-if="!itemAlerts.length" class="py-8 text-center text-sm app-muted">{{ t('research.noAlerts') }}</p>
              <details v-if="archivedAlerts.length">
                <summary class="cursor-pointer text-sm font-semibold app-muted">{{ t('research.archivedAlerts', { count: archivedAlerts.length }) }}</summary>
                <div class="mt-3 space-y-2">
                  <div v-for="alert in archivedAlerts" :key="alert.id" class="flex items-center justify-between border p-3 text-sm dark:border-slate-700">
                    <span>{{ alert.name }}</span>
                    <button type="button" class="text-emerald-700 underline dark:text-emerald-300" @click="setAlertArchived(alert, false)">{{ t('research.restore') }}</button>
                  </div>
                </div>
              </details>
            </div>

            <div v-else class="space-y-3 p-5">
              <article v-for="event in filteredEvents" :key="event.id" class="border-l p-4" :class="event.acknowledgedAt ? 'border-stone-300 bg-stone-50/60 dark:border-slate-600 dark:bg-slate-900/30' : 'border-emerald-700 bg-emerald-50/70 dark:bg-emerald-950/20'">
                <div class="flex items-start justify-between gap-4">
                  <div>
                    <p class="font-semibold text-stone-950 dark:text-white">{{ event.title }}</p>
                    <p v-if="event.body" class="mt-2 whitespace-pre-wrap text-sm leading-6 text-stone-600 dark:text-slate-300">{{ event.body }}</p>
                    <p class="mt-2 text-xs app-muted">{{ formatDateTime(event.occurredAt) }} · {{ event.kind }}</p>
                  </div>
                  <button v-if="!event.acknowledgedAt" type="button" class="shrink-0 text-xs text-emerald-700 underline dark:text-emerald-300" @click="acknowledgeEvent(event.id)">{{ t('research.acknowledge') }}</button>
                </div>
              </article>
              <p v-if="!filteredEvents.length" class="py-8 text-center text-sm app-muted">{{ t('research.noEvents') }}</p>
            </div>
          </template>
          <div v-else class="flex min-h-[28rem] items-center justify-center p-8 text-center app-muted">
            <p>{{ t('research.chooseAsset') }}</p>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { BookmarkSquareIcon } from '@heroicons/vue/24/outline'
import AppEmptyState from '@/components/AppEmptyState.vue'
import AppLoadingState from '@/components/AppLoadingState.vue'
import { useI18n } from 'vue-i18n'
import SymbolSearchBox from '@/components/SymbolSearchBox.vue'
import { useDateTime } from '@/composables/useDateTime'
import { useResearchWorkbench } from '@/modules/research'
import type { MarketSymbolSearchItem } from '@/modules/market/contracts'

const { t } = useI18n()
const { formatDateTime } = useDateTime()
const {
  workbench, loading, saving, error, activeWatchlistId, activeItemId,
  activeWatchlists, archivedWatchlists, activeWatchlist, activeItems, archivedItems,
  activeItem, itemNotes, archivedNotes, itemAlerts, archivedAlerts,
  load, createWatchlist, setWatchlistArchived, createItem, saveItem, setItemArchived,
  createNote, setNoteArchived, createAlert, setAlertArchived, acknowledgeEvent,
  requestDesktopPermission,
  evaluateAlerts,
} = useResearchWorkbench()

const showNewList = ref(false)
const showNewItem = ref(false)
const newListName = ref('')
const newListDescription = ref('')
const feedback = ref('')
const activeTab = ref<'journal' | 'alerts' | 'timeline'>('journal')
const tabs = ['journal', 'alerts', 'timeline'] as const

const emptyItemForm = () => ({ symbol: '', assetClass: 'crypto' as 'crypto' | 'index', displayName: '', thesis: '', targetPrice: '', invalidationPrice: '', tags: '' })
const itemForm = reactive(emptyItemForm())
const editItem = reactive({ thesis: '', targetPrice: '', invalidationPrice: '', tags: '' })
const noteForm = reactive({ kind: 'update' as 'thesis' | 'update' | 'review' | 'decision', title: '', content: '' })
const alertMetrics = ['price', 'price_change_24h', 'breakout_score', 'funding_rate_pct', 'oi_change_1h_pct', 'portfolio_drift_pct', 'rsi'] as const
const alertOperators = ['gt', 'gte', 'lt', 'lte', 'crosses_above', 'crosses_below', 'between', 'outside'] as const
const alertForm = reactive({ name: '', metric: 'price', operator: 'crosses_above', threshold: '' as string | number, secondaryThreshold: '' as string | number, cooldownMinutes: 60, windows: false })

const filteredEvents = computed(() => (workbench.value.events || []).filter((event) => (
  !activeItem.value || event.symbol === activeItem.value.symbol || event.entityId === activeItem.value.id
)))

const numberOrNull = (value: string | number) => {
  if (value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

const setFeedback = (message: string) => {
  feedback.value = message
  window.setTimeout(() => { if (feedback.value === message) feedback.value = '' }, 3500)
}

const submitWatchlist = async () => {
  const result = await createWatchlist(newListName.value, newListDescription.value)
  if (!result) return
  newListName.value = ''
  newListDescription.value = ''
  showNewList.value = false
  setFeedback(t('research.feedback.watchlistCreated'))
}

const selectWatchlist = (id: string) => {
  activeWatchlistId.value = id
  activeItemId.value = activeItems.value[0]?.id || ''
}

const onCatalogSelect = (catalogItem: MarketSymbolSearchItem) => {
  itemForm.assetClass = catalogItem.asset_class === 'index' ? 'index' : 'crypto'
  itemForm.displayName = catalogItem.name
}

const submitItem = async () => {
  if (!activeWatchlist.value) return
  const result = await createItem({
    watchlistId: activeWatchlist.value.id,
    symbol: itemForm.symbol,
    assetClass: itemForm.assetClass,
    displayName: itemForm.displayName,
    thesis: itemForm.thesis,
    targetPrice: numberOrNull(itemForm.targetPrice),
    invalidationPrice: numberOrNull(itemForm.invalidationPrice),
    tags: itemForm.tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean),
    sourceContext: { route: window.location.pathname },
  })
  if (!result) return
  Object.assign(itemForm, emptyItemForm())
  showNewItem.value = false
  setFeedback(t('research.feedback.assetAdded'))
}

const saveActiveItem = async () => {
  if (!activeItem.value) return
  const result = await saveItem(activeItem.value, {
    watchlistId: activeItem.value.watchlistId,
    symbol: activeItem.value.symbol,
    assetClass: activeItem.value.assetClass,
    displayName: activeItem.value.displayName,
    thesis: editItem.thesis,
    targetPrice: numberOrNull(editItem.targetPrice),
    invalidationPrice: numberOrNull(editItem.invalidationPrice),
    tags: editItem.tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean),
    sourceContext: activeItem.value.sourceContext || {},
  })
  if (result) setFeedback(t('research.feedback.thesisSaved'))
}

const submitNote = async () => {
  if (!activeItem.value) return
  const result = await createNote({
    watchItemId: activeItem.value.id,
    symbol: activeItem.value.symbol,
    kind: noteForm.kind,
    title: noteForm.title,
    content: noteForm.content,
    snapshot: {},
  })
  if (!result) return
  noteForm.title = ''
  noteForm.content = ''
  setFeedback(t('research.feedback.noteAdded'))
}

const submitAlert = async () => {
  if (!activeItem.value) return
  const threshold = Number(alertForm.threshold)
  const secondary = alertForm.secondaryThreshold === '' ? null : Number(alertForm.secondaryThreshold)
  const result = await createAlert({
    watchItemId: activeItem.value.id,
    symbol: activeItem.value.symbol,
    name: alertForm.name,
    metric: alertForm.metric,
    operator: alertForm.operator as typeof alertOperators[number],
    threshold,
    secondaryThreshold: secondary,
    enabled: true,
    cooldownMinutes: alertForm.cooldownMinutes,
    notificationChannels: alertForm.windows ? ['in_app', 'windows'] : ['in_app'],
    configuration: {},
  })
  if (!result) return
  alertForm.name = ''
  alertForm.threshold = ''
  alertForm.secondaryThreshold = ''
  setFeedback(t('research.feedback.alertAdded'))
}

const enableDesktopNotifications = async () => {
  const permission = await requestDesktopPermission()
  setFeedback(permission === 'granted' ? t('research.feedback.notificationsEnabled') : t('research.feedback.notificationsUnavailable'))
}

const evaluateNow = async () => {
  const result = await evaluateAlerts()
  if (!result) return
  setFeedback(t('research.feedback.alertsEvaluated', {
    evaluated: result.evaluatedCount,
    triggered: result.triggeredCount,
    unavailable: result.unavailableCount,
  }))
}

watch(activeItem, (item) => {
  editItem.thesis = item?.thesis || ''
  editItem.targetPrice = item?.targetPrice == null ? '' : String(item.targetPrice)
  editItem.invalidationPrice = item?.invalidationPrice == null ? '' : String(item.invalidationPrice)
  editItem.tags = (item?.tags || []).join(', ')
}, { immediate: true })

onMounted(load)
</script>

<style scoped>
.research-workspace { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; align-items: start; }
.research-list-pane { border-bottom: 1px solid var(--ui-border); }
.research-list-pane > .app-panel-header { border: 0; padding: 0 0 8px; }
.research-list-pane > .p-3 { display: flex; overflow-x: auto; gap: 8px; padding-inline: 0; }
.research-list-pane > .p-3 > button { flex: 0 0 180px; border: 0; border-radius: 5px; padding: 12px; margin: 0; }
.research-list-pane > .p-3 > button span:nth-child(2) { display: none; }
@container app-content (min-width: 60rem) {
  .research-workspace.has-detail { grid-template-columns: minmax(260px, .7fr) minmax(0, 1.3fr); }
  .research-list-pane { grid-column: 1 / -1; }
  .research-asset-list { max-height: 640px; overflow-y: auto; }
}
@container app-content (min-width: 88rem) {
  .research-workspace { grid-template-columns: 200px minmax(0, 1fr); }
  .research-workspace.has-detail { grid-template-columns: 200px minmax(280px, .7fr) minmax(0, 1.3fr); }
  .research-list-pane { grid-column: auto; border: 0; }
  .research-list-pane > .p-3 { display: block; }
  .research-list-pane > .p-3 > button { width: 100%; margin-bottom: 8px; }
}
</style>
