import { computed, reactive, ref } from 'vue'

import type {
  FactorBlendResponse,
  FactorCatalogItemResponse,
  FactorCatalogResponse,
  FactorDetailResponse,
  FactorExecutionConfig,
  FactorResearchContractResponse,
  FactorResearchRequest,
  FactorResearchRunListItemResponse,
  FactorResearchSummaryResponse,
  FactorScorecardResponse,
} from './contracts'

export type FactorResearchForm = Required<FactorResearchRequest>
export type FactorExecutionForm = Required<Omit<FactorExecutionConfig, 'research_run_id'>>

export const createEmptyFactorResearchForm = (): FactorResearchForm => ({
  symbol: '',
  timeframe: '1d',
  days: 0,
  horizon_bars: 0,
  max_lag_bars: 0,
  categories: [],
  factor_ids: [],
})

export const createEmptyFactorExecutionForm = (): FactorExecutionForm => ({
  initial_cash: 0,
  fee_rate: 0,
  position_size_pct: 0,
  stake_mode: 'fixed',
  entry_threshold: null,
  exit_threshold: null,
  stoploss_pct: 0,
  takeprofit_pct: 0,
  max_hold_bars: 0,
})

export const createFactorResearchForm = (
  contract?: FactorResearchContractResponse | null,
): FactorResearchForm => {
  const defaults = contract?.research_defaults || {}
  return {
    symbol: defaults.symbol || '',
    timeframe: (defaults.timeframe || '1d') as FactorResearchForm['timeframe'],
    days: defaults.days ?? 0,
    horizon_bars: defaults.horizon_bars ?? 0,
    max_lag_bars: defaults.max_lag_bars ?? 0,
    categories: [...(defaults.categories || [])],
    factor_ids: [...(defaults.factor_ids || [])],
  }
}

export const createFactorExecutionForm = (
  contract?: FactorResearchContractResponse | null,
): FactorExecutionForm => {
  const defaults = contract?.execution_defaults || {}
  return {
    initial_cash: defaults.initial_cash ?? 0,
    fee_rate: defaults.fee_rate ?? 0,
    position_size_pct: defaults.position_size_pct ?? 0,
    stake_mode: (defaults.stake_mode || 'fixed') as FactorExecutionForm['stake_mode'],
    entry_threshold: defaults.entry_threshold ?? null,
    exit_threshold: defaults.exit_threshold ?? null,
    stoploss_pct: defaults.stoploss_pct ?? 0,
    takeprofit_pct: defaults.takeprofit_pct ?? 0,
    max_hold_bars: defaults.max_hold_bars ?? 0,
  }
}

export const factorResearchPayload = (form: FactorResearchForm): FactorResearchForm => ({
  symbol: form.symbol,
  timeframe: form.timeframe,
  days: form.days,
  horizon_bars: form.horizon_bars,
  max_lag_bars: form.max_lag_bars,
  categories: [...form.categories],
  factor_ids: [...form.factor_ids],
})

export const factorExecutionPayload = (form: FactorExecutionForm): FactorExecutionForm => ({
  initial_cash: form.initial_cash,
  fee_rate: form.fee_rate,
  position_size_pct: form.position_size_pct,
  stake_mode: form.stake_mode,
  entry_threshold: form.entry_threshold,
  exit_threshold: form.exit_threshold,
  stoploss_pct: form.stoploss_pct,
  takeprofit_pct: form.takeprofit_pct,
  max_hold_bars: form.max_hold_bars,
})

export const createFactorResearchState = () => {
  const loading = ref(false)
  const catalogLoading = ref(false)
  const runsLoading = ref(false)
  const executionLoading = ref<'backtest' | 'paper' | ''>('')
  const error = ref('')
  const catalog = reactive({
    symbols: [] as string[],
    timeframes: [] as string[],
    categories: [] as string[],
    factors: [] as FactorCatalogItemResponse[],
    forward_horizons: [] as number[],
    cleaning: {} as FactorCatalogResponse['cleaning'],
  })
  const form = reactive(createEmptyFactorResearchForm())
  const executionForm = reactive(createEmptyFactorExecutionForm())
  const runs = ref<FactorResearchRunListItemResponse[]>([])
  const summary = ref<FactorResearchSummaryResponse | null>(null)
  const ranking = ref<FactorScorecardResponse[]>([])
  const details = ref<FactorDetailResponse[]>([])
  const blend = ref<FactorBlendResponse | null>(null)
  const selectedFactorId = ref('')
  const selectedRunId = ref<number | null>(null)

  const factorPool = computed(() => {
    if (!form.categories.length) return catalog.factors
    return catalog.factors.filter((item) => form.categories.includes(item.category))
  })
  const selectedDetail = computed(() => details.value.find((item) => item.factor_id === selectedFactorId.value) || details.value[0] || null)
  const selectedRun = computed(() => runs.value.find((item) => item.id === selectedRunId.value) || null)
  const selectedFactorLookup = computed(() => new Set(form.factor_ids))
  const useAllFactors = computed(() => !form.factor_ids.length)

  return {
    loading,
    catalogLoading,
    runsLoading,
    executionLoading,
    error,
    catalog,
    form,
    executionForm,
    runs,
    summary,
    ranking,
    details,
    blend,
    selectedFactorId,
    selectedRunId,
    factorPool,
    selectedDetail,
    selectedRun,
    selectedFactorLookup,
    useAllFactors,
  }
}

export type FactorResearchState = ReturnType<typeof createFactorResearchState>


