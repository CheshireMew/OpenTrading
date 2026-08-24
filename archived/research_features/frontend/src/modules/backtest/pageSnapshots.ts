import { isRecord, readBoolean, readEnum, readNumber, readString } from '@/composables/pageSnapshot'
import type { BacktestRunDefaultsResponse } from './contracts'
import type { BacktestPageConfig, BacktestRunSelectionConfig } from './viewTypes'

export interface BacktestPageSnapshot {
  config: BacktestPageConfig
  symbolsText: string
  historyMode: 'backtest' | 'paper'
}

export interface BacktestEditorSnapshot {
  showVersionEditor: boolean
  showIndicatorCreator: boolean
  showTemplateCreator: boolean
  useGlobalIndicatorCatalog: boolean
  newIndicatorType: string
  versionDraft: Record<string, unknown>
  indicatorDraft: Record<string, unknown>
  templateDraft: Record<string, unknown>
}

export interface BacktestEditorPageSnapshot {
  config: BacktestRunSelectionConfig
  editor: BacktestEditorSnapshot | null
}

const normalizeRecord = (value: unknown): Record<string, unknown> => (isRecord(value) ? value : {})

export const readStakeMode = (value: unknown, fallback: 'fixed' | 'unlimited') => (
  readEnum(value, ['fixed', 'unlimited'] as const, fallback)
)

export const readOptimizeMetric = (
  value: unknown,
  fallback: 'sharpe' | 'profit_pct' | 'calmar' | 'profit_factor',
) => (
  readEnum(value, ['sharpe', 'profit_pct', 'calmar', 'profit_factor'] as const, fallback)
)

export const createEmptyBacktestPageSnapshot = (): BacktestPageSnapshot => ({
  config: {
    strategy_key: '',
    strategy_version: 1,
    timeframe: '',
    start_date: '',
    end_date: '',
    initial_cash: 0,
    fee_rate: 0,
    portfolio: {
      max_open_trades: 1,
      position_size_pct: 0,
      stake_mode: 'fixed',
    },
    research: {
      slippage_bps: 0,
      funding_rate_daily: 0,
      in_sample_ratio: 100,
      optimize_metric: 'sharpe',
      optimize_trials: 0,
      rolling_windows: 0,
    },
  },
  symbolsText: '',
  historyMode: 'backtest',
})

export const createBacktestPageSnapshotDefaults = (runDefaults: BacktestRunDefaultsResponse): BacktestPageSnapshot => ({
  config: {
    strategy_key: runDefaults.strategy_key ?? '',
    strategy_version: 1,
    timeframe: runDefaults.timeframe ?? '',
    start_date: runDefaults.start_date ?? '',
    end_date: runDefaults.end_date ?? '',
    initial_cash: runDefaults.initial_cash ?? 0,
    fee_rate: runDefaults.fee_rate ?? 0,
    portfolio: {
      max_open_trades: runDefaults.portfolio?.max_open_trades ?? 1,
      position_size_pct: runDefaults.portfolio?.position_size_pct ?? 0,
      stake_mode: runDefaults.portfolio?.stake_mode ?? 'fixed',
    },
    research: {
      slippage_bps: runDefaults.research?.slippage_bps ?? 0,
      funding_rate_daily: runDefaults.research?.funding_rate_daily ?? 0,
      in_sample_ratio: runDefaults.research?.in_sample_ratio ?? 100,
      optimize_metric: readOptimizeMetric(runDefaults.research?.optimize_metric, 'sharpe'),
      optimize_trials: runDefaults.research?.optimize_trials ?? 0,
      rolling_windows: runDefaults.research?.rolling_windows ?? 0,
    },
  },
  symbolsText: (runDefaults.portfolio?.symbols || []).join(', '),
  historyMode: runDefaults.history_mode === 'paper' ? 'paper' : 'backtest',
})

