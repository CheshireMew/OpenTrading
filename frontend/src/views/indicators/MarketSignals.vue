<template>
  <div :class="['signal-page min-h-full text-slate-900 transition-colors dark:text-slate-100', theme === 'dark' ? 'signal-page--dark' : 'signal-page--light']">
    <section class="flex w-full flex-col gap-8 px-3 py-5 sm:px-4 lg:px-5 xl:px-6">
      <header class="app-page-header flex flex-wrap items-center justify-between gap-4">
        <h1 class="app-title">
          {{ t('marketSignals.title') }}
        </h1>
        <div class="flex flex-wrap items-center gap-3"><AppLayoutSwitch v-model="pageLayout" :options="layoutOptions" />
        <button type="button" class="app-button-primary app-touch-target" :disabled="loading" @click="refresh">
          {{ loading ? t('marketSignals.refreshing') : t('marketSignals.refresh') }}
        </button></div>
      </header>

      <div v-if="error" role="alert" class="flex flex-wrap items-center justify-between gap-3 border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-950/40 dark:text-red-200">
        <span>{{ error }}</span>
        <button type="button" class="app-button-secondary app-touch-target" :disabled="loading" @click="refresh">{{ t('app.retry') }}</button>
      </div>

      <div v-if="!error || totalCount > 0" class="signal-navigation app-metric-strip">
        <button type="button" class="summary-card" :aria-pressed="activeGroup === 'all'" @click="activeGroup = 'all'">
          <span>{{ t('marketSignals.currentIndicators') }}</span>
          <strong>{{ totalCount }}</strong>
        </button>
        <button v-for="group in groups" :key="group.definition.id" type="button" class="summary-card" :aria-pressed="activeGroup === group.definition.id" @click="activeGroup = group.definition.id">
          <span>{{ group.definition.title }}</span>
          <strong>{{ group.cards.length }}</strong>
          <em>{{ t('marketSignals.lastUpdated', { time: group.latestUpdatedLabel }) }}</em>
        </button>
      </div>

      <div v-if="loading" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div v-for="item in 6" :key="item" class="h-72 animate-pulse border border-slate-200 bg-white/70 dark:border-slate-800 dark:bg-slate-900/50"></div>
      </div>

      <template v-else-if="totalCount > 0">
        <section v-if="selectedCard" class="signal-detail app-panel p-5" aria-labelledby="signal-detail-title">
          <header class="flex flex-wrap items-center justify-between gap-3"><h2 id="signal-detail-title" class="app-section-title">{{ t('indicator.' + selectedCard.indicator.indicator_id, selectedCard.indicator.name) }}</h2><button type="button" class="app-button-secondary" @click="selectedId = ''">{{ t('workspaceViews.close') }}</button></header>
          <div class="my-4 flex items-baseline gap-4"><strong class="text-3xl">{{ selectedCard.valueLabel }}</strong><span :class="changeToneClass(selectedCard.changeValue)">{{ selectedCard.changeLabel }}</span><span class="text-xs app-muted">{{ selectedCard.lastUpdatedLabel }}</span></div>
          <IndicatorChart v-if="selectedCard.indicator.history.length >= 2" :key="selectedId" :indicator="selectedCard.indicator" height="h-80" />
          <p v-else class="py-12 text-center app-muted">{{ t('marketSignals.collectingHistory', { count: selectedCard.indicator.history.length }) }}</p>
          <p v-if="selectedCard.indicator.description" class="mt-4 text-sm app-muted">{{ selectedCard.indicator.description }}</p>
        </section>

        <section v-for="group in visibleGroups" :key="group.definition.id" class="space-y-3">
          <div :class="['category-heading', `category-heading--${group.definition.accent}`]">
            <div>
              <h2 class="text-lg font-semibold text-slate-950 dark:text-white">{{ group.definition.title }}</h2>
            </div>
            <div class="text-sm font-semibold text-slate-500 dark:text-slate-400">{{ t('marketSignals.itemCount', { count: group.cards.length }) }}</div>
          </div>

          <div v-if="group.cards.length > 0 && pageLayout === 'cards'" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <article v-for="card in group.cards" :key="card.indicator.indicator_id" class="metric-card">
              <button type="button" class="flex w-full items-start justify-between gap-3 text-left" :aria-expanded="selectedId === card.indicator.indicator_id" @click="selectIndicator(card.indicator.indicator_id)">
                <div class="min-w-0">
                  <h3 class="text-sm font-semibold text-slate-950 dark:text-white" :title="card.indicator.indicator_id">
                    {{ $t('indicator.' + card.indicator.indicator_id, card.indicator.name) }}
                  </h3>
                </div>
                <span :class="['change-pill', changeToneClass(card.changeValue)]">{{ card.changeLabel }}</span>
              </button>

              <div class="mt-4 flex items-end justify-between gap-3">
                <div class="min-w-0 text-2xl font-semibold text-slate-950 dark:text-white">{{ card.valueLabel }}</div>
                <div class="text-right text-xs app-muted">{{ card.lastUpdatedLabel }}</div>
              </div>

              <div class="mt-3">
                <IndicatorChart v-if="card.indicator.history.length >= 2" :indicator="card.indicator" height="h-44" />
                <div v-else class="flex h-44 items-center justify-center px-4 text-center text-sm text-stone-400 dark:text-slate-500">
                  {{ $t('marketSignals.collectingHistory', { count: card.indicator.history.length }) }}
                </div>
              </div>

              <p v-if="card.indicator.description" class="mt-3 border-t border-stone-200 pt-3 text-xs leading-5 text-stone-500 dark:border-slate-800 dark:text-slate-500">
                {{ card.indicator.description }}
              </p>
            </article>
          </div>

          <div v-else-if="group.cards.length > 0" class="signal-compact-list">
            <button v-for="card in group.cards" :key="card.indicator.indicator_id" type="button" :aria-expanded="selectedId === card.indicator.indicator_id" @click="selectIndicator(card.indicator.indicator_id)">
              <strong>{{ t('indicator.' + card.indicator.indicator_id, card.indicator.name) }}</strong><span class="signal-list-value">{{ card.valueLabel }}</span><span :class="changeToneClass(card.changeValue)">{{ card.changeLabel }}</span><time>{{ card.lastUpdatedLabel }}</time>
            </button>
          </div>
          <div v-else class="empty-row">
            {{ $t('marketSignals.groupEmpty') }}
          </div>
        </section>
      </template>
      <div v-else-if="!error" class="signal-panel flex min-h-[20rem] items-center justify-center p-8 text-center">
        <div class="max-w-lg">
          <h2 class="text-lg font-semibold text-slate-950 dark:text-white">{{ t('marketSignals.emptyTitle') }}</h2>
          <p class="mt-3 text-sm leading-6 text-stone-600 dark:text-slate-400">{{ t('marketSignals.emptyDescription') }}</p>
          <button type="button" class="app-button-primary app-touch-target mt-5" @click="refresh">{{ t('marketSignals.refresh') }}</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import AppLayoutSwitch from "@/components/AppLayoutSwitch.vue"
