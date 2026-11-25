from __future__ import annotations


from datetime import datetime
from app.contracts.timestamps import UtcResponseModel


class IndicatorHistoryPoint(UtcResponseModel):
    date: datetime
    value: float


class MarketIndicatorResponse(UtcResponseModel):
    indicator_id: str
    name: str
    category: str
    unit: str | None
    current_value: float | None
    last_updated: datetime | None
    data_lag_days: int | None = None
    short_label: str | None = None
    group: str | None = None
    group_label: str | None = None
    group_description: str | None = None
    polarity: str | None = None
    description: str | None = None
    is_scored: bool | None = None
    history: list[IndicatorHistoryPoint]
