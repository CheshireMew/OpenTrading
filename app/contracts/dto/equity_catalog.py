from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EquityOfferingResponse(BaseModel):
    source_id: str
    platform: Literal["binance", "okx", "bitget"]
    trading_type: Literal["spot", "perpetual"]
    product: str
    symbol: str
    quote: str
    status: str
    url: str


class EquityCatalogItemResponse(BaseModel):
    ticker: str
    name: str
    name_zh: str
    logo_url: str | None
    asset_type: Literal["stock", "etf", "index", "unknown"]
    market: str
    platforms: list[str]
    trading_types: list[str]
    offerings: list[EquityOfferingResponse]


class EquityCatalogSourceResponse(BaseModel):
    id: str
    platform: Literal["binance", "okx", "bitget"]
    label: str
    trading_type: Literal["spot", "perpetual", "metadata"]
    status: Literal["ok", "stale", "unavailable"]
    count: int
    updated_at: str | None
    error: str | None
    url: str


class EquityCatalogResponse(BaseModel):
    updated_at: str
    complete: bool
    items: list[EquityCatalogItemResponse]
    sources: list[EquityCatalogSourceResponse]
