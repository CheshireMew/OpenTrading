from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.json_types import JsonObject
from app.contracts.timestamps import UtcResponseModel
from app.contracts.dto.market_history import IndicatorSummaryResponse, OhlcvPointResponse


ResearchAssetClass = Literal["crypto", "index", "cash", "web3"]
ResearchNoteKind = Literal["thesis", "update", "review", "decision"]
ResearchAlertOperator = Literal["gt", "gte", "lt", "lte", "crosses", "crosses_above", "crosses_below", "between", "outside"]
ResearchNotificationChannel = Literal["in_app", "windows", "sound"]


class ResearchWatchlistCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4_000)


class ResearchWatchlistUpdateCommand(ResearchWatchlistCreateCommand):
    expectedVersion: int = Field(ge=1)


class ResearchArchiveCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedVersion: int = Field(ge=1)


class ResearchWatchlistResponse(UtcResponseModel):
    id: str
    name: str
    description: str
    position: int
    version: int
    archivedAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class ResearchWatchItemCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchlistId: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=160)
    assetClass: ResearchAssetClass = "crypto"
    displayName: str = Field(default="", max_length=200)
    thesis: str = Field(default="", max_length=20_000)
    targetPrice: float | None = Field(default=None, gt=0)
    invalidationPrice: float | None = Field(default=None, gt=0)
    tags: list[str] = Field(default_factory=list, max_length=30)
    sourceContext: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_tags(self):
        normalized: list[str] = []
        seen: set[str] = set()
        for value in self.tags:
            tag = value.strip()
            if not tag or tag.casefold() in seen:
                continue
            if len(tag) > 40:
                raise ValueError("标签不能超过 40 个字符")
            seen.add(tag.casefold())
            normalized.append(tag)
        self.tags = normalized
        return self


class ResearchWatchItemUpdateCommand(ResearchWatchItemCreateCommand):
    expectedVersion: int = Field(ge=1)


class ResearchWatchItemResponse(UtcResponseModel):
    id: str
    watchlistId: str
    symbol: str
    assetClass: ResearchAssetClass
    displayName: str
    thesis: str
    targetPrice: float | None = None
    invalidationPrice: float | None = None
    tags: list[str] = Field(default_factory=list)
    sourceContext: JsonObject = Field(default_factory=dict)
    position: int
    version: int
    archivedAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class ResearchNoteCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchItemId: str | None = Field(default=None, max_length=120)
    symbol: str = Field(min_length=1, max_length=160)
    kind: ResearchNoteKind = "update"
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(default="", max_length=100_000)
    snapshot: JsonObject = Field(default_factory=dict)
    occurredAt: datetime | None = None


class ResearchNoteUpdateCommand(ResearchNoteCreateCommand):
    expectedVersion: int = Field(ge=1)


class ResearchNoteResponse(UtcResponseModel):
    id: str
    watchItemId: str | None = None
    symbol: str
    kind: ResearchNoteKind
    title: str
    content: str
    snapshot: JsonObject = Field(default_factory=dict)
    version: int
    occurredAt: datetime
    archivedAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class ResearchAlertCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchItemId: str | None = Field(default=None, max_length=120)
    symbol: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=200)
    metric: str = Field(min_length=1, max_length=80)
    operator: ResearchAlertOperator
    threshold: float
    secondaryThreshold: float | None = None
    enabled: bool = True
    cooldownMinutes: int = Field(default=60, ge=0, le=43_200)
    notificationChannels: list[ResearchNotificationChannel] = Field(default_factory=lambda: ["in_app"])
    configuration: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_thresholds(self):
        if self.metric == 'portfolio_drift_pct':
            raise ValueError('组合平衡已退出，不能创建或更新组合偏离提醒')
        if not math.isfinite(self.threshold) or (self.secondaryThreshold is not None and not math.isfinite(self.secondaryThreshold)):
            raise ValueError("提醒价格必须是有效数字")
        if self.configuration.get("chartSymbolId"):
            if not isinstance(self.configuration["chartSymbolId"], str):
                raise ValueError("图表警报必须指定有效品种")
            if self.metric != "price" or self.threshold <= 0:
                raise ValueError("图表警报必须使用有效的正数价格")
            initial = self.configuration.get("initialPrice")
            if initial is not None and (not isinstance(initial, (int, float)) or not math.isfinite(initial) or initial <= 0):
                raise ValueError("初始价格必须是有效的正数")
        if self.operator in {"between", "outside"}:
            if self.secondaryThreshold is None:
                raise ValueError("区间提醒必须提供第二个阈值")
            if self.threshold >= self.secondaryThreshold:
                raise ValueError("区间提醒的第二个阈值必须大于第一个阈值")
        return self


