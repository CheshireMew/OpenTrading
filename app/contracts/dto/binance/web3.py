from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.json_types import JsonObject


class BinanceWeb3HeatRankMetricsResponse(BaseModel):
    price: float | None = None
    market_cap: float | None = None
    liquidity: float | None = None
    holders: int | None = None
    launch_time: int | None = None
    percent_change_1h: float | None = None
    percent_change_24h: float | None = None
    volume_1h: float | None = None
    volume_4h: float | None = None
    volume_24h: float | None = None
    count_1h: int | None = None
    count_24h: int | None = None
    unique_trader_1h: int | None = None
    unique_trader_24h: int | None = None
    kyc_holders: int | None = None
    social_hype: float | None = None
    social_hype_normalized: float | None = None
    smart_money_inflow: float | None = None
    smart_money_traders: int | None = None
    smart_money_inflow_normalized: float | None = None
    smart_money_risk_level: int | None = None
    meme_score: float | None = None
    meme_score_normalized: float | None = None


class BinanceWeb3AddressPnlItemResponse(BaseModel):
    address: str | None = None
    address_label: str | None = None
    address_logo: str | None = None
    tags: list[str] = Field(default_factory=list)
    realized_pnl: float | None = None
    realized_pnl_pct: float | None = None
    win_rate: float | None = None
    total_volume: float | None = None
    total_tx_cnt: int | None = None
    total_traded_tokens: int | None = None
    last_activity: int | None = None


class BinanceWeb3AddressPnlResponse(BaseModel):
    source: str
    leaderboard: str
    page: int
    size: int
    pages: int | None = None
    items: list[BinanceWeb3AddressPnlItemResponse] = Field(default_factory=list)


class BinanceWeb3HeatRankItemResponse(BaseModel):
    rank: int | None = None
    symbol: str | None = None
    chain_id: str | None = None
    contract_address: str | None = None
    icon_url: str | None = None
    platform: str | None = None
    heat_score: float = 0
    ranks: dict[str, int] = Field(default_factory=dict)
    components: dict[str, float] = Field(default_factory=dict)
    penalties: dict[str, float] = Field(default_factory=dict)
    metrics: BinanceWeb3HeatRankMetricsResponse = Field(default_factory=BinanceWeb3HeatRankMetricsResponse)
    audit_info: JsonObject = Field(default_factory=dict)
    sentiment: str | None = None
    summary: str | None = None


class BinanceWeb3HeatRankResponse(BaseModel):
    source: str
    leaderboard: str
    chain_id: str
    size: int
    items: list[BinanceWeb3HeatRankItemResponse] = Field(default_factory=list)
    formula: dict[str, list[str]] = Field(default_factory=dict)


class BinanceWeb3HeatRankBoardsResponse(BaseModel):
    source: str
    leaderboard: str
    chain_id: str
    size: int
    boards: dict[str, BinanceWeb3HeatRankResponse] = Field(default_factory=dict)
    formula: dict[str, list[str]] = Field(default_factory=dict)


class BinanceWeb3TokenDynamicResponse(BaseModel):
    source: str
    chain_id: str
    contract_address: str
    price: float | None = None
    native_token_price: float | None = None
    volume_24h: float | None = None
    volume_24h_buy: float | None = None
    volume_24h_sell: float | None = None
    volume_4h: float | None = None
    volume_1h: float | None = None
    volume_5m: float | None = None
    count_24h: int | None = None
    count_24h_buy: int | None = None
    count_24h_sell: int | None = None
    percent_change_5m: float | None = None
    percent_change_1h: float | None = None
    percent_change_4h: float | None = None
    percent_change_24h: float | None = None
    market_cap: float | None = None
    fdv: float | None = None
    total_supply: float | None = None
    circulating_supply: float | None = None
    price_high_24h: float | None = None
    price_low_24h: float | None = None
    holders: int | None = None
    liquidity: float | None = None
    launch_time: int | None = None
    top10_holders_percentage: float | None = None
    kyc_holder_count: int | None = None
    kol_holders: int | None = None
    kol_holding_percent: float | None = None
    pro_holders: int | None = None
    pro_holding_percent: float | None = None
    smart_money_holders: int | None = None
    smart_money_holding_percent: float | None = None


class BinanceWeb3TokenKlineItemResponse(BaseModel):
    open_time: int | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    trade_count: int | None = None


class BinanceWeb3TokenKlineResponse(BaseModel):
    source: str
    address: str
    platform: str
    interval: str
    items: list[BinanceWeb3TokenKlineItemResponse] = Field(default_factory=list)


class BinanceWeb3TokenAuditResponse(BaseModel):
    source: str
    binance_chain_id: str
    contract_address: str
    has_result: bool = False
    is_supported: bool = False
    risk_level_enum: str | None = None
    risk_level: int | None = None
    buy_tax: float | None = None
    sell_tax: float | None = None
    is_verified: bool | None = None
    risk_items: list[JsonObject] = Field(default_factory=list)


