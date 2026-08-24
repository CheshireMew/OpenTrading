from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TradeSetupResponseItem(BaseModel):
    side: str
    entry: float
    target: float
    stop: float
    risk_reward: float
    confidence: int
    risk_amount: float
    entry_time: int
    style: str
    strategy: str
    source: str


class TradeSetupResponse(BaseModel):
    symbol: str
    timeframe: str
    timestamp: str
    current_price: float | None
    setup: TradeSetupResponseItem | None
    reason: str
    source: str
    status: Literal["ready", "waiting", "unavailable", "rejected"]
    error_code: str | None


class IndicatorHistoryPoint(BaseModel):
    date: str
    value: float


class MarketIndicatorResponse(BaseModel):
    indicator_id: str
    name: str
    category: str
    unit: str | None
    current_value: float | None
    last_updated: str | None
    data_lag_days: int | None = None
    short_label: str | None = None
    group: str | None = None
    group_label: str | None = None
    group_description: str | None = None
    polarity: str | None = None
    description: str | None = None
    is_scored: bool | None = None
    history: list[IndicatorHistoryPoint]