class ResearchAlertUpdateCommand(ResearchAlertCreateCommand):
    expectedVersion: int = Field(ge=1)


class ResearchAlertResponse(UtcResponseModel):
    id: str
    watchItemId: str | None = None
    symbol: str
    name: str
    metric: str
    operator: ResearchAlertOperator
    threshold: float
    secondaryThreshold: float | None = None
    enabled: bool
    cooldownMinutes: int
    notificationChannels: list[ResearchNotificationChannel] = Field(default_factory=list)
    configuration: JsonObject = Field(default_factory=dict)
    lastValue: float | None = None
    lastEvaluatedAt: datetime | None = None
    lastTriggeredAt: datetime | None = None
    version: int
    archivedAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class ResearchEventResponse(UtcResponseModel):
    id: str
    entityType: str
    entityId: str | None = None
    symbol: str | None = None
    kind: str
    title: str
    body: str
    payload: JsonObject = Field(default_factory=dict)
    occurredAt: datetime
    acknowledgedAt: datetime | None = None
    createdAt: datetime


class ResearchEventAcknowledgeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged: bool = True


class ResearchEventPageResponse(UtcResponseModel):
    items: list[ResearchEventResponse] = Field(default_factory=list)
    total: int = Field(ge=0)


class ResearchWorkbenchResponse(UtcResponseModel):
    watchlists: list[ResearchWatchlistResponse] = Field(default_factory=list)
    items: list[ResearchWatchItemResponse] = Field(default_factory=list)
    notes: list[ResearchNoteResponse] = Field(default_factory=list)
    alerts: list[ResearchAlertResponse] = Field(default_factory=list)
    events: list[ResearchEventResponse] = Field(default_factory=list)
    unacknowledgedEventCount: int = Field(ge=0)


class ResearchAlertEvaluationResponse(UtcResponseModel):
    evaluatedAt: datetime
    ruleCount: int = Field(ge=0)
    evaluatedCount: int = Field(ge=0)
    triggeredCount: int = Field(ge=0)
    unavailableCount: int = Field(ge=0)


class ResearchAlertEvaluateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = True


class TradeSignalResponse(UtcResponseModel):
    id: str
    symbol: str
    timeframe: str
    source: str
    mode: str
    signalStatus: str
    side: str | None = None
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    riskReward: float | None = None
    confidence: int | None = None
    riskAmount: float | None = None
    style: str | None = None
    strategy: str | None = None
    reason: str
    errorCode: str | None = None
    currentPrice: float | None = None
    entryTime: int | None = None
    marketSnapshot: JsonObject = Field(default_factory=dict)
    outcomeStatus: Literal["pending", "target_hit", "stop_hit", "ambiguous", "expired", "unavailable"]
    outcomePrice: float | None = None
    targetHitAt: datetime | None = None
    stopHitAt: datetime | None = None
    mfePct: float | None = None
    maePct: float | None = None
    forwardReturns: dict[str, float | None] = Field(default_factory=dict)
    evaluatedAt: datetime | None = None
    expiresAt: datetime | None = None
    version: int = Field(ge=1)
    archivedAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class TradeSignalPageResponse(UtcResponseModel):
    items: list[TradeSignalResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)


class TradeSignalStatGroupResponse(UtcResponseModel):
    key: str
    total: int = Field(ge=0)
    resolved: int = Field(ge=0)
    targetHits: int = Field(ge=0)
    stopHits: int = Field(ge=0)
    ambiguous: int = Field(ge=0)
    expired: int = Field(ge=0)
    winRatePct: float | None = None
    averageConfidence: float | None = None
    averageMfePct: float | None = None
    averageMaePct: float | None = None


class TradeSignalConfidenceBucketResponse(UtcResponseModel):
    key: str
    minConfidence: int = Field(ge=0, le=100)
    maxConfidence: int = Field(ge=0, le=100)
    total: int = Field(ge=0)
    resolved: int = Field(ge=0)
    targetHits: int = Field(ge=0)
    stopHits: int = Field(ge=0)
    winRatePct: float | None = None
    expectedWinRatePct: float | None = None
    calibrationGapPct: float | None = None


