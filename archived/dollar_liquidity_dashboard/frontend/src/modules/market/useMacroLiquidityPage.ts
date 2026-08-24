import { computed, unref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatCompactNumber, formatSignedPercent } from '@/modules/format'
import type { DliComponentResponse, DliLiquidityResponse, MarketIndicatorResponse } from './contracts'
import { indicatorChangePercent, indicatorLatestValue, parseIndicatorTimestamp } from './indicatorSeries'
import { useMacroLiquidityStore } from './macroLiquidityStore'

export type MacroGroupId = 'policy' | 'funding' | 'credit' | 'risk'
export type MacroPolarity = 'higherTightens' | 'lowerTightens'

export interface MacroIndicatorDefinition {
  id: string
  label: string
  shortLabel: string
  group: MacroGroupId
  groupLabel: string
  groupDescription: string
  polarity: MacroPolarity
  description: string
}

export interface MacroMetricCard {
  definition: MacroIndicatorDefinition
  indicator: MarketIndicatorResponse | null
  valueLabel: string
  changeLabel: string
  changeValue: number | null
  tone: 'support' | 'pressure' | 'neutral'
  freshness: string
  dataLagDays: number | null
  dataLagLabel: string
}

export interface MacroDriver extends MacroMetricCard {
  score: number
  pressure: number
  contribution: number | null
  rawWeight: number
  effectiveWeight: number
  zScore: number | null
  percentile: number | null
}

const formatDateLabel = (value: string | null | undefined, locale: string, fallback: string) => {
  const time = parseIndicatorTimestamp(value)
  if (!time) return fallback
  return new Intl.DateTimeFormat(locale, { month: '2-digit', day: '2-digit' }).format(new Date(time))
}

