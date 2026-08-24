import type { FactorResearchState } from './state'
import { formatDate, formatLocalizedNumber, formatRatioPercent } from '@/modules/format'


export const useFactorResearchFormatting = (state: FactorResearchState) => {
  const factorChipClass = (factorId: string) => {
    const active = state.useAllFactors.value || state.selectedFactorLookup.value.has(factorId)
    return active
      ? 'bg-[#0f6b4f] text-white border-[#0f6b4f]'
      : 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-900 dark:text-slate-400 dark:border-slate-700'
  }

  const categoryChipClass = (category: string) => (
    state.form.categories.includes(category)
      ? 'bg-[#0f6b4f] text-white border-[#0f6b4f] dark:bg-emerald-600 dark:border-emerald-500'
      : 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-900 dark:text-slate-400 dark:border-slate-700'
  )

  const scoreClass = (score: number) => {
    if (score >= 70) return 'text-emerald-600 dark:text-emerald-400'
    if (score >= 45) return 'text-amber-600 dark:text-amber-300'
    return 'text-slate-500 dark:text-slate-400'
  }

  const correlationClass = (value: number) => {
    if (value > 0) return 'text-emerald-600 dark:text-emerald-400'
    if (value < 0) return 'text-rose-600 dark:text-rose-400'
    return 'text-slate-500 dark:text-slate-400'
  }

  return {
    factorChipClass,
    categoryChipClass,
    scoreClass,
    correlationClass,
    formatPct: (value: number | null | undefined, digits: number = 2) => formatRatioPercent(value, digits, { empty: '--' }),
    formatNumber: (value: number | null | undefined, digits: number = 3) => formatLocalizedNumber(value, digits),
    formatDate,
  }
}

