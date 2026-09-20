"""Public contracts for the independent chart workspace."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ChartSymbol(BaseModel):
    id: str
    symbol: str
    name: str
    exchange: str
    market: Literal["spot", "usdm", "index"]
    currency: str
    timeframes: list[str]
    close_only: bool = False
    timezone: str = "Etc/UTC"
    session: str = "24x7"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChartBar(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    closeTime: int
    closed: bool


class ChartBars(BaseModel):
    symbol: ChartSymbol
    timeframe: str
    bars: list[ChartBar]
    source: str


class ChartQuote(BaseModel):
    id: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    basis: str = "24h"
    updated_at: int
    error: str | None = None


class WorkspaceDocument(BaseModel):
    id: str
    name: str
    version: int
    data: dict[str, Any]
    updated_at: int
    readonly: bool = False


class WorkspaceWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    data: dict[str, Any]
    expected_version: int = Field(0, ge=0)


class PineRunRequest(BaseModel):
    script_id: str
    script_version: int = Field(ge=1)
    symbol: str
    timeframe: str
    start: int
    end: int
    inputs: dict[str, Any] = Field(default_factory=dict)
    props: dict[str, Any] = Field(default_factory=dict)


class PineRun(BaseModel):
    id: str
    status: Literal["queued", "loading", "running", "completed", "failed", "cancelled", "interrupted"]
    progress: float = 0
    created_at: int
    request: PineRunRequest
    error: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class PineRecords(BaseModel):
    items: list[dict[str, Any]]
    total: int
    offset: int


class PineCapabilities(BaseModel):
    engine: str = "PineTS"
    version: str = "0.9.34"
    versions: list[int] = [5, 6]
    supported: list[str]
    limited: list[str]
    unsupported: list[str]
