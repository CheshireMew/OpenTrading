from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ResearchResultEntry(BaseModel):
    id: str
    run_id: str | None = None
    source_type: Literal['native', 'legacy']
    label: str
    family: str | None = None
    archived: bool
    config: dict[str, Any]
    report: dict[str, Any]
    metadata: dict[str, Any]
    missing: list[str]
    cohort: str | None = None
    execution_summary: dict[str, Any]
    sources: list[dict[str, Any]]
    context_note: str | None = None


class ResearchResultQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: str | None = None
    strategy: str | None = None
    family: str | None = None
    timeframe: str | None = None
    start: str | None = None
    end: str | None = None
    execution_timeframe: str | None = None
    intrabar_profit_protection: bool | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    reference_id: str | None = None
    sort: Literal['return_pct', 'win_rate', 'max_drawdown_pct', 'total_trades'] = 'return_pct'
    descending: bool = True
    minimum_trades: int = Field(0, ge=0)
    include_archived: bool = False
    offset: int = Field(0, ge=0)
    limit: int = Field(30, ge=1, le=200)


class ResearchResultPage(BaseModel):
    items: list[ResearchResultEntry]
    total: int
    offset: int
    mode: Literal['historical', 'same_conditions']
    reference_id: str | None = None
    note: str


class ResearchResultImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    roots: list[str] = Field(default_factory=list)


class ResearchResultRefresh(BaseModel):
    native_runs: int
    scanned_files: int
    imported_references: int
    unchanged_files: int
    issues: list[dict[str, Any]]
    index: str
    note: str
