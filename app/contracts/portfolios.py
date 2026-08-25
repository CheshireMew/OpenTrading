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
    holdingsSource: Literal["virtual", "ledger"] | None = None
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


PortfolioTransactionType = Literal[
    "buy",
    "sell",
    "deposit",
    "withdrawal",
    "fee",
    "transfer_in",
    "transfer_out",
]


class PortfolioTransactionCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transactionType: PortfolioTransactionType
    symbol: str = Field(default="", max_length=160)
    quantity: float = Field(default=0, ge=0)
    unitPrice: float = Field(default=0, ge=0)
    cashAmount: float = Field(default=0, ge=0)
    fee: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=1, max_length=16)
    feeCurrency: str = Field(default="USD", min_length=1, max_length=16)
    externalId: str | None = Field(default=None, max_length=200)
    note: str = Field(default="", max_length=10_000)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    occurredAt: datetime

    @model_validator(mode="after")
    def validate_transaction_shape(self):
        if self.transactionType in {"buy", "sell", "transfer_in", "transfer_out"}:
            if not self.symbol.strip():
                raise ValueError("资产流水必须填写标的")
            if self.quantity <= 0:
                raise ValueError("资产流水数量必须大于 0")
        if self.transactionType in {"buy", "sell"} and self.unitPrice <= 0:
            raise ValueError("买卖流水单价必须大于 0")
        if self.transactionType in {"deposit", "withdrawal", "fee"} and self.cashAmount <= 0:
            raise ValueError("现金流水金额必须大于 0")
        return self


class PortfolioTransactionUpdateCommand(PortfolioTransactionCreateCommand):
    expectedVersion: int = Field(ge=1)


class PortfolioTransactionArchiveCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedVersion: int = Field(ge=1)


class PortfolioTransactionResponse(BaseModel):
    id: str
    portfolioId: str
    transactionType: PortfolioTransactionType
    symbol: str
    quantity: float
    unitPrice: float
    cashAmount: float
    fee: float
    currency: str
    feeCurrency: str
    externalId: str | None = None
    note: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    version: int
    occurredAt: datetime
    archivedAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class PortfolioLedgerPositionResponse(BaseModel):
    symbol: str
    units: float
    averageCost: float
    costBasis: float
    marketPrice: float | None = None
    marketValue: float
    realizedPnl: float
    unrealizedPnl: float
    fees: float


class PortfolioLedgerSummaryResponse(BaseModel):
    cashBalance: float
    contributions: float
    withdrawals: float
    netContributions: float
    totalFees: float
    costBasis: float
    marketValue: float
    totalEquity: float
    realizedPnl: float
    unrealizedPnl: float
    totalPnl: float
    simpleReturnPct: float | None = None
    moneyWeightedReturnPct: float | None = None
    timeWeightedReturnPct: float | None = None
    positions: list[PortfolioLedgerPositionResponse] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    reliability: Literal["complete", "incomplete"]


class PortfolioLedgerResponse(BaseModel):
    portfolioId: str
    transactions: list[PortfolioTransactionResponse] = Field(default_factory=list)
    archivedTransactions: list[PortfolioTransactionResponse] = Field(default_factory=list)
    summary: PortfolioLedgerSummaryResponse


class PortfolioTransactionImportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["append", "replace"] = "append"
    transactions: list[PortfolioTransactionCreateCommand] = Field(min_length=1, max_length=5_000)


class PortfolioTransactionImportResponse(BaseModel):
    importedCount: int = Field(ge=0)
    archivedCount: int = Field(ge=0)
    ledger: PortfolioLedgerResponse


class PortfolioAnalyticsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    periodDays: int = Field(default=365, ge=30, le=3_650)
    benchmarkSymbol: str = Field(default="BTC/USDT", min_length=1, max_length=160)
    customShocks: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shocks(self):
        normalized: dict[str, float] = {}
        for symbol, value in self.customShocks.items():
            key = symbol.strip().upper()
            if not key:
                continue
            if not -100 <= value <= 1_000:
                raise ValueError("情景冲击必须在 -100% 到 1000% 之间")
            normalized[key] = value
        self.customShocks = normalized
        return self


class PortfolioPerformancePointResponse(BaseModel):
    date: str
    equity: float
    externalCashFlow: float
    dailyReturnPct: float | None = None
    drawdownPct: float


class PortfolioAssetRiskResponse(BaseModel):
    symbol: str
    weightPct: float
    annualizedVolatilityPct: float | None = None
    riskContributionPct: float | None = None
    periodReturnPct: float | None = None
    returnContributionPct: float | None = None


class PortfolioCorrelationRowResponse(BaseModel):
    symbol: str
    values: list[float | None] = Field(default_factory=list)


class PortfolioScenarioResponse(BaseModel):
    id: str
    name: str
    shocks: dict[str, float] = Field(default_factory=dict)
    projectedPnl: float
    projectedReturnPct: float | None = None
    projectedEquity: float


class PortfolioAnalyticsResponse(BaseModel):
    portfolioId: str
    startDate: str
    endDate: str
    periodDays: int
    totalEquity: float
    timeWeightedReturnPct: float | None = None
    moneyWeightedReturnPct: float | None = None
    benchmarkSymbol: str
    benchmarkReturnPct: float | None = None
    excessReturnPct: float | None = None
    annualizedVolatilityPct: float | None = None
    valueAtRisk95: float | None = None
    maxDrawdownPct: float | None = None
    concentrationHhi: float
    effectivePositionCount: float | None = None
    topPositionWeightPct: float
    symbols: list[str] = Field(default_factory=list)
    correlation: list[PortfolioCorrelationRowResponse] = Field(default_factory=list)
    assets: list[PortfolioAssetRiskResponse] = Field(default_factory=list)
    performance: list[PortfolioPerformancePointResponse] = Field(default_factory=list)
    scenarios: list[PortfolioScenarioResponse] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
