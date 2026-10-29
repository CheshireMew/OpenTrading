<template>
  <section class="portfolio-overview space-y-5">
    <div v-if="ledgerState.error" role="alert" class="app-inline-note text-rose-700 dark:text-rose-300">{{ ledgerState.error }} <button type="button" class="ml-3 underline" @click="$emit('navigate', 'ledger')">{{ t('workspaceViews.ledger') }}</button></div>
    <dl class="app-metric-strip portfolio-overview-metrics" :aria-busy="ledgerState.loading">
      <div><dt>{{ t('portfolioLedger.totalEquity') }}</dt><dd>{{ ledger ? formatMoney(ledger.summary.totalEquity) : '—' }}</dd></div>
      <div><dt>{{ t('portfolioLedger.totalPnl') }}</dt><dd :class="tone(ledger?.summary.totalPnl)">{{ ledger ? formatSignedMoney(ledger.summary.totalPnl) : '—' }}</dd></div>
      <div><dt>{{ t('portfolioLedger.return') }}</dt><dd :class="tone(ledger?.summary.simpleReturnPct)">{{ ledger?.summary.simpleReturnPct == null ? '—' : `${ledger.summary.simpleReturnPct.toFixed(2)}%` }}</dd></div>
      <div><dt>{{ t('workspaceViews.allocation') }}</dt><dd>{{ plan.maxDriftWeight.toFixed(2) }}<small class="ml-1 text-sm">pp</small></dd></div>
    </dl>
    <p v-if="ledgerState.loading && !ledger" role="status" class="text-sm app-muted">{{ t('workspaceViews.ledgerPending') }}</p>
    <div v-if="ledger?.summary.issues?.length" class="app-inline-note text-amber-800 dark:text-amber-200"><p>{{ t('portfolioLedger.incomplete') }}</p><ul class="mt-2 list-disc pl-5"><li v-for="issue in ledger.summary.issues" :key="issue">{{ issue }}</li></ul></div>
    <div class="portfolio-overview-grid">
      <section class="app-panel p-5">
        <header class="mb-5 flex flex-wrap items-center justify-between gap-3"><h2 class="app-section-title">{{ t('workspaceViews.allocation') }}</h2><button type="button" class="text-sm underline" @click="$emit('navigate', 'allocation')">{{ t('workspaceViews.review') }}</button></header>
        <p class="mb-3 text-xs app-muted">{{ t('workspaceViews.allocationBasis') }}</p>
        <div v-for="asset in plan.assets" :key="asset.id" class="portfolio-allocation-row">
          <div class="flex items-baseline justify-between gap-3"><strong>{{ asset.symbol || '—' }}</strong><span :class="asset.isOutOfBand ? 'text-amber-700 dark:text-amber-300' : 'app-muted'">{{ (asset.currentWeight * 100).toFixed(1) }}% <small>/ {{ (asset.normalizedTargetWeight * 100).toFixed(1) }}%</small></span></div>
          <div class="portfolio-weight-track" :aria-label="`${asset.symbol}: ${t('workspaceViews.currentWeight')} ${(asset.currentWeight * 100).toFixed(1)}%, ${t('workspaceViews.targetWeight')} ${(asset.normalizedTargetWeight * 100).toFixed(1)}%`"><span :style="{ width: `${Math.min(100, Math.max(0, asset.currentWeight * 100))}%` }" /><i :style="{ left: `${Math.min(100, Math.max(0, asset.normalizedTargetWeight * 100))}%` }" /></div>
        </div>
      </section>
      <section class="app-panel p-5">
        <h2 class="app-section-title mb-5">{{ t('workspaceViews.needsAttention') }}</h2>
        <div v-if="plan.outOfBandCount" class="mb-5"><strong class="text-2xl">{{ plan.outOfBandCount }}</strong> <span class="text-sm app-muted">{{ t('workspaceViews.outOfBand') }}</span><div class="mt-3 flex flex-wrap gap-2"><span v-for="asset in plan.assets.filter(item => item.isOutOfBand)" :key="asset.id" class="app-chip">{{ asset.symbol }} {{ (asset.driftWeight * 100).toFixed(1) }} pp</span></div></div>
        <p v-else class="mb-5 text-sm app-muted">{{ t('workspaceViews.noActions') }}</p>
        <p v-if="missingPrices" class="mb-5 text-sm text-amber-700 dark:text-amber-300">{{ t('workspaceViews.missingPrices', { count: missingPrices }) }}</p>
        <dl v-if="ledger" class="mb-5 flex flex-wrap justify-between gap-3 text-sm"><dt class="app-muted">{{ t('workspaceViews.cash') }}</dt><dd>{{ formatMoney(ledger.summary.cashBalance) }}</dd></dl>
        <div class="flex flex-wrap gap-3"><button type="button" class="app-button-secondary" @click="$emit('navigate', 'ledger')">{{ t('workspaceViews.ledger') }}</button><button type="button" class="app-button-secondary" @click="$emit('navigate', 'risk')">{{ t('workspaceViews.risk') }}</button></div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMoney } from '@/composables/useMoney'
import type { PortfolioBalancePlan } from '@/modules/tools/portfolioBalance/types'
import type { PortfolioLedgerResponse } from '@/modules/tools/generatedContracts'
const props = defineProps<{ plan: PortfolioBalancePlan; ledger: PortfolioLedgerResponse | null; ledgerState: { loading: boolean; error: string } }>()
defineEmits<{ navigate: [section: string] }>()
const { t } = useI18n()
const { formatMoney, formatSignedMoney } = useMoney()
const missingPrices = computed(() => props.plan.assets.filter(asset => asset.units > 0 && !asset.price).length)
const tone = (value?: number | null) => value == null || value === 0 ? '' : value > 0 ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300'
</script>

<style scoped>
.portfolio-overview-metrics { grid-template-columns:repeat(4,minmax(0,1fr)); }
.portfolio-overview-grid { display:grid; grid-template-columns:minmax(0,1.3fr) minmax(0,1fr); gap:20px; align-items:start; }
.portfolio-allocation-row { padding:14px 0; font-size:13px; }
.portfolio-weight-track { height:8px; background:var(--ui-elevated); border-radius:2px; margin-top:12px; position:relative; }
.portfolio-weight-track span { display:block; height:100%; background:var(--ui-accent); border-radius:2px; }
.portfolio-weight-track i { position:absolute; width:2px; height:16px; top:-4px; background:var(--ui-title); transform:translateX(-1px); }
@container app-content (max-width:48rem) { .portfolio-overview-grid { grid-template-columns:minmax(0,1fr); } .portfolio-overview-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); } }
</style>
