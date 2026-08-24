<template>
  <div :class="['signal-page min-h-full text-slate-900 transition-colors dark:text-slate-100', theme === 'dark' ? 'signal-page--dark' : 'signal-page--light']">
    <section class="flex w-full flex-col gap-8 px-3 py-5 sm:px-4 lg:px-5 xl:px-6">
      <div class="signal-hero max-w-4xl space-y-4 border-b border-stone-200 pb-6 dark:border-slate-800">
        <div class="signal-kicker inline-flex items-center gap-2 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]">
          Market Signal Monitor
        </div>
        <h1 class="signal-title max-w-3xl text-4xl font-semibold leading-tight dark:text-white sm:text-5xl">
          {{ t('marketSignals.title') }}
        </h1>
        <p class="max-w-3xl text-sm leading-6 text-stone-600 dark:text-slate-400 sm:text-base">
          {{ t('marketSignals.subtitle') }}
        </p>
      </div>

      <div v-if="error" class="border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-950/40 dark:text-red-200">
        {{ error }}
      </div>

      <div class="signal-panel p-5">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div class="panel-kicker">{{ t('marketSignals.coverage') }}</div>
            <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ t('marketSignals.overview') }}</h2>
          </div>
          <button class="signal-primary-button self-start" :disabled="loading" @click="refresh">
            {{ loading ? t('marketSignals.refreshing') : t('marketSignals.refresh') }}
          </button>
        </div>

        <div class="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div class="summary-card summary-card--primary">
            <span>{{ t('marketSignals.currentIndicators') }}</span>
            <strong>{{ totalCount }}</strong>
            <em>{{ t('marketSignals.fromGroups', { count: populatedGroupCount }) }}</em>
          </div>
          <div v-for="group in groups" :key="group.definition.id" class="summary-card">
            <span>{{ group.definition.title }}</span>
            <strong>{{ group.cards.length }}</strong>
            <em>{{ t('marketSignals.lastUpdated', { time: group.latestUpdatedLabel }) }}</em>
          </div>
        </div>
      </div>

      <div v-if="loading" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <div v-for="item in 6" :key="item" class="h-72 animate-pulse border border-slate-200 bg-white/70 dark:border-slate-800 dark:bg-slate-900/50"></div>
      </div>

      <template v-else>
        <section v-for="group in groups" :key="group.definition.id" class="space-y-3">
          <div :class="['category-heading', `category-heading--${group.definition.accent}`]">
            <div>
              <div class="panel-kicker">{{ group.definition.eyebrow }}</div>
              <h2 class="mt-2 text-lg font-semibold text-slate-950 dark:text-white">{{ group.definition.title }}</h2>
              <p class="mt-1 text-sm text-slate-500 dark:text-slate-500">{{ group.definition.description }}</p>
            </div>
            <div class="text-sm font-semibold text-slate-500 dark:text-slate-400">{{ t('marketSignals.itemCount', { count: group.cards.length }) }}</div>
          </div>

          <div v-if="group.cards.length > 0" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <article v-for="card in group.cards" :key="card.indicator.indicator_id" class="metric-card">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-xs uppercase tracking-wide text-stone-500 dark:text-slate-500">
                    {{ card.indicator.indicator_id }}
                  </div>
                  <h3 class="mt-1 text-sm font-semibold text-slate-950 dark:text-white">
                    {{ $t('indicator.' + card.indicator.indicator_id, card.indicator.name) }}
                  </h3>
                </div>
                <span :class="['change-pill', changeToneClass(card.changeValue)]">{{ card.changeLabel }}</span>
              </div>

              <div class="mt-4 flex items-end justify-between gap-3">
                <div class="min-w-0 text-2xl font-semibold text-slate-950 dark:text-white">{{ card.valueLabel }}</div>
                <div class="text-right text-[11px] text-stone-500 dark:text-slate-500">{{ card.lastUpdatedLabel }}</div>
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

          <div v-else class="empty-row">
            {{ $t('common.waitingData') }}
          </div>
        </section>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import IndicatorChart from '@/components/IndicatorChart.vue'
