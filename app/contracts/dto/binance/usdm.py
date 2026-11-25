from __future__ import annotations

from pydantic import BaseModel, Field

class BinanceMarkPriceItemResponse(BaseModel):
    symbol: str | None = None
    pair: str | None = None
    mark_price: float | None = None
    index_price: float | None = None
    estimated_settle_price: float | None = None
    last_funding_rate: float | None = Field(default=None, description="Funding-rate fraction (0.0001 means 0.01%)")
    next_funding_time: int | None = None
    interest_rate: float | None = None
    time: int | None = None


class BinanceMarkPriceResponse(BaseModel):
    exchange: str
    market: str
    items: list[BinanceMarkPriceItemResponse] = Field(default_factory=list)


class BinanceOpenInterestStatItemResponse(BaseModel):
    symbol: str | None = None
    pair: str | None = None
    contract_type: str | None = None
    sum_open_interest: float | None = None
    sum_open_interest_value: float | None = None
    timestamp: int | None = None


class BinanceOpenInterestStatsResponse(BaseModel):
    exchange: str
    market: str
    items: list[BinanceOpenInterestStatItemResponse] = Field(default_factory=list)


class BinanceRatioItemResponse(BaseModel):
    symbol: str | None = None
    pair: str | None = None
    long_short_ratio: float | None = None
    long_account: float | None = None
    short_account: float | None = None
    long_position: float | None = None
    short_position: float | None = None
    timestamp: int | None = None


class BinanceRatioSeriesResponse(BaseModel):
    exchange: str
    market: str
    items: list[BinanceRatioItemResponse] = Field(default_factory=list)


class BinanceTakerVolumeItemResponse(BaseModel):
    symbol: str | None = None
    pair: str | None = None
    buy_sell_ratio: float | None = None
    buy_vol: float | None = None
    sell_vol: float | None = None
    buy_vol_value: float | None = None
    sell_vol_value: float | None = None
    timestamp: int | None = None


class BinanceTakerVolumeResponse(BaseModel):
    exchange: str
    market: str
    items: list[BinanceTakerVolumeItemResponse] = Field(default_factory=list)


class BinanceBasisItemResponse(BaseModel):
    symbol: str | None = None
    pair: str | None = None
    contract_type: str | None = None
    basis: float | None = None
    basis_rate: float | None = None
    annualized_basis_rate: float | None = None
    futures_price: float | None = None
    index_price: float | None = None
    timestamp: int | None = None


class BinanceBasisResponse(BaseModel):
    exchange: str
    market: str
    items: list[BinanceBasisItemResponse] = Field(default_factory=list)


class BinanceForceOrderItemResponse(BaseModel):
    symbol: str | None = None
    side: str | None = None
    price: float | None = None
    avg_price: float | None = None
    orig_qty: float | None = None
    executed_qty: float | None = None
    cum_quote: float | None = None
    status: str | None = None
    time: int | None = None
    update_time: int | None = None


class BinanceForceOrderResponse(BaseModel):
    exchange: str
    market: str
    items: list[BinanceForceOrderItemResponse] = Field(default_factory=list)


class BinanceContractResearchDetailResponse(BaseModel):
    exchange: str
    market: str
    symbol: str
    period: str
    open_interest: BinanceOpenInterestStatsResponse
    basis: BinanceBasisResponse
    taker_volume: BinanceTakerVolumeResponse
    force_orders: BinanceForceOrderResponse
    long_short_ratio: BinanceRatioSeriesResponse
    top_trader_accounts: BinanceRatioSeriesResponse
    top_trader_positions: BinanceRatioSeriesResponse