import { usePageLayout } from "@/composables/usePageLayout"
import { nextTick, computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import IndicatorChart from '@/components/IndicatorChart.vue'
import { useTheme } from '@/composables/useTheme'
import { useMarketSignalIndicators } from '@/modules/market'

const { theme } = useTheme()
const { t } = useI18n()
const { loading, error, groups, totalCount, load, refresh } = useMarketSignalIndicators()

const activeGroup = ref('all')
const visibleGroups = computed(() => activeGroup.value === 'all' ? groups.value : groups.value.filter(group => group.definition.id === activeGroup.value))

const changeToneClass = (value: number | null) => {
  if (typeof value !== 'number' || Math.abs(value) < 0.01) {
    return 'border-stone-200 bg-stone-100 text-stone-600 dark:border-slate-600 dark:bg-slate-800/70 dark:text-slate-300'
  }
  if (value > 0) {
    return 'border-[#b8d2c4] bg-[#edf3ee] text-[#0f6b4f] dark:border-emerald-400/40 dark:bg-emerald-400/10 dark:text-emerald-300'
  }
  return 'border-[#efc4b5] bg-[#fff3ed] text-[#c84c28] dark:border-orange-400/40 dark:bg-orange-400/10 dark:text-orange-300'
}

onMounted(() => {
  load()
})

const pageLayout = usePageLayout('signals', ['cards', 'compact'] as const, 'cards')
const layoutOptions = computed(() => ['cards', 'compact'].map(value => ({ value, label: t(`workspaceViews.${value}`) })))
const selectedId = ref('')
const selectedCard = computed(() => visibleGroups.value.flatMap(group => group.cards).find(card => card.indicator.indicator_id === selectedId.value))
const selectIndicator = (id: string) => { selectedId.value = selectedId.value === id ? '' : id; if (selectedId.value) void nextTick(() => document.querySelector('.signal-detail')?.scrollIntoView({ block: 'nearest' })) }
</script>

<style scoped>
.signal-page { background: var(--ui-canvas); }
.signal-panel, .metric-card { min-width: 0; border: 1px solid var(--ui-border); background: var(--ui-panel); border-radius: 8px; }
.summary-card { min-width: 0; padding: 12px 16px; border: 1px solid var(--ui-border); border-radius: 6px; background: var(--ui-toolbar); }
.summary-card span, .summary-card em { display: block; color: var(--ui-muted); font-size: 12px; font-style: normal; }
.summary-card strong { display: block; margin-top: 6px; font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--ui-title); }
.summary-card em { margin-top: 4px; }
.category-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 16px; }
.metric-card { padding: 18px; }
.change-pill { flex-shrink: 0; border-width: 1px; border-radius: 4px; padding: 3px 6px; font-size: 12px; font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
.empty-row { border: 1px solid var(--ui-border); border-radius: 6px; background: var(--ui-panel); padding: 32px 20px; text-align: center; color: var(--ui-muted); }

.signal-compact-list { border-block:1px solid var(--ui-border); }
.signal-compact-list button { display:grid; grid-template-columns:minmax(180px,1fr) minmax(100px,.6fr) 100px 140px; gap:18px; align-items:center; width:100%; padding:18px 12px; text-align:left; border-bottom:1px solid var(--ui-border); font-size:13px; }
.signal-compact-list button:hover,.signal-compact-list button[aria-expanded=true] { background:var(--ui-hover); }
.signal-list-value { font-size:18px; font-weight:600; font-variant-numeric:tabular-nums; }
.signal-compact-list time { color:var(--ui-muted); font-size:11px; text-align:right; }
@container app-content (max-width:48rem) { .signal-compact-list button { grid-template-columns:minmax(0,1fr) auto; gap:8px 16px; } .signal-compact-list time { grid-column:1; text-align:left; grid-row:2; } }
</style>

<style scoped>
.signal-navigation .summary-card { border: 0; border-radius: 0; padding: 16px 20px; background: transparent; text-align: left; }
.signal-navigation .summary-card:first-child { padding-left: 0; }
.signal-navigation .summary-card:hover { background: var(--ui-elevated); }
.signal-navigation .summary-card[aria-pressed=true] { background: color-mix(in srgb, var(--ui-accent) 8%, var(--ui-canvas)); }
.signal-navigation .summary-card[aria-pressed=true] strong { color: var(--ui-accent); }
</style>