import { useTheme } from '@/composables/useTheme'
import { useMarketSignalIndicators } from '@/modules/market'

const { theme } = useTheme()
const { t } = useI18n()
const { loading, error, groups, totalCount, populatedGroupCount, load, refresh } = useMarketSignalIndicators()

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
</script>

<style scoped>
.signal-page {
  background: #f7f4ed;
}

.signal-page--dark {
  background:
    radial-gradient(circle at top left, rgba(15, 107, 79, 0.12), transparent 32rem),
    linear-gradient(180deg, #020713 0%, #030816 52%, #020617 100%);
}

.signal-panel,
.metric-card {
  border: 1px solid #e4ded3;
  background: rgba(255, 255, 255, 0.88);
}

.signal-page--dark .signal-panel,
.signal-page--dark .metric-card {
  border-color: rgba(30, 41, 59, 0.95);
  background: rgba(2, 6, 23, 0.72);
}

.signal-kicker {
  border: 1px solid #cfded4;
  background: #edf3ee;
  color: #0f6b4f;
}

.signal-page--dark .signal-kicker {
  border-color: rgba(52, 211, 153, 0.3);
  background: rgba(52, 211, 153, 0.1);
  color: #6ee7b7;
}

.signal-title {
  color: #14110f;
  font-family: Georgia, "Times New Roman", serif;
  letter-spacing: 0;
}

.signal-page--dark .signal-title {
  color: #f8fafc;
}

.panel-kicker {
  color: #0f6b4f;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.signal-page--dark .panel-kicker {
  color: #34d399;
}

.signal-primary-button {
  border: 1px solid #0f6b4f;
  background: #0f6b4f;
  color: #ffffff;
  padding: 0.65rem 0.95rem;
  font-size: 0.82rem;
  font-weight: 700;
  transition: background-color 0.18s ease, border-color 0.18s ease;
}

.signal-primary-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.summary-card {
  min-width: 0;
  border: 1px solid #eee7dc;
  background: #fbfaf7;
  padding: 0.7rem 0.8rem;
}

.signal-page--dark .summary-card {
  border-color: rgba(30, 41, 59, 0.75);
  background: rgba(15, 23, 42, 0.32);
}

.summary-card span {
  display: block;
  font-size: 0.68rem;
  color: #78716c;
}

.summary-card strong {
  margin-top: 0.35rem;
  display: block;
  font-size: 1.1rem;
}

.summary-card--primary strong {
  color: #0f6b4f;
  font-size: 2rem;
  line-height: 1;
}

.summary-card em {
  display: block;
  margin-top: 0.35rem;
  color: #78716c;
  font-size: 0.78rem;
  font-style: normal;
}

.signal-page--dark .summary-card span,
.signal-page--dark .summary-card em {
  color: #94a3b8;
}

.category-heading {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  border-left: 2px solid #0f6b4f;
  padding-left: 0.75rem;
}

.category-heading--amber {
  border-left-color: #b7791f;
}

.category-heading--blue {
  border-left-color: #1d6fba;
}

@media (min-width: 640px) {
  .category-heading {
    flex-direction: row;
    align-items: flex-end;
    justify-content: space-between;
  }
}

.metric-card {
  min-height: 24rem;
  padding: 1rem;
}

.change-pill {
  flex-shrink: 0;
  border-width: 1px;
  padding: 0.18rem 0.4rem;
  font-size: 0.68rem;
  font-weight: 700;
  white-space: nowrap;
}

.empty-row {
  border: 1px solid #e4ded3;
  background: rgba(255, 255, 255, 0.64);
  padding: 2rem;
  text-align: center;
  color: #78716c;
}

.signal-page--dark .empty-row {
  border-color: rgba(30, 41, 59, 0.95);
  background: rgba(2, 6, 23, 0.48);
  color: #94a3b8;
}
</style>