export const normalizeBacktestPageSnapshot = (
  value: unknown,
  defaults: BacktestPageSnapshot,
): BacktestPageSnapshot => {
  if (!isRecord(value) || !isRecord(value.config)) return defaults
  const config = value.config
  const portfolio = normalizeRecord(config.portfolio)
  const research = normalizeRecord(config.research)
  const historyMode = readString(value.historyMode, defaults.historyMode)

  return {
    config: {
      strategy_key: readString(config.strategy_key, defaults.config.strategy_key),
      strategy_version: readNumber(config.strategy_version, defaults.config.strategy_version),
      timeframe: readString(config.timeframe, defaults.config.timeframe),
      start_date: readString(config.start_date, defaults.config.start_date),
      end_date: readString(config.end_date, defaults.config.end_date),
      initial_cash: readNumber(config.initial_cash, defaults.config.initial_cash),
      fee_rate: readNumber(config.fee_rate, defaults.config.fee_rate),
      portfolio: {
        max_open_trades: readNumber(portfolio.max_open_trades, defaults.config.portfolio.max_open_trades),
        position_size_pct: readNumber(portfolio.position_size_pct, defaults.config.portfolio.position_size_pct),
        stake_mode: readStakeMode(portfolio.stake_mode, defaults.config.portfolio.stake_mode),
      },
      research: {
        slippage_bps: readNumber(research.slippage_bps, defaults.config.research.slippage_bps),
        funding_rate_daily: readNumber(research.funding_rate_daily, defaults.config.research.funding_rate_daily),
        in_sample_ratio: readNumber(research.in_sample_ratio, defaults.config.research.in_sample_ratio),
        optimize_metric: readOptimizeMetric(research.optimize_metric, defaults.config.research.optimize_metric),
        optimize_trials: readNumber(research.optimize_trials, defaults.config.research.optimize_trials),
        rolling_windows: readNumber(research.rolling_windows, defaults.config.research.rolling_windows),
      },
    },
    symbolsText: readString(value.symbolsText, defaults.symbolsText),
    historyMode: historyMode === 'paper' ? 'paper' : 'backtest',
  }
}

export const applyBacktestPageSnapshot = (
  config: BacktestPageSnapshot['config'],
  snapshot: BacktestPageSnapshot,
  symbolsText: { value: string },
  historyMode: { value: 'backtest' | 'paper' },
) => {
  config.strategy_key = snapshot.config.strategy_key
  config.strategy_version = snapshot.config.strategy_version
  config.timeframe = snapshot.config.timeframe
  config.start_date = snapshot.config.start_date
  config.end_date = snapshot.config.end_date
  config.initial_cash = snapshot.config.initial_cash
  config.fee_rate = snapshot.config.fee_rate
  config.portfolio = { ...snapshot.config.portfolio }
  config.research = { ...snapshot.config.research }
  symbolsText.value = snapshot.symbolsText
  historyMode.value = snapshot.historyMode
}

export const buildBacktestPageSnapshot = (
  config: BacktestPageSnapshot['config'],
  symbolsText: string,
  historyMode: 'backtest' | 'paper',
  defaults: BacktestPageSnapshot,
): BacktestPageSnapshot => normalizeBacktestPageSnapshot({
  config,
  symbolsText,
  historyMode,
}, defaults)

export const createDefaultBacktestEditorPageSnapshot = (): BacktestEditorPageSnapshot => ({
  config: {
    strategy_key: '',
    strategy_version: 0,
  },
  editor: null,
})

export const normalizeBacktestEditorPageSnapshot = (
  value: unknown,
  fallback = createDefaultBacktestEditorPageSnapshot(),
): BacktestEditorPageSnapshot => {
  const defaults = fallback
  if (!isRecord(value) || !isRecord(value.config)) return defaults

  const editor = isRecord(value.editor)
    ? {
        showVersionEditor: readBoolean(value.editor.showVersionEditor, false),
        showIndicatorCreator: readBoolean(value.editor.showIndicatorCreator, false),
        showTemplateCreator: readBoolean(value.editor.showTemplateCreator, false),
        useGlobalIndicatorCatalog: readBoolean(value.editor.useGlobalIndicatorCatalog, false),
        newIndicatorType: readString(value.editor.newIndicatorType, ''),
        versionDraft: normalizeRecord(value.editor.versionDraft),
        indicatorDraft: normalizeRecord(value.editor.indicatorDraft),
        templateDraft: normalizeRecord(value.editor.templateDraft),
      }
    : null

  return {
    config: {
      strategy_key: readString(value.config.strategy_key, defaults.config.strategy_key),
      strategy_version: readNumber(value.config.strategy_version, defaults.config.strategy_version),
    },
    editor,
  }
}

export const buildBacktestEditorPageSnapshot = (
  config: BacktestEditorPageSnapshot['config'],
  editor: BacktestEditorSnapshot,
): BacktestEditorPageSnapshot => normalizeBacktestEditorPageSnapshot({
  config,
  editor,
})


