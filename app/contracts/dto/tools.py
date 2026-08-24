from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.contracts.tools import ComparePairsCommand, DcaStrategyKey, SimulateDcaCommand


class DCAHistoryPointResponse(BaseModel):
    date: str
    price: float
    invested: float
    value: float
    coins: float
    roi: float
    avg_cost: float


class DCAResponse(BaseModel):
    symbol: str
    asset_class: str | None = None
    price_basis: str | None = None
    pricing_symbol: str | None = None
    pricing_name: str | None = None
    pricing_currency: str | None = None
    data_quality: Literal["exchange", "synthetic_and_exchange_proxy", "index_proxy"]
    start_date: str
    end_date: str
    target_time: str
    total_days: int
    total_invested: float
    final_value: float
    total_coins: float
    roi: float
    average_cost: float
    profit_loss: float
    current_price: float
    history: list[DCAHistoryPointResponse]
    profit_pct: float | None = None


class ToolCandlestickPointResponse(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class PairCompareToolResponse(BaseModel):
    symbol_a: str
    symbol_b: str
    data_a: list[ToolCandlestickPointResponse]
    data_b: list[ToolCandlestickPointResponse]
    ratio_ohlc: list[ToolCandlestickPointResponse]
    ratio_symbol: str
    timeframe: str | None = None
    relative_strength: float | None = None


class ToolsPageContractResponse(BaseModel):
    dca_defaults: SimulateDcaCommand
    dca_strategies: list[DcaStrategyKey]
    dca_multiplier_default: float
    dca_max_days: int
    compare_defaults: ComparePairsCommand