export const formatMacroValue = (indicator: MarketIndicatorResponse | null) => {
  const value = indicatorLatestValue(indicator)
  if (value === null) return '--'
  switch (indicator?.indicator_id) {
    case 'FED_BALANCE':
      return `$${(value / 1_000_000).toFixed(2)}T`
    case 'TGA':
      return `$${(value / 1_000).toFixed(1)}B`
    case 'ONRRP':
    case 'SRF_USAGE':
      return `$${value.toFixed(1)}B`
    case 'SOFR_IORB':
      return `${value.toFixed(1)}bp`
    case 'M2':
      return `$${(value / 1_000).toFixed(2)}T`
    case 'NET_LIQUIDITY':
      return `$${(value / 1_000_000).toFixed(2)}T`
    case 'GOLD':
    case 'WTI':
      return `$${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
    case 'NASDAQ':
    case 'DXY':
    case 'VIX':
      return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
    case 'FED_RATE':
    case 'SOFR':
    case 'US10Y_REAL':
    case 'BANK_CASH_BUFFER':
    case 'US02Y':
    case 'HY_SPREAD':
      return `${value.toFixed(2)}%`
    default:
      return indicator?.unit ? `${formatCompactNumber(value)} ${indicator.unit}` : formatCompactNumber(value)
  }
}

const metricTone = (definition: MacroIndicatorDefinition, change: number | null): MacroMetricCard['tone'] => {
  if (change === null || Math.abs(change) < 0.01) return 'neutral'
  const pressure = definition.polarity === 'higherTightens' ? change > 0 : change < 0
  return pressure ? 'pressure' : 'support'
}

const normalizePolarity = (value: string | null | undefined): MacroPolarity => (
  value === 'higher_tightens' || value === 'higherTightens' ? 'higherTightens' : 'lowerTightens'
)

const definitionFromIndicator = (indicator: MarketIndicatorResponse): MacroIndicatorDefinition => ({
  id: indicator.indicator_id,
  label: indicator.name,
  shortLabel: indicator.short_label || indicator.name,
  group: (indicator.group as MacroGroupId) || 'risk',
  groupLabel: indicator.group_label || '风险与价格',
  groupDescription: indicator.group_description || '',
  polarity: normalizePolarity(indicator.polarity),
  description: indicator.description || '',
})

const definitionFromComponent = (component: DliComponentResponse): MacroIndicatorDefinition => {
  return {
    id: component.indicator_id,
    label: component.name,
    shortLabel: component.short_label,
    group: (component.group as MacroGroupId) || 'risk',
    groupLabel: component.group_label,
    groupDescription: component.group_description || '',
    polarity: normalizePolarity(component.polarity),
    description: '',
  }
}

export function useMacroLiquidityPage(days: number | Ref<number> = 365, changeDays: number | Ref<number> = 30) {
  const { t, locale } = useI18n()
  const macroLiquidityStore = useMacroLiquidityStore()
  const formatLagLabel = (value: number | null | undefined) => {
    if (typeof value !== 'number') return t('macro.lagUnknown')
    if (value <= 0) return t('macro.updatedToday')
    return t('macro.lagDays', { count: value })
  }
  const currentDays = computed(() => unref(days))
  const currentChangeDays = computed(() => unref(changeDays))
  const dli = computed<DliLiquidityResponse | null>(() => (
    macroLiquidityStore.readDliLiquidity(currentDays.value, currentChangeDays.value)
  ))
  const indicators = computed<MarketIndicatorResponse[]>(() => dli.value?.indicators || [])
  const error = computed(() => {
    const key = macroLiquidityStore.getDliLiquidityError(currentDays.value, currentChangeDays.value)
    return key ? t(key) : ''
  })
  const loading = computed(() => (
    macroLiquidityStore.isDliLiquidityLoading(currentDays.value, currentChangeDays.value)
    || (!dli.value && !error.value)
  ))

  const load = async (options: { force?: boolean } = {}) => {
    await macroLiquidityStore.getDliLiquidity(currentDays.value, currentChangeDays.value, options)
  }

  const refresh = async () => {
    await load({ force: true })
  }

  const indicatorMap = computed(() => new Map(indicators.value.map((item) => [item.indicator_id, item])))

  const changeWindowDays = computed(() => unref(changeDays))
  const changeWindowLabel = computed(() => t('macro.dayCount', { count: changeWindowDays.value }))

  const definitions = computed(() => indicators.value.map(definitionFromIndicator))

  const cards = computed<MacroMetricCard[]>(() => definitions.value.map((definition) => {
    const indicator = indicatorMap.value.get(definition.id) || null
    const change = indicatorChangePercent(indicator, changeWindowDays.value)
    return {
      definition,
      indicator,
      valueLabel: formatMacroValue(indicator),
      changeLabel: formatSignedPercent(change),
      changeValue: change,
      tone: metricTone(definition, change),
      freshness: formatDateLabel(indicator?.last_updated, locale.value, t('macro.notUpdated')),
      dataLagDays: indicator?.data_lag_days ?? null,
      dataLagLabel: formatLagLabel(indicator?.data_lag_days),
    }
  }))

  const score = computed(() => dli.value?.score ?? null)
  const rawScore = computed(() => dli.value?.raw_score ?? null)
  const scorePercentile = computed(() => dli.value?.score_percentile ?? null)
  const scoreLabel = computed(() => dli.value?.state || t('macro.waitingData'))
  const scoreTone = computed(() => dli.value?.tone || 'neutral')
  const thresholds = computed(() => dli.value?.thresholds || null)

  const groups = computed(() => Array.from(new Set(cards.value.map((card) => card.definition.group))).map((group) => {
    const groupCards = cards.value.filter((card) => card.definition.group === group)
    const firstDefinition = groupCards[0]?.definition
    return {
      id: group,
      title: firstDefinition?.groupLabel || group,
      description: firstDefinition?.groupDescription || '',
      cards: groupCards,
    }
  }))

  const drivers = computed<MacroDriver[]>(() => (dli.value?.components || []).map((component) => {
    const definition = definitionFromComponent(component)
    const card = cards.value.find((item) => item.definition.id === component.indicator_id)
    const driverScore = Math.round(component.score ?? 50)
    return {
      definition,
      indicator: card?.indicator || null,
      valueLabel: card?.valueLabel || '--',
      changeLabel: typeof component.change_pct === 'number' ? formatSignedPercent(component.change_pct) : (card?.changeLabel || '--'),
      changeValue: component.change_pct ?? card?.changeValue ?? null,
      tone: driverScore >= 50 ? 'pressure' : 'support',
      freshness: card?.freshness || formatDateLabel(component.last_updated, locale.value, t('macro.notUpdated')),
      dataLagDays: component.data_lag_days ?? card?.dataLagDays ?? null,
      dataLagLabel: formatLagLabel(component.data_lag_days ?? card?.dataLagDays),
      score: driverScore,
      pressure: Math.round(100 - driverScore),
      contribution: component.contribution,
      rawWeight: component.weight,
      effectiveWeight: component.effective_weight,
      zScore: component.z_score,
      percentile: component.percentile,
    }
  }))

  const alerts = computed(() => dli.value?.alerts?.length ? dli.value.alerts : [t('macro.waitingAlert')])

  const lastUpdated = computed(() => {
    const time = parseIndicatorTimestamp(dli.value?.updated_at)
    if (!time) return t('macro.notUpdated')
    return new Intl.DateTimeFormat(locale.value, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(time))
  })

  return {
    dli,
    indicators,
    loading,
    error,
    cards,
    score,
    rawScore,
    scorePercentile,
    scoreLabel,
    scoreTone,
    thresholds,
    groups,
    drivers,
    alerts,
    lastUpdated,
    changeWindowDays,
    changeWindowLabel,
    load,
    refresh,
  }
}

