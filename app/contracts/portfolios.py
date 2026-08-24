from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortfolioBalanceAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    symbol: str = Field(default="", max_length=40)
    targetWeight: float = Field(default=0, ge=0, le=100)
    units: float = Field(default=0, ge=0)
    currentPrice: float = Field(default=0, ge=0)
    seedValue: float = Field(default=0, ge=0)


class PortfolioBalanceStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rebalanceBand: float = Field(default=5, ge=0, le=100)
    minTradeAmount: float = Field(default=10, ge=0)
    reviewFrequency: Literal["daily", "weekly", "monthly", "quarterly"] = "monthly"


class PortfolioBalanceTracking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    virtualCapital: float = Field(default=100_000, ge=0)
    inceptionDate: str = Field(max_length=32)


class PortfolioBalanceSimulation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initialCapital: float = Field(default=100_000, ge=0)
    simulationStartDate: str = Field(max_length=32)


class PortfolioSimulationEquityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=0)
    timestamp: str = Field(max_length=64)
    equity: float = Field(ge=0)
    pnl_abs: float
    drawdown_pct: float = Field(ge=0)


class PortfolioSimulationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    startDate: str = Field(max_length=32)
    endDate: str = Field(max_length=32)
    initialValue: float = Field(ge=0)
    finalValue: float = Field(ge=0)
    totalReturnPct: float
    annualizedReturnPct: float | None = None
    maxDrawdownPct: float = Field(ge=0)
    reviewCount: int = Field(ge=0)
    outOfBandReviewCount: int = Field(ge=0)
    rebalanceCount: int = Field(ge=0)
    equityCurve: list[PortfolioSimulationEquityPoint] = Field(default_factory=list, max_length=10_000)


class PortfolioBalancePortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    assets: list[PortfolioBalanceAsset] = Field(min_length=1, max_length=100)
    strategy: PortfolioBalanceStrategy
    tracking: PortfolioBalanceTracking
    simulation: PortfolioBalanceSimulation
    holdingsInitializedAt: str | None = Field(default=None, max_length=64)
    lastPriceUpdatedAt: str | None = Field(default=None, max_length=64)
    seedCapital: float | None = Field(default=None, ge=0)
    holdingsSource: Literal["virtual"] | None = None
    createdAt: str = Field(max_length=64)
    updatedAt: str = Field(max_length=64)

    @model_validator(mode="after")
    def validate_asset_ids(self):
        asset_ids = [asset.id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("同一组合中的资产 ID 不能重复")
        return self


class PortfolioBalanceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activePortfolioId: str = Field(default="", max_length=120)
    portfolios: list[PortfolioBalancePortfolio] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_collection_ids(self):
        portfolio_ids = [portfolio.id for portfolio in self.portfolios]
        if len(portfolio_ids) != len(set(portfolio_ids)):
            raise ValueError("组合 ID 不能重复")
        if self.portfolios and self.activePortfolioId not in set(portfolio_ids):
            raise ValueError("当前组合必须属于活动组合集合")
        if not self.portfolios and self.activePortfolioId:
            raise ValueError("空组合集合不能指定当前组合")
        return self


class PortfolioCollectionSaveCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedRevision: int = Field(ge=0)
    snapshot: PortfolioBalanceSnapshot

    @model_validator(mode="after")
    def require_portfolio(self):
        if not self.snapshot.portfolios:
            raise ValueError("至少保留一个活动组合")
        return self


class PortfolioCollectionChangeCommand(BaseModel):
    """A revision-checked change set; portfolioOrder is the authoritative live set."""

    model_config = ConfigDict(extra="forbid")

    expectedRevision: int = Field(ge=0)
    activePortfolioId: str = Field(min_length=1, max_length=120)
    changedPortfolios: list[PortfolioBalancePortfolio] = Field(default_factory=list, max_length=100)
    portfolioOrder: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_change_set(self):
        if len(self.portfolioOrder) != len(set(self.portfolioOrder)):
            raise ValueError("组合顺序中不能出现重复 ID")
        ordered_ids = set(self.portfolioOrder)
        if self.activePortfolioId not in ordered_ids:
            raise ValueError("当前组合必须属于活动组合集合")
        changed_ids = [portfolio.id for portfolio in self.changedPortfolios]
        if len(changed_ids) != len(set(changed_ids)):
            raise ValueError("变更集合中的组合 ID 不能重复")
        if not set(changed_ids).issubset(ordered_ids):
            raise ValueError("变更集合只能包含活动组合")
        return self


class PortfolioRestoreCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedRevision: int = Field(ge=0)


class PortfolioCollectionResponse(BaseModel):
    revision: int = Field(ge=0)
    snapshot: PortfolioBalanceSnapshot


class PortfolioDeletedSummary(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    deletedAt: datetime


class PortfolioDeletedPage(BaseModel):
    items: list[PortfolioDeletedSummary] = Field(default_factory=list, max_length=50)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=50)
    total: int = Field(ge=0)


class PortfolioSimulationResultCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedRevision: int = Field(ge=0)
    result: PortfolioSimulationSummary


class PortfolioSimulationResultResponse(BaseModel):
    portfolioId: str = Field(min_length=1, max_length=120)
    result: PortfolioSimulationSummary | None = None
    updatedAt: datetime | None = None


class PortfolioSimulationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolioId: str = Field(min_length=1, max_length=120)
    result: PortfolioSimulationSummary


class PortfolioExportDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[2] = 2
    exportedAt: datetime
    snapshot: PortfolioBalanceSnapshot
    deletedPortfolios: list[PortfolioBalancePortfolio] = Field(default_factory=list, max_length=100)
    simulationResults: list[PortfolioSimulationArtifact] = Field(default_factory=list, max_length=100)


class LegacyPortfolioBalancePortfolio(PortfolioBalancePortfolio):
    lastSimulationResult: PortfolioSimulationSummary | None = None


class LegacyPortfolioBalanceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activePortfolioId: str = Field(default="", max_length=120)
    portfolios: list[LegacyPortfolioBalancePortfolio] = Field(default_factory=list, max_length=100)


class LegacyPortfolioExportDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal[1] = 1
    exportedAt: datetime
    snapshot: LegacyPortfolioBalanceSnapshot
    deletedPortfolios: list[LegacyPortfolioBalancePortfolio] = Field(default_factory=list, max_length=100)


class PortfolioCollectionImportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedRevision: int = Field(ge=0)
    mode: Literal["merge", "replace"] = "merge"
    document: Annotated[
        PortfolioExportDocument | LegacyPortfolioExportDocument,
        Field(discriminator="schemaVersion"),
    ]
