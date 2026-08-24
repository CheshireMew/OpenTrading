<template>
  <section class="app-panel p-6">
    <div class="flex flex-col gap-3">
      <div class="flex items-center justify-between gap-4"><h2 class="text-xl font-semibold text-stone-950 dark:text-white">{{ $t('portfolioBalance.simulationTitle') }}</h2><button type="button" class="inline-flex items-center justify-center border border-[#b8d2c4] bg-[#edf3ee] px-4 py-2 text-sm font-medium text-[#0f6b4f] transition hover:bg-[#e1ece4] disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200 dark:hover:bg-emerald-900/50" :disabled="loading" @click="$emit('run')"><ArrowPathIcon class="mr-2 h-4 w-4" />{{ loading ? $t('portfolioBalance.simulating') : $t('portfolioBalance.simulationRun') }}</button></div>
      <div class="grid gap-4 lg:grid-cols-2"><AppDateField :model-value="simulation.simulationStartDate" :label="$t('portfolioBalance.simulationStartDate')" :max="today" @update:model-value="$emit('update-start-date', $event)" /><label class="block"><span class="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('portfolioBalance.simulationInitialCapital', { currency: displayCurrency }) }}</span><input :value="initialCapitalInput" type="number" min="0" step="1000" class="app-control w-full px-4 py-3" @input="updateInitialCapital($event.target.value)" /></label></div>
    </div>
    <div v-if="result" class="mt-5 space-y-5">
      <div class="border border-stone-200 bg-[#fbfaf7] p-4 dark:border-slate-700 dark:bg-slate-900/60"><div class="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">{{ $t('portfolioBalance.equityCurve') }}</div><div class="h-[320px]"><PortfolioEquityChart :points="result.equityCurve" /></div></div>
      <div class="grid grid-cols-2 gap-3 xl:grid-cols-8">
        <div v-for="metric in metrics" :key="metric.label" class="border border-stone-200 bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/60"><div class="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ metric.label }}</div><div class="mt-1 font-semibold" :class="metric.className">{{ metric.value }}</div></div>
      </div>
    </div>
    <div v-else class="mt-5 border border-stone-200 bg-[#fbfaf7] px-4 py-6 text-center text-sm text-stone-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-400">{{ $t('portfolioBalance.noSimulation') }}</div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import { useI18n } from 'vue-i18n'
import AppDateField from '@/components/AppDateField.vue'
import PortfolioEquityChart from '@/components/PortfolioEquityChart.vue'
import { formatDate, formatPercent, formatSignedPercent } from '@/modules/format'
import { useMoney } from '@/composables/useMoney'

const props = defineProps({ simulation: { type: Object, required: true }, result: { type: Object, default: null }, loading: Boolean, today: { type: String, required: true } })
const emit = defineEmits(['run', 'update-start-date', 'update-initial-capital'])
const { t } = useI18n()
const { displayCurrency, formatDisplayNumber, fromDisplayAmount } = useMoney()
const initialCapitalInput = computed(() => formatDisplayNumber(props.simulation.initialCapital, 'USDT', 2))
const updateInitialCapital = (value) => emit('update-initial-capital', fromDisplayAmount(value, 'USDT') ?? props.simulation.initialCapital)
const returnClass = (value) => value > 0 ? 'text-emerald-600 dark:text-emerald-300' : value < 0 ? 'text-rose-600 dark:text-rose-300' : 'text-slate-600 dark:text-slate-300'
const metrics = computed(() => props.result ? [
  { label: t('portfolioBalance.simulationStartDate'), value: formatDate(props.result.startDate), className: 'text-slate-900 dark:text-white' },
  { label: t('portfolioBalance.simulationEndDate'), value: formatDate(props.result.endDate), className: 'text-slate-900 dark:text-white' },
  { label: t('portfolioBalance.totalReturn'), value: formatSignedPercent(props.result.totalReturnPct), className: returnClass(props.result.totalReturnPct) },
  { label: t('portfolioBalance.annualizedReturn'), value: props.result.annualizedReturnPct === null ? '--' : formatSignedPercent(props.result.annualizedReturnPct), className: returnClass(props.result.annualizedReturnPct || 0) },
  { label: t('portfolioBalance.maxDrawdown'), value: formatPercent(props.result.maxDrawdownPct), className: 'text-rose-600 dark:text-rose-300' },
  { label: t('portfolioBalance.reviewCount'), value: props.result.reviewCount, className: 'text-slate-900 dark:text-white' },
  { label: t('portfolioBalance.outOfBandReviewCount'), value: props.result.outOfBandReviewCount, className: 'text-amber-600 dark:text-amber-300' },
  { label: t('portfolioBalance.rebalanceCount'), value: props.result.rebalanceCount, className: 'text-slate-900 dark:text-white' },
] : [])
</script>
