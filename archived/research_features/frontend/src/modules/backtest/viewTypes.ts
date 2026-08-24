import { reactive } from 'vue'
import type {
  CandlestickData,
  ChartMarkerData,
  VolumeData,
} from './contracts'
import type {
  BacktestDetailResponse,
  BacktestOptimizationTrialResponse,
  BacktestPairBreakdownResponse,
  BacktestRollingWindowResponse,
  BacktestRunResponse,
  BacktestPreviewResponse,
  StrategyPreviewMarkerResponse,
  StrategyEvolutionResponse,
  StrategyDefinitionResponse,
  StrategyVersionResponse,
} from './contracts'

export const defineReactiveView = <T extends object>(value: object): T => {
  // Vue templates receive unwrapped refs, while TypeScript checks this boundary
  // before Vue unwraps it. Keep that mismatch handled in one place.
  return reactive(value) as T
}

export interface BacktestRunSelectionConfig {
  strategy_key: string
  strategy_version: number
}

export interface BacktestPageConfig extends BacktestRunSelectionConfig {
  strategy_key: string
  strategy_version: number
  timeframe: string
  start_date: string
  end_date: string
  initial_cash: number
  fee_rate: number
  portfolio: {
    max_open_trades: number
    position_size_pct: number
    stake_mode: 'fixed' | 'unlimited'
  }
  research: {
    slippage_bps: number
    funding_rate_daily: number
    in_sample_ratio: number
    optimize_metric: 'sharpe' | 'profit_pct' | 'calmar' | 'profit_factor'
    optimize_trials: number
    rolling_windows: number
  }
}

type BacktestListRun = BacktestRunResponse
type BacktestLoadedRun = BacktestDetailResponse
export type BacktestDisplayRun = BacktestListRun | BacktestLoadedRun

export interface BacktestChartData {
  candles: CandlestickData[]
  volume: VolumeData[]
  markers: ChartMarkerData[]
}

export interface BacktestComparisonSeries {
  name: string
  color: string
  data: number[]
}

export interface BacktestComparisonChart {
  performance: {
    categories: string[]
    series: BacktestComparisonSeries[]
  }
  quality: {
    categories: string[]
    series: BacktestComparisonSeries[]
  }
}

export interface BacktestVersionCompareOption {
  version: number
  name: string
  run: BacktestRunResponse
}

export interface BacktestControlPanelView {
  config: BacktestPageConfig
  today: string
  ready: boolean
  strategies: StrategyDefinitionResponse[]
  selectedStrategy: StrategyDefinitionResponse | null
  selectedStrategyVersions: StrategyVersionResponse[]
  selectedVersion: StrategyVersionResponse | null
  canCopyCurrentStrategy: boolean
  canStartPaperRun: boolean
  strategyCapabilityHint: string
  timeframes: string[]
  optimizeMetrics: string[]
  symbolsText: string
  backtestLoading: boolean
  previewLoading: boolean
  paperLoading: boolean
  isBusy: boolean
  strategyPreview: BacktestPreviewResponse | null
  previewSymbol: string
  previewSymbols: string[]
  previewChartData: BacktestChartData
  previewMarkers: StrategyPreviewMarkerResponse[]
  syncStrategyVersion: () => void
  openCopyEditor: () => void
  openBlankEditor: () => void
  previewBacktest: () => Promise<unknown>
  startBacktest: () => Promise<void>
  startPaperRun: () => Promise<void>
}

export interface BacktestHistoryPanelView {
  historyMode: 'backtest' | 'paper'
  enableHistoryCompare: boolean
  visibleHistory: BacktestRunResponse[]
  compareRunIds: number[]
  openRunDetail: (run: BacktestRunResponse, mode?: 'backtest' | 'paper') => void
  toggleCompareRun: (runId: number) => void
  portfolioLabel: (run: BacktestDisplayRun) => string
  runStatusLabel: (run: BacktestDisplayRun) => string
  profitColorClass: (value: unknown) => string
  stopPaperRun: (runId: number) => Promise<void>
  deleteRun: (runId: number, mode: 'backtest' | 'paper') => Promise<void>
}

export interface BacktestResultPanelView {
  selectedRun: BacktestDetailResponse | null
  isPaperRun: boolean
  isDark: boolean
  chartColors: {
    bg: string
    grid: string
    text: string
    upColor: string
    downColor: string
  }
  chartData: BacktestChartData
  pairBreakdown: BacktestPairBreakdownResponse[]
  optimizationTrials: BacktestOptimizationTrialResponse[]
  rollingWindows: BacktestRollingWindowResponse[]
  evolutionLoading: boolean
  evolutionResult: StrategyEvolutionResponse | null
  selectedCompareRuns: BacktestRunResponse[]
  recentRunCompare: BacktestComparisonChart
  versionCompareOptions: BacktestVersionCompareOption[]
  versionCompareSelections: number[]
  selectedVersionCompareRuns: BacktestRunResponse[]
  versionRunCompare: BacktestComparisonChart
  profitColorClass: (value: unknown) => string
  runStatusLabel: (run: BacktestDisplayRun) => string
  portfolioLabel: (run: BacktestDisplayRun) => string
  joinSymbols: (symbols: string[] | undefined) => string
  configLabel: (value: Record<string, unknown> | null | undefined) => string
  compareRunLabel: (run: BacktestDisplayRun) => string
  toggleVersionCompare: (version: number) => void
  evolveStrategy: () => Promise<void>
}

export interface BacktestDetailHeroView {
  selectedRun: BacktestDetailResponse | null
  isPaperRun: boolean
  goBackToCenter: () => void
  portfolioLabel: (run: BacktestDisplayRun) => string
  runStatusLabel: (run: BacktestDisplayRun) => string
}



