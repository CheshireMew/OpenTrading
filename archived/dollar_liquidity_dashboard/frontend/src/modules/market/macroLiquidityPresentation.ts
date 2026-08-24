import { computed, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DliThresholdsResponse } from './contracts'

export type MacroTone = 'support' | 'pressure' | 'neutral'

export const macroScoreToneClass = (tone: MacroTone) => {
  if (tone === 'support') return 'text-[#0f6b4f] dark:text-emerald-300'
  if (tone === 'pressure') return 'text-[#c84c28] dark:text-orange-300'
  return 'text-[#8a6a24] dark:text-amber-300'
}

export const macroPressureClass = (value: number | null) => {
  if (typeof value !== 'number' || Math.abs(value) < 0.001) return 'text-slate-500 dark:text-slate-400'
  return value >= 0 ? 'text-[#c84c28] dark:text-orange-300' : 'text-[#0f6b4f] dark:text-emerald-300'
}

export const macroThresholdValues = (thresholds: DliThresholdsResponse | null | undefined) => ({
  p20: thresholds?.p20 ?? 43,
  p50: thresholds?.p50 ?? 50,
  p80: thresholds?.p80 ?? 68,
})

export const useMacroRegimes = (thresholds: ComputedRef<DliThresholdsResponse | null>) => {
  const { t } = useI18n()
  return computed(() => {
    const values = macroThresholdValues(thresholds.value)
    return [
    {
      title: t('macro.regimes.loose.title'),
      range: `≤ P20 (${values.p20.toFixed(1)})`,
      color: '#0f6b4f',
      description: t('macro.regimes.loose.description'),
    },
    {
      title: t('macro.regimes.neutralLoose.title'),
      range: `P20-P50 (${values.p20.toFixed(1)}-${values.p50.toFixed(1)})`,
      color: '#8a8f56',
      description: t('macro.regimes.neutralLoose.description'),
    },
    {
      title: t('macro.regimes.neutralTight.title'),
      range: `P50-P80 (${values.p50.toFixed(1)}-${values.p80.toFixed(1)})`,
      color: '#c9873a',
      description: t('macro.regimes.neutralTight.description'),
    },
    {
      title: t('macro.regimes.tight.title'),
      range: `≥ P80 (${values.p80.toFixed(1)})`,
      color: '#c84c28',
      description: t('macro.regimes.tight.description'),
    },
    ]
  })
}
