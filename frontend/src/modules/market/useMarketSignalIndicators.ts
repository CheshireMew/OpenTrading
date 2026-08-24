import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatDate, formatSignedPercent } from '@/modules/format'
import { formatIndicatorDisplayValue } from './indicatorDisplay'
import type { MarketIndicatorResponse } from './contracts'
import { indicatorChangePercent, indicatorLatestValue, parseIndicatorTimestamp } from './indicatorSeries'
import { useMarketIndicatorStore } from './indicatorStore'

export type MarketSignalCategoryId = 'Onchain' | 'Sentiment' | 'Tech'
export type MarketSignalGroupId = 'cycle' | 'stablecoins' | 'mining'

export interface MarketSignalGroupDefinition {
  id: MarketSignalGroupId
  title: string
  eyebrow: string
  description: string
  accent: 'green' | 'amber' | 'blue'
  indicatorIds: string[]
}

export interface MarketSignalIndicatorCard {
  indicator: MarketIndicatorResponse
  valueLabel: string
  changeLabel: string
  changeValue: number | null
  lastUpdatedLabel: string
}

export interface MarketSignalCategoryGroup {
  definition: MarketSignalGroupDefinition
  cards: MarketSignalIndicatorCard[]
  latestUpdatedLabel: string
}

const SOURCE_CATEGORIES: MarketSignalCategoryId[] = ['Onchain', 'Sentiment', 'Tech']

const latestUpdatedLabel = (cards: MarketSignalIndicatorCard[], fallback: string) => {
  const latest = cards
    .map((card) => parseIndicatorTimestamp(card.indicator.last_updated))
    .filter((time): time is number => typeof time === 'number')
    .sort((left, right) => right - left)[0]
  return latest ? formatDate(new Date(latest), fallback) : fallback
}

const cardFromIndicator = (indicator: MarketIndicatorResponse, changeDays: number, fallback: string): MarketSignalIndicatorCard => {
  const changeValue = indicatorChangePercent(indicator, changeDays)
  return {
    indicator,
    valueLabel: formatIndicatorDisplayValue(indicator, indicatorLatestValue(indicator)),
    changeLabel: formatSignedPercent(changeValue),
    changeValue,
    lastUpdatedLabel: formatDate(indicator.last_updated, fallback),
  }
}

export function useMarketSignalIndicators(days = 365, changeDays = 30) {
  const { t } = useI18n()
  const indicatorStore = useMarketIndicatorStore()
  const groupDefinitions = computed<MarketSignalGroupDefinition[]>(() => [
    {
      id: 'cycle',
      eyebrow: 'Cycle & Sentiment',
      title: t('marketSignals.groups.cycle.title'),
      description: t('marketSignals.groups.cycle.description'),
      accent: 'blue',
      indicatorIds: ['BTC_DRAWDOWN', '200WMA', 'GOOGLE_TRENDS_BTC', 'FEAR_GREED'],
    },
    {
      id: 'stablecoins',
      eyebrow: 'Stablecoin Liquidity',
      title: t('marketSignals.groups.stablecoins.title'),
      description: t('marketSignals.groups.stablecoins.description'),
      accent: 'amber',
      indicatorIds: ['STABLECOIN_CAP', 'USDC_CAP', 'USDT_CAP'],
    },
    {
      id: 'mining',
      eyebrow: 'Mining & Network',
      title: t('marketSignals.groups.mining.title'),
      description: t('marketSignals.groups.mining.description'),
      accent: 'green',
      indicatorIds: ['DIFFICULTY', 'HASHRATE', 'S19_BREAKEVEN', 'S21_BREAKEVEN', 'S23_BREAKEVEN'],
    },
  ])
  const indicators = computed<Record<MarketSignalCategoryId, MarketIndicatorResponse[]>>(() => ({
    Onchain: indicatorStore.readMarketIndicators('Onchain', days) || [],
    Sentiment: indicatorStore.readMarketIndicators('Sentiment', days) || [],
    Tech: indicatorStore.readMarketIndicators('Tech', days) || [],
  }))
  const error = computed(() => {
    const key = SOURCE_CATEGORIES.map((category) => indicatorStore.getMarketIndicatorsError(category, days)).find(Boolean)
    return key ? t(key) : ''
  })
  const hasLoadedAllCategories = computed(() => (
    SOURCE_CATEGORIES.every((category) => indicatorStore.readMarketIndicators(category, days) !== null)
  ))
  const loading = computed(() => (
    SOURCE_CATEGORIES.some((category) => indicatorStore.isMarketIndicatorsLoading(category, days))
    || (!hasLoadedAllCategories.value && !error.value)
  ))

  const load = async (options: { force?: boolean } = {}) => {
    await Promise.all(
      SOURCE_CATEGORIES.map((category) => indicatorStore.getMarketIndicators(category, days, options)),
    )
  }

  const refresh = async () => {
    await load({ force: true })
  }

  const groups = computed<MarketSignalCategoryGroup[]>(() => {
    const indicatorMap = new Map(
      SOURCE_CATEGORIES.flatMap((category) => indicators.value[category]).map((indicator) => [indicator.indicator_id, indicator]),
    )
    const notUpdated = t('marketSignals.notUpdated')
    return groupDefinitions.value.map((definition) => {
      const cards = definition.indicatorIds
        .map((indicatorId) => indicatorMap.get(indicatorId))
        .filter((indicator): indicator is MarketIndicatorResponse => Boolean(indicator))
        .map((indicator) => cardFromIndicator(indicator, changeDays, notUpdated))

      return {
        definition,
        cards,
        latestUpdatedLabel: latestUpdatedLabel(cards, notUpdated),
      }
    })
  })

  const totalCount = computed(() => groups.value.reduce((count, group) => count + group.cards.length, 0))
  const populatedGroupCount = computed(() => groups.value.filter((group) => group.cards.length > 0).length)

  return {
    loading,
    error,
    groups,
    totalCount,
    populatedGroupCount,
    load,
    refresh,
  }
}
