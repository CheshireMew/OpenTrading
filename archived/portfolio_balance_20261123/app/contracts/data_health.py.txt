from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.json_types import JsonObject


class DataSourceHealthResponse(BaseModel):
    id: str
    name: str
    status: Literal["ready", "stale", "empty", "failed", "stopped", "starting"]
    recordCount: int = Field(ge=0)
    coverageStart: datetime | None = None
    coverageEnd: datetime | None = None
    ageSeconds: float | None = Field(default=None, ge=0)
    gapCount: int | None = Field(default=None, ge=0)
    lastSuccessAt: datetime | None = None
    lastFailureAt: datetime | None = None
    nextRunAt: datetime | None = None
    detail: str = ""
    metadata: JsonObject = Field(default_factory=dict)
    repairActions: list[str] = Field(default_factory=list)


class DataHealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "empty"]
    checkedAt: datetime
    databaseRevision: str | None = None
    sources: list[DataSourceHealthResponse] = Field(default_factory=list)
    summary: JsonObject = Field(default_factory=dict)


class DataRepairCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "verify_database",
        "refresh_binance_snapshot",
        "hydrate_symbol_history",
        "evaluate_research_alerts",
        "evaluate_trade_signals",
    ]
    symbol: str | None = Field(default=None, max_length=160)
    timeframe: str = Field(default="1h", max_length=16)
    days: int = Field(default=365, ge=1, le=3_650)


class DataRepairResponse(BaseModel):
    action: str
    status: Literal["completed", "failed"]
    startedAt: datetime
    completedAt: datetime
    detail: str
    result: JsonObject = Field(default_factory=dict)
