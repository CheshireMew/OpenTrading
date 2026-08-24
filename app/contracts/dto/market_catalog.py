from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.dto.market_history import OhlcvPointResponse


class ApiStatusResponse(BaseModel):
    status: str
    version: str
    framework: str
    dependencies: str
    timestamp: str


class MarketIndexResponse(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    pricing_symbol: str | None = None
    pricing_name: str | None = None
    pricing_currency: str | None = None


class MarketSymbolSearchResponse(BaseModel):
    symbol: str
    name: str
    asset_class: str
    market: str
    currency: str
    exchange: str | None = None
    aliases: list[str] = Field(default_factory=list)
    pricing_symbol: str | None = None
    pricing_name: str | None = None
    pricing_currency: str | None = None


class MarketIndexHistoryResponse(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    native_currency: str | None = None
    timeframe: str
    source: str
    price_basis: str = "index"
    pricing_symbol: str | None = None
    pricing_name: str | None = None
    pricing_currency: str | None = None
    is_close_only: bool = False
    count: int
    data: list[OhlcvPointResponse] = Field(default_factory=list)
