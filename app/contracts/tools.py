from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.json_types import JsonObject


DCA_STRATEGY_KEYS = (
    "standard",
    "ema_deviation",
    "rsi_dynamic",
    "ahr999",
    "fear_greed",
    "value_averaging",
)

DCA_MAX_DAYS = 3650


DcaStrategyKey = Literal[
    "standard",
    "ema_deviation",
    "rsi_dynamic",
    "ahr999",
    "fear_greed",
    "value_averaging",
]


class SimulateDcaCommand(BaseModel):
    symbol: str = "BTC/USDT"
    amount: float = Field(100.0, gt=0, le=1_000_000)
    start_date: date | None = None
    investment_time: str = "23:00"
    timezone: str = "Asia/Shanghai"
    days: int | None = Field(None, gt=0, le=DCA_MAX_DAYS)
    strategy: DcaStrategyKey = "standard"
    strategy_params: JsonObject = Field(default_factory=dict)


class ComparePairsCommand(BaseModel):
    symbol_a: str = "BTC"
    symbol_b: str = "ETH"
    days: int = Field(7, gt=0, le=3650)
    timeframe: str = "1h"
