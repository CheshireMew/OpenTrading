from __future__ import annotations

from pydantic import BaseModel, Field


class LlmProviderPresetResponse(BaseModel):
    id: str
    label: str
    baseUrl: str
    defaultModel: str
    supportsReasoning: bool = False


class LlmProviderConfigResponse(BaseModel):
    provider: str
    apiKey: str = ""
    apiKeySet: bool = False
    apiKeyPreview: str = ""
    baseUrl: str
    modelId: str
    reasoningEnabled: bool = False
    presets: list[LlmProviderPresetResponse] = Field(default_factory=list)


class LlmProviderConfigUpdateRequest(BaseModel):
    provider: str
    apiKey: str | None = None
    baseUrl: str = ""
    modelId: str = ""
    reasoningEnabled: bool = False


class SystemIndicatorConfigResponse(BaseModel):
    ema_period: int
    rsi_period: int
    macd_fast: int
    macd_slow: int
    macd_signal: int


class SystemRuntimeConfigResponse(BaseModel):
    app_role: str
    database_engine: str
    database_source: str
    cache_backend: str


class SystemConfigResponse(BaseModel):
    version: str
    exchange: str
    symbols: list[str]
    timeframe: str
    indicators: SystemIndicatorConfigResponse
    runtime: SystemRuntimeConfigResponse


class DisplayCurrencyResponse(BaseModel):
    code: str
    name: str
    symbol: str
    locale: str
    fraction_digits: int


class CurrencyRatesResponse(BaseModel):
    base: str
    rates: dict[str, float]
    supported: list[DisplayCurrencyResponse]
    aliases: dict[str, str] = Field(default_factory=dict)
    updated_at: str
    source: str
    is_fallback: bool = False
