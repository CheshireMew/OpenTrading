// This file is generated from backend FastAPI route contracts.
// Do not edit manually.

export interface ChartSymbol {
  id: string
  symbol: string
  name: string
  exchange: string
  market: "spot" | "usdm" | "index"
  currency: string
  timeframes: Array<string>
  close_only?: boolean
  timezone?: string
  session?: string
  metadata?: { [key: string]: unknown }
}

export interface ChartBars {
  symbol: ChartSymbol
  timeframe: string
  bars: Array<ChartBar>
  source: string
}

export interface ChartQuote {
  id: string
  price?: number | null
  change?: number | null
  change_pct?: number | null
  basis?: string
  updated_at: number
  error?: string | null
}

export interface PineCapabilities {
  engine?: string
  version?: string
  versions?: Array<number>
  supported: Array<string>
  limited: Array<string>
  unsupported: Array<string>
}

export interface PineRun {
  id: string
  status: "queued" | "loading" | "running" | "completed" | "failed" | "cancelled" | "interrupted"
  progress?: number
  created_at: number
  request: PineRunRequest
  error?: string | null
  summary?: { [key: string]: unknown }
  provenance?: { [key: string]: unknown }
}

export interface PineRunRequest {
  script_id: string
  script_version: number
  symbol: string
  timeframe: string
  start: number
  end: number
  inputs?: { [key: string]: unknown }
  props?: { [key: string]: unknown }
}

export interface PineRecords {
  items: Array<{ [key: string]: unknown }>
  total: number
  offset: number
}

export interface WorkspaceDocument {
  id: string
  name: string
  version: number
  data: { [key: string]: unknown }
  updated_at: number
  readonly?: boolean
}

export interface WorkspaceWrite {
  name: string
  data: { [key: string]: unknown }
  expected_version?: number
}

export interface ChartBar {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume?: number
  closeTime: number
  closed: boolean
}

export interface ChartBarsQueryParams {
  symbol: string
  timeframe: string
  limit?: number
  start?: number | null
  end?: number | null
}

export interface ChartDocumentQueryParams {
  version?: number | null
}

export interface ChartPineRecordsQueryParams {
  kind?: "equity" | "trades" | "open_trades" | "orders" | "fills" | "warnings" | "bars"
  offset?: number
  limit?: number
}

export interface ChartQuotesQueryParams {
  symbols: string
}
