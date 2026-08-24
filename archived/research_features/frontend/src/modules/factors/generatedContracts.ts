// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

export interface FactorResearchContractResponse {
  research_defaults: FactorResearchRequest
  execution_defaults: FactorExecutionConfig
}

export interface FactorCatalogResponse {
  symbols: Array<string>
  timeframes: Array<string>
  categories: Array<string>
  factors: Array<FactorCatalogItemResponse>
  forward_horizons: Array<number>
  cleaning: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface FactorResearchResponse {
  run_id: number
  dataset_id: number
  summary: FactorResearchSummaryResponse
  ranking: Array<FactorScorecardResponse>
  details: Array<FactorDetailResponse>
  blend: FactorBlendResponse
}

export interface FactorResearchRequest {
  symbol?: string
  timeframe?: "1h" | "4h" | "1d"
  days?: number
  horizon_bars?: number
  max_lag_bars?: number
  categories?: Array<string>
  factor_ids?: Array<string>
}

export interface FactorResearchRunListItemResponse {
  id: number
  dataset_id: number
  status: string
  request: FactorResearchRequest
  summary: FactorResearchSummaryResponse
  ranking: Array<FactorScorecardResponse>
  blend: FactorBlendResponse
  error?: string | null
  created_at: string | null
}

export interface FactorResearchRunDetailResponse {
  id: number
  dataset_id: number
  status: string
  request: FactorResearchRequest
  summary: FactorResearchSummaryResponse
  ranking: Array<FactorScorecardResponse>
  blend: FactorBlendResponse
  error?: string | null
  created_at: string | null
  details: Array<FactorDetailResponse>
}

export interface FactorExecutionResponse {
  success: boolean
  run_id: number
  message: string
}

export interface FactorExecutionConfig {
  research_run_id?: number | null
  initial_cash?: number
  fee_rate?: number
  position_size_pct?: number
  stake_mode?: "fixed" | "unlimited"
  entry_threshold?: number | null
  exit_threshold?: number | null
  stoploss_pct?: number
  takeprofit_pct?: number
  max_hold_bars?: number
}

export interface FactorBlendComponentResponse {
  factor_id: string
  name: string
  category: string
  score: number
  correlation: number
  stability: number
  turnover: number
  weight: number
}

export interface FactorBlendResponse {
  selected_factors: Array<FactorBlendComponentResponse>
  dropped_factors: Array<FactorDroppedComponentResponse>
  weights: Array<FactorBlendComponentResponse>
  forward_metrics: Array<FactorForwardMetricResponse>
  quantiles: Array<FactorQuantileBucketResponse>
  normalized_series: Array<FactorNormalizedPointResponse>
  entry_threshold: number
  exit_threshold: number
  score_std: number
  score_mean: number
}

export interface FactorCatalogItemResponse {
  factor_id: string
  name: string
  category: string
  source: string
  unit?: string | null
  feature_mode: string
  description?: string | null
}

export interface FactorDetailResponse {
  factor_id: string
  name: string
  category: string
  unit?: string | null
  feature_mode: string
  description?: string | null
  sample_range: FactorSampleRangeResponse
  sample_size: number
  latest_raw_value: number
  latest_feature_value: number
  target_mean: number
  target_std: number
  correlation: number
  rank_correlation: number
  best_lag: number
  best_lag_correlation: number
  stability: number
  quantile_spread: number
  hit_rate: number
  turnover: number
  ic_mean: number
  ic_std: number
  ic_ir: number
  ic_t_stat: number
  forward_metrics: Array<FactorForwardMetricResponse>
  lag_profile: Array<FactorLagPointResponse>
  rolling_correlation: Array<FactorRollingPointResponse>
  quantiles: Array<FactorQuantileBucketResponse>
  normalized_series: Array<FactorNormalizedPointResponse>
}

export interface FactorDroppedComponentResponse {
  factor_id: string
  name: string
  reason: string
}

export interface FactorForwardMetricResponse {
  horizon: number
  sample_size: number
  target_mean?: number | null
  target_std?: number | null
  correlation: number
  rank_correlation: number
  ic_mean: number
  ic_std: number
  ic_ir: number
  ic_t_stat: number
  quantile_spread: number
  hit_rate: number
}

export interface FactorLagPointResponse {
  lag: number
  correlation: number
}

export interface FactorNormalizedPointResponse {
  date: string
  price_z: number
  factor_z: number
  future_return: number
}

export interface FactorQuantileBucketResponse {
  bucket: number
  label: string
  avg_future_return: number
  count: number
}

export interface FactorResearchSummaryResponse {
  symbol: string
  timeframe: string
  days: number
  horizon_bars: number
  max_lag_bars: number
  factor_count: number
  dataset_id: number
  forward_horizons: Array<number>
  sample_range: FactorSampleRangeResponse
  target_label: string
  blend_factor_count: number
}

export interface FactorRollingPointResponse {
  date: string
  value: number
}

export interface FactorSampleRangeResponse {
  start: string
  end: string
}

export interface FactorScorecardResponse {
  factor_id: string
  name: string
  category: string
  feature_mode: string
  sample_size: number
  latest_value: number
  correlation: number
  rank_correlation: number
  best_lag: number
  best_lag_correlation: number
  stability: number
  quantile_spread: number
  hit_rate: number
  turnover: number
  ic_ir: number
  direction: string
  score: number
}

export interface ListFactorRunsQueryParams {
  limit?: number
}
