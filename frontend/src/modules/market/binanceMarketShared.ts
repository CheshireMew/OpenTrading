import type {
  BinanceBreakoutMonitorItemResponse,
  BinanceBreakoutMonitorResponse,
  BinanceContractBoardItemResponse,
} from './contracts'
import { isRecord, readBoolean, readNumber } from '@/composables/pageSnapshot'
import { toBaseSymbol } from './symbolCatalog'

export type MonitorMode = 'all' | 'natural' | 'momentum' | 'focus'
export type MarketFilter = 'all' | 'spot' | 'usdm'
export type SpotSortField = 'price_change_pct' | 'quote_volume'
export type ContractSortField = 'price_change_pct' | 'funding_rate_pct' | 'quote_volume' | 'oi_change_24h_pct'
export type SortDirection = 'desc' | 'asc'

export type ContractBoardRow = BinanceContractBoardItemResponse

export type ContractSortState = {
  field: ContractSortField
  direction: SortDirection
}

export type SpotSortState = {
  field: SpotSortField
  direction: SortDirection
}

export type ChartDialogState = {
  open: boolean
  rawSymbol: string
  market: string
}

export type BinanceMarketSnapshot = {
  minRisePct: number
  mode: MonitorMode
  marketFilter: MarketFilter
  autoRefresh: boolean
  spotSortField: SpotSortField
  spotSortDirection: SortDirection
  contractSortField: ContractSortField
  contractSortDirection: SortDirection
}

export const EMPTY_RESPONSE: BinanceBreakoutMonitorResponse = {
  exchange: 'binance',
  min_rise_pct: 5,
  quote_asset: 'USDT',
  updated_at: 0,
  summary: {
    monitored_count: 0,
    natural_count: 0,
    momentum_count: 0,
    focus_count: 0,
    advancing_count: 0,
    spot_count: 0,
    contract_count: 0,
  },
  items: [],
}

export const createDefaultSnapshot = (): BinanceMarketSnapshot => ({
  minRisePct: 5,
  mode: 'focus',
  marketFilter: 'all',
  autoRefresh: true,
  spotSortField: 'price_change_pct',
  spotSortDirection: 'desc',
  contractSortField: 'price_change_pct',
  contractSortDirection: 'desc',
})

export const normalizeMode = (value: unknown): MonitorMode => (
  value === 'all' || value === 'natural' || value === 'momentum' || value === 'focus'
    ? value
    : 'focus'
)

export const normalizeMarketFilter = (value: unknown): MarketFilter => (
  value === 'all' || value === 'spot' || value === 'usdm'
    ? value
    : 'all'
)

export const normalizeContractSortField = (value: unknown): ContractSortField => (
  value === 'price_change_pct' || value === 'funding_rate_pct' || value === 'quote_volume' || value === 'oi_change_24h_pct'
    ? value
    : 'price_change_pct'
)

export const normalizeSpotSortField = (value: unknown): SpotSortField => (
  value === 'price_change_pct' || value === 'quote_volume'
    ? value
    : 'price_change_pct'
)

export const normalizeSortDirection = (value: unknown): SortDirection => (
  value === 'asc' || value === 'desc'
    ? value
    : 'desc'
)

export const normalizeSnapshot = (
  value: unknown,
  fallback = createDefaultSnapshot(),
): BinanceMarketSnapshot => {
  const defaults = fallback
  if (!isRecord(value)) return defaults
  return {
    minRisePct: readNumber(value.minRisePct, defaults.minRisePct),
    mode: normalizeMode(value.mode),
    marketFilter: normalizeMarketFilter(value.marketFilter),
    autoRefresh: readBoolean(value.autoRefresh, defaults.autoRefresh),
    spotSortField: normalizeSpotSortField(value.spotSortField),
    spotSortDirection: normalizeSortDirection(value.spotSortDirection),
    contractSortField: normalizeContractSortField(value.contractSortField),
    contractSortDirection: normalizeSortDirection(value.contractSortDirection),
  }
}

export const buildBinanceMarketSnapshot = (snapshot: BinanceMarketSnapshot): BinanceMarketSnapshot => (
  normalizeSnapshot(snapshot)
)

export const formatScore = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return `${Math.round(Number(value))}`
}

export const formatTime = (timestamp: number | null | undefined, locale?: string) => {
  if (!timestamp) return '--'
  return new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp))
}

export const valueTone = (value: number | null | undefined, positiveIsGood = true) => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'text-slate-500 dark:text-slate-400'
  const rising = positiveIsGood ? value >= 0 : value <= 0
  return rising ? 'text-[var(--ui-positiveInk)]' : 'text-[var(--ui-negativeInk)]'
}

export const verdictTone = (verdict: string | null | undefined) => {
  if (verdict === '优先关注') return 'bg-emerald-500/10 text-[var(--ui-positiveInk)] ring-emerald-500/20'
  if (verdict === '继续跟踪') return 'bg-amber-500/10 text-amber-800 ring-amber-500/20 dark:text-amber-300'
  return 'bg-stone-100 text-stone-600 ring-stone-300/70 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-600/40'
}

export const compareNullableNumber = (
  left: number | null | undefined,
  right: number | null | undefined,
  direction: SortDirection,
) => {
  const leftValue = left === null || left === undefined || Number.isNaN(left) ? null : Number(left)
  const rightValue = right === null || right === undefined || Number.isNaN(right) ? null : Number(right)
  if (leftValue === null && rightValue === null) return 0
  if (leftValue === null) return 1
  if (rightValue === null) return -1
  return direction === 'desc' ? rightValue - leftValue : leftValue - rightValue
}

export const sortDirectionIcon = (active: boolean, direction: SortDirection) => {
  if (!active) return '↕'
  return direction === 'desc' ? '↓' : '↑'
}

export const toItemKey = (
  item: Pick<BinanceBreakoutMonitorItemResponse, 'market' | 'symbol'> | Pick<ContractBoardRow, 'market' | 'symbol'> | null | undefined,
) => (item ? `${item.market}:${item.symbol}` : '')

export const displaySymbol = (value: string | null | undefined) => {
  const symbol = String(value || '').trim().toUpperCase()
  if (!symbol) return '--'
  return toBaseSymbol(symbol) || symbol
}

