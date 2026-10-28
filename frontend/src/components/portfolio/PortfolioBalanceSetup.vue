<template>
  <section class="app-hero-panel portfolio-setup-panel p-6">
    <div class="portfolio-setup-grid grid min-w-0 gap-6">
      <div class="grid gap-4 md:grid-cols-2">
        <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">{{ $t('portfolioBalance.portfolioName') }}</span><input :value="activePortfolio.name" type="text" class="app-control w-full px-4 py-3" @input="$emit('update-name', $event.target.value.trim())" /></label>
        <AppDateField :model-value="tracking.inceptionDate" :label="$t('portfolioBalance.inceptionDate')" input-class="app-control w-full px-4 py-3" label-class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300" @update:model-value="$emit('update-inception-date', $event)" />
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div v-for="metric in metrics" :key="metric.label" class="min-w-0 py-2">
          <div class="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ metric.label }}</div>
          <div class="mt-2 break-words text-2xl font-semibold tabular-nums" :class="metric.className">{{ metric.value }}</div>
        </div>
      </div>
    </div>
  </section>

  <section class="app-panel p-6">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <h2 class="text-xl font-semibold text-stone-950 dark:text-white">{{ $t('portfolioBalance.configTitle') }}</h2>
      <div class="flex flex-wrap gap-3">
        <button type="button" class="inline-flex items-center justify-center border border-[#b8d2c4] bg-[#edf3ee] px-4 py-2 text-sm font-medium text-[#0f6b4f] transition hover:bg-[#e1ece4] disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:hover:bg-emerald-900/50" :disabled="marketLoading" @click="$emit('refresh-prices')"><ArrowPathIcon class="mr-2 h-4 w-4" />{{ marketLoading ? $t('portfolioBalance.refreshing') : $t('portfolioBalance.refreshPrices') }}</button>
        <button type="button" class="app-button-secondary inline-flex items-center justify-center px-4 py-2" @click="$emit('add-asset')"><PlusIcon class="mr-2 h-4 w-4" />{{ $t('portfolioBalance.addAsset') }}</button>
      </div>
    </div>
    <div v-if="sourceMessage || sourceError" class="mt-4 space-y-2 text-sm">
      <div v-if="sourceMessage" role="status" aria-live="polite" class="border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-800 dark:border-emerald-900/70 dark:bg-emerald-950/30 dark:text-emerald-200">{{ sourceMessage }}</div>
      <div v-if="sourceError" role="alert" class="border border-rose-200 bg-rose-50 px-4 py-3 text-rose-800 dark:border-rose-900/70 dark:bg-rose-950/30 dark:text-rose-200">{{ sourceError }}</div>
    </div>
    <div class="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.reviewFrequency') }}</span><select :value="strategy.reviewFrequency" class="app-control w-full px-4 py-3" @change="$emit('update-review-frequency', $event.target.value)"><option value="daily">{{ $t('portfolioBalance.frequencies.daily') }}</option><option value="weekly">{{ $t('portfolioBalance.frequencies.weekly') }}</option><option value="monthly">{{ $t('portfolioBalance.frequencies.monthly') }}</option><option value="quarterly">{{ $t('portfolioBalance.frequencies.quarterly') }}</option></select></label>
      <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.virtualCapital', { currency: displayCurrency }) }}</span><input :value="trackingCapitalInput" type="number" min="0" step="1000" class="app-control w-full px-4 py-3" @input="updateMoney('update-tracking-capital', $event.target.value, tracking.virtualCapital)" /></label>
      <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.rebalanceBand') }}</span><input :value="strategy.rebalanceBand" type="number" min="0" max="100" step="0.5" class="app-control w-full px-4 py-3" @input="$emit('update-rebalance-band', Number($event.target.value))" /></label>
      <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.minTradeAmount', { currency: displayCurrency }) }}</span><input :value="minTradeAmountInput" type="number" min="0" step="100" class="app-control w-full px-4 py-3" @input="updateMoney('update-min-trade-amount', $event.target.value, strategy.minTradeAmount)" /></label>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { ArrowPathIcon, PlusIcon } from '@heroicons/vue/24/outline'
import { useI18n } from 'vue-i18n'
import AppDateField from '@/components/AppDateField.vue'
import { formatPercent } from '@/modules/format'
import { useMoney } from '@/composables/useMoney'

const props = defineProps({ activePortfolio: { type: Object, required: true }, tracking: { type: Object, required: true }, strategy: { type: Object, required: true }, plan: { type: Object, required: true }, marketLoading: Boolean, sourceMessage: { type: String, default: '' }, sourceError: { type: String, default: '' } })
const emit = defineEmits(['update-name', 'update-inception-date', 'refresh-prices', 'add-asset', 'update-review-frequency', 'update-tracking-capital', 'update-rebalance-band', 'update-min-trade-amount'])
const { t } = useI18n()
const { displayCurrency, formatMoney, formatDisplayNumber, fromDisplayAmount } = useMoney()
const trackingCapitalInput = computed(() => formatDisplayNumber(props.tracking.virtualCapital, 'USDT', 2))
const minTradeAmountInput = computed(() => formatDisplayNumber(props.strategy.minTradeAmount, 'USDT', 2))
const metrics = computed(() => [
  { label: t('portfolioBalance.totalValue'), value: formatMoney(props.plan.totalValue || 0, 'USDT'), className: 'text-slate-900 dark:text-white' },
  { label: t('portfolioBalance.outOfBand'), value: String(props.plan.outOfBandCount || 0), className: 'text-amber-600 dark:text-amber-300' },
  { label: t('portfolioBalance.maxDrift'), value: formatPercent(props.plan.maxDriftWeight || 0), className: 'text-rose-600 dark:text-rose-300' },
  { label: t('portfolioBalance.virtualCapital', { currency: displayCurrency.value }), value: formatMoney(props.plan.trackingCapital || 0, 'USDT'), className: 'text-emerald-600 dark:text-emerald-300' },
])
const updateMoney = (eventName, value, fallback) => emit(eventName, fromDisplayAmount(value, 'USDT') ?? fallback)
</script>