class TradeSignalStatsResponse(UtcResponseModel):
    overall: TradeSignalStatGroupResponse
    bySource: list[TradeSignalStatGroupResponse] = Field(default_factory=list)
    byStrategy: list[TradeSignalStatGroupResponse] = Field(default_factory=list)
    confidenceCalibration: list[TradeSignalConfidenceBucketResponse] = Field(default_factory=list)


class TradeSignalEvaluationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signalId: str | None = Field(default=None, max_length=120)
    force: bool = True


class TradeSignalEvaluationRunResponse(UtcResponseModel):
    evaluatedAt: datetime
    candidateCount: int = Field(ge=0)
    evaluatedCount: int = Field(ge=0)
    resolvedCount: int = Field(ge=0)
    unavailableCount: int = Field(ge=0)


class AssetResearchResponse(UtcResponseModel):
    symbol: str
    assetClass: ResearchAssetClass
    timeframe: str
    currentPrice: float | None = None
    updatedAt: datetime
    indicators: IndicatorSummaryResponse | None = None
    history: list[OhlcvPointResponse] = Field(default_factory=list)
    marketContext: dict[str, Any] = Field(default_factory=dict)
    watchItems: list[ResearchWatchItemResponse] = Field(default_factory=list)
    notes: list[ResearchNoteResponse] = Field(default_factory=list)
    alerts: list[ResearchAlertResponse] = Field(default_factory=list)
    events: list[ResearchEventResponse] = Field(default_factory=list)
    signals: list[TradeSignalResponse] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class MarketScreenerFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market: Literal["spot", "usdm", "all"] = "all"
    quoteAsset: str = Field(default="USDT", min_length=2, max_length=12)
    minPriceChangePct: float | None = Field(default=None, ge=-100, le=10_000)
    maxPriceChangePct: float | None = Field(default=None, ge=-100, le=10_000)
    minQuoteVolume: float | None = Field(default=None, ge=0)
    maxFundingRatePct: float | None = Field(default=None, ge=-100, le=100)
    minBreakoutScore: int | None = Field(default=None, ge=0, le=100)
    minOiChange1hPct: float | None = Field(default=None, ge=-1_000, le=10_000)
    minRsi: float | None = Field(default=None, ge=0, le=100)
    maxRsi: float | None = Field(default=None, ge=0, le=100)
    includeWeb3: bool = False
    web3ChainId: str | None = Field(default=None, max_length=32)
    maxWeb3RiskLevel: int | None = Field(default=None, ge=0, le=5)
    symbols: list[str] = Field(default_factory=list, max_length=200)
    limit: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def normalize(self):
        self.quoteAsset = self.quoteAsset.strip().upper()
        self.symbols = list(
            dict.fromkeys(value.strip().upper().replace("/", "") for value in self.symbols if value.strip())
        )
        if (
            self.minPriceChangePct is not None
            and self.maxPriceChangePct is not None
            and self.minPriceChangePct > self.maxPriceChangePct
        ):
            raise ValueError("最小涨跌幅不能大于最大涨跌幅")
        if self.minRsi is not None and self.maxRsi is not None and self.minRsi > self.maxRsi:
            raise ValueError("最小 RSI 不能大于最大 RSI")
        self.web3ChainId = self.web3ChainId.strip() if self.web3ChainId else None
        return self


class SavedMarketScreenerCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4_000)
    filters: MarketScreenerFilters


class SavedMarketScreenerUpdateCommand(SavedMarketScreenerCreateCommand):
    expectedVersion: int = Field(ge=1)


class SavedMarketScreenerResponse(UtcResponseModel):
    id: str
    name: str
    description: str
    filters: MarketScreenerFilters
    version: int
    archivedAt: datetime | None = None
    createdAt: datetime
    updatedAt: datetime


class SavedMarketScreenerListResponse(UtcResponseModel):
    items: list[SavedMarketScreenerResponse] = Field(default_factory=list)


class MarketScreenerRunCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asOf: datetime | None = None


class MarketScreenerRunResponse(UtcResponseModel):
    id: str
    screenerId: str
    filters: MarketScreenerFilters
    resultItems: list[JsonObject] = Field(default_factory=list)
    resultCount: int = Field(ge=0)
    snapshotAsOf: datetime
    evaluatedAt: datetime
    historicalReplay: bool = False


class MarketScreenerRunPageResponse(UtcResponseModel):
    items: list[MarketScreenerRunResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
