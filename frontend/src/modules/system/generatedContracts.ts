// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

export interface DataHealthResponse {
  status: "healthy" | "degraded" | "empty"
  checkedAt: string
  databaseRevision?: string | null
  sources?: Array<DataSourceHealthResponse>
  summary?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface DataRepairResponse {
  action: string
  status: "completed" | "failed"
  startedAt: string
  completedAt: string
  detail: string
  result?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
}

export interface DataRepairCommand {
  action: "verify_database" | "refresh_binance_snapshot" | "hydrate_symbol_history" | "evaluate_research_alerts" | "evaluate_trade_signals"
  symbol?: string | null
  timeframe?: string
  days?: number
}

export interface SystemConfigResponse {
  version: string
  exchange: string
  symbols: Array<string>
  timeframe: string
  indicators: SystemIndicatorConfigResponse
  runtime: SystemRuntimeConfigResponse
}

export interface CurrencyRatesResponse {
  base: string
  rates: { [key: string]: number }
  supported: Array<DisplayCurrencyResponse>
  aliases?: { [key: string]: string }
  updated_at: string
  source: string
  is_fallback?: boolean
}

export interface LlmProviderConfigResponse {
  provider: string
  apiKey?: string
  apiKeySet?: boolean
  apiKeyPreview?: string
  baseUrl: string
  modelId: string
  reasoningEnabled?: boolean
  presets?: Array<LlmProviderPresetResponse>
}

export interface LlmProviderConfigUpdateRequest {
  provider: string
  apiKey?: string | null
  baseUrl?: string
  modelId?: string
  reasoningEnabled?: boolean
}

export interface FredApiConfigResponse {
  apiKey?: string
  apiKeySet?: boolean
  apiKeyPreview?: string
  source?: string
}

export interface FredApiConfigUpdateRequest {
  apiKey?: string | null
}

export interface DataSourceHealthResponse {
  id: string
  name: string
  status: "ready" | "stale" | "empty" | "failed" | "stopped" | "starting"
  recordCount: number
  coverageStart?: string | null
  coverageEnd?: string | null
  ageSeconds?: number | null
  gapCount?: number | null
  lastSuccessAt?: string | null
  lastFailureAt?: string | null
  nextRunAt?: string | null
  detail?: string
  metadata?: { [key: string]: string | number | boolean | Array<string | number | boolean | null> | { [key: string]: string | number | boolean | null } | Array<{ [key: string]: string | number | boolean | null }> | { [key: string]: Array<string | number | boolean | null> } | null }
  repairActions?: Array<string>
}

export interface DisplayCurrencyResponse {
  code: string
  name: string
  symbol: string
  locale: string
  fraction_digits: number
}

export interface LlmProviderPresetResponse {
  id: string
  label: string
  baseUrl: string
  defaultModel: string
  supportsReasoning?: boolean
}

export interface SystemIndicatorConfigResponse {
  ema_period: number
  rsi_period: number
  macd_fast: number
  macd_slow: number
  macd_signal: number
}

export interface SystemRuntimeConfigResponse {
  app_role: string
  database_engine: string
  database_source: string
  cache_backend: string
}
