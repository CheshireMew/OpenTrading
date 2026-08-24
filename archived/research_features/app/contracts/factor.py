from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FactorExecutionConfig(BaseModel):
    research_run_id: int | None = None
    initial_cash: float = Field(default=100000.0, gt=0)
    fee_rate: float = Field(default=0.1, ge=0, le=100)
    position_size_pct: float = Field(default=25.0, gt=0, le=100)
    stake_mode: Literal["fixed", "unlimited"] = "fixed"
    entry_threshold: float | None = None
    exit_threshold: float | None = None
    stoploss_pct: float = Field(default=-0.08, ge=-1.0, le=0.0)
    takeprofit_pct: float = Field(default=0.16, ge=0.0, le=10.0)
    max_hold_bars: int = Field(default=20, ge=1, le=365)

    def require_research_run_id(self) -> int:
        if self.research_run_id is None:
            raise ValueError("缺少因子研究记录 ID")
        return self.research_run_id
