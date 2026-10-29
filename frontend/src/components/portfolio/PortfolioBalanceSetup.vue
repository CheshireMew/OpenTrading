<template>
  <details class="app-panel portfolio-settings">
    <summary class="px-5 py-4 text-sm font-semibold">{{ $t('portfolioBalance.configTitle') }}</summary>
    <div class="border-t p-5" style="border-color:var(--ui-border)">
            <div class="grid gap-4 md:grid-cols-2">
        <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">{{ $t('portfolioBalance.portfolioName') }}</span><input :value="activePortfolio.name" type="text" class="app-control w-full px-4 py-3" @input="$emit('update-name', $event.target.value.trim())" /></label>
        <AppDateField :model-value="tracking.inceptionDate" :label="$t('portfolioBalance.inceptionDate')" input-class="app-control w-full px-4 py-3" label-class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300" @update:model-value="$emit('update-inception-date', $event)" />
      </div>
          <div class="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.reviewFrequency') }}</span><select :value="strategy.reviewFrequency" class="app-control w-full px-4 py-3" @change="$emit('update-review-frequency', $event.target.value)"><option value="daily">{{ $t('portfolioBalance.frequencies.daily') }}</option><option value="weekly">{{ $t('portfolioBalance.frequencies.weekly') }}</option><option value="monthly">{{ $t('portfolioBalance.frequencies.monthly') }}</option><option value="quarterly">{{ $t('portfolioBalance.frequencies.quarterly') }}</option></select></label>
      <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.virtualCapital', { currency: displayCurrency }) }}</span><input :value="trackingCapitalInput" type="number" min="0" step="1000" class="app-control w-full px-4 py-3" @input="updateMoney('update-tracking-capital', $event.target.value, tracking.virtualCapital)" /></label>
      <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.rebalanceBand') }}</span><input :value="strategy.rebalanceBand" type="number" min="0" max="100" step="0.5" class="app-control w-full px-4 py-3" @input="$emit('update-rebalance-band', Number($event.target.value))" /></label>
      <label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.minTradeAmount', { currency: displayCurrency }) }}</span><input :value="minTradeAmountInput" type="number" min="0" step="100" class="app-control w-full px-4 py-3" @input="updateMoney('update-min-trade-amount', $event.target.value, strategy.minTradeAmount)" /></label>
    </div>
      <dl v-if="plan.totalValue > 0" class="app-metric-strip mt-5"><div v-for="metric in metrics" :key="metric.label"><dt>{{ metric.label }}</dt><dd :class="metric.className">{{ metric.value }}</dd></div></dl>
    </div>
  </details>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppDateField from '@/components/AppDateField.vue'
import { formatPercent } from '@/modules/format'
import { useMoney } from '@/composables/useMoney'

const props = defineProps({ activePortfolio: { type: Object, required: true }, tracking: { type: Object, required: true }, strategy: { type: Object, required: true }, plan: { type: Object, required: true } })
const emit = defineEmits(['update-name', 'update-inception-date', 'update-review-frequency', 'update-tracking-capital', 'update-rebalance-band', 'update-min-trade-amount'])
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
