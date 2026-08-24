from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.factor import FactorExecutionConfig
from app.contracts.json_types import JsonObject


class FactorCatalogItemResponse(BaseModel):
    factor_id: str
    name: str
    category: str
    source: str
    unit: str | None = None
    feature_mode: str
    description: str | None = None


class FactorCatalogResponse(BaseModel):
    symbols: list[str]
    timeframes: list[str]
    categories: list[str]
    factors: list[FactorCatalogItemResponse]
    forward_horizons: list[int]
    cleaning: JsonObject


class FactorResearchRequest(BaseModel):
    symbol: str = "BTC/USDT"
    timeframe: Literal["1h", "4h", "1d"] = "1d"
    days: int = Field(default=365, ge=60, le=1460)
    horizon_bars: int = Field(default=3, ge=1, le=30)
    max_lag_bars: int = Field(default=7, ge=0, le=30)
    categories: list[str] = Field(default_factory=list)
    factor_ids: list[str] = Field(default_factory=list)


class FactorSampleRangeResponse(BaseModel):
    start: str
    end: str


class FactorForwardMetricResponse(BaseModel):
    horizon: int
    sample_size: int
    target_mean: float | None = None
    target_std: float | None = None
    correlation: float
    rank_correlation: float
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_t_stat: float
    quantile_spread: float
    hit_rate: float


class FactorResearchSummaryResponse(BaseModel):
    symbol: str
    timeframe: str
    days: int
    horizon_bars: int
    max_lag_bars: int
    factor_count: int
    dataset_id: int
    forward_horizons: list[int]
    sample_range: FactorSampleRangeResponse
    target_label: str
    blend_factor_count: int


class FactorScorecardResponse(BaseModel):
    factor_id: str
    name: str
    category: str
    feature_mode: str
    sample_size: int
    latest_value: float
    correlation: float
    rank_correlation: float
    best_lag: int
    best_lag_correlation: float
    stability: float
    quantile_spread: float
    hit_rate: float
    turnover: float
    ic_ir: float
    direction: str
    score: float


class FactorLagPointResponse(BaseModel):
    lag: int
    correlation: float


class FactorRollingPointResponse(BaseModel):
    date: str
    value: float


class FactorQuantileBucketResponse(BaseModel):
    bucket: int
    label: str
    avg_future_return: float
    count: int


class FactorNormalizedPointResponse(BaseModel):
    date: str
    price_z: float
    factor_z: float
    future_return: float


class FactorDetailResponse(BaseModel):
    factor_id: str
    name: str
    category: str
    unit: str | None = None
    feature_mode: str
    description: str | None = None
    sample_range: FactorSampleRangeResponse
    sample_size: int
    latest_raw_value: float
    latest_feature_value: float
    target_mean: float
    target_std: float
    correlation: float
    rank_correlation: float
    best_lag: int
    best_lag_correlation: float
    stability: float
    quantile_spread: float
    hit_rate: float
    turnover: float
    ic_mean: float
    ic_std: float
    ic_ir: float
    ic_t_stat: float
    forward_metrics: list[FactorForwardMetricResponse]
    lag_profile: list[FactorLagPointResponse]
    rolling_correlation: list[FactorRollingPointResponse]
    quantiles: list[FactorQuantileBucketResponse]
    normalized_series: list[FactorNormalizedPointResponse]


class FactorBlendComponentResponse(BaseModel):
    factor_id: str
    name: str
    category: str
    score: float
    correlation: float
    stability: float
    turnover: float
    weight: float


class FactorDroppedComponentResponse(BaseModel):
    factor_id: str
    name: str
    reason: str


class FactorBlendResponse(BaseModel):
    selected_factors: list[FactorBlendComponentResponse]
    dropped_factors: list[FactorDroppedComponentResponse]
    weights: list[FactorBlendComponentResponse]
    forward_metrics: list[FactorForwardMetricResponse]
    quantiles: list[FactorQuantileBucketResponse]
    normalized_series: list[FactorNormalizedPointResponse]
    entry_threshold: float
    exit_threshold: float
    score_std: float
    score_mean: float


class FactorResearchResponse(BaseModel):
    run_id: int
    dataset_id: int
    summary: FactorResearchSummaryResponse
    ranking: list[FactorScorecardResponse]
    details: list[FactorDetailResponse]
    blend: FactorBlendResponse


class FactorResearchRunListItemResponse(BaseModel):
    id: int
    dataset_id: int
    status: str
    request: FactorResearchRequest
    summary: FactorResearchSummaryResponse
    ranking: list[FactorScorecardResponse]
    blend: FactorBlendResponse
    error: str | None = None
    created_at: str | None


class FactorResearchRunDetailResponse(FactorResearchRunListItemResponse):
    details: list[FactorDetailResponse]


class FactorExecutionResponse(BaseModel):
    success: bool
    run_id: int
    message: str


class FactorResearchContractResponse(BaseModel):
    research_defaults: FactorResearchRequest
    execution_defaults: FactorExecutionConfig
