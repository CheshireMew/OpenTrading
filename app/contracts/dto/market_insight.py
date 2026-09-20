from __future__ import annotations


from pydantic import BaseModel


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
