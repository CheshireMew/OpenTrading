import { computed, ref, type Ref } from 'vue'

import { backtestApi } from './api'
import type { BacktestPageConfig, BacktestChartData } from './viewTypes'
import type { BacktestPreviewResponse, StrategyPreviewMarkerResponse } from './contracts'


interface UseBacktestRunExecutionOptions {
  t: (key: string) => string
  config: BacktestPageConfig
  backtestLoading: Ref<boolean>
  paperLoading: Ref<boolean>
  historyMode: Ref<'backtest' | 'paper'>
  symbolsText: Ref<string>
  fetchHistory: () => Promise<void>
  fetchPaperHistory: () => Promise<void>
}

export const useBacktestRunExecution = ({
  t,
  config,
  backtestLoading,
  paperLoading,
  historyMode,
  symbolsText,
  fetchHistory,
  fetchPaperHistory,
}: UseBacktestRunExecutionOptions) => {
  const splitSymbols = () => symbolsText.value.split(',').map((item) => item.trim()).filter(Boolean)
  const isBusy = () => backtestLoading.value || paperLoading.value
  const previewLoading = ref(false)
  const strategyPreview = ref<BacktestPreviewResponse | null>(null)
  const previewSymbol = ref('')

  const buildPreviewPayload = () => ({
    strategy_key: config.strategy_key,
    strategy_version: config.strategy_version,
    timeframe: config.timeframe,
    start_date: config.start_date,
    end_date: config.end_date,
    initial_cash: config.initial_cash,
    fee_rate: config.fee_rate,
    portfolio: {
      symbols: splitSymbols(),
      max_open_trades: config.portfolio.max_open_trades,
      position_size_pct: config.portfolio.position_size_pct,
      stake_mode: config.portfolio.stake_mode,
    },
    research: {
      slippage_bps: config.research.slippage_bps,
      funding_rate_daily: config.research.funding_rate_daily,
      in_sample_ratio: config.research.in_sample_ratio,
      optimize_metric: config.research.optimize_metric,
      optimize_trials: config.research.optimize_trials,
      rolling_windows: config.research.rolling_windows,
    },
  })

  const buildPayload = () => {
    if (!strategyPreview.value) {
      throw new Error(t('backtest.previewRequired'))
    }
    return {
      ...buildPreviewPayload(),
      preview_id: strategyPreview.value.preview_id,
      approved_fingerprint: strategyPreview.value.fingerprint,
    }
  }

  const buildPaperPayload = () => ({
    strategy_key: config.strategy_key,
    strategy_version: config.strategy_version,
    timeframe: config.timeframe,
    initial_cash: config.initial_cash,
    fee_rate: config.fee_rate,
    portfolio: {
      symbols: splitSymbols(),
      max_open_trades: config.portfolio.max_open_trades,
      position_size_pct: config.portfolio.position_size_pct,
      stake_mode: config.portfolio.stake_mode,
    },
  })

  const previewSymbols = computed(() => strategyPreview.value?.symbols || [])
  const previewMarkers = computed<StrategyPreviewMarkerResponse[]>(() => {
    const symbol = previewSymbol.value
    if (!symbol || !strategyPreview.value?.markers) return []
    return strategyPreview.value.markers[symbol] || []
  })
  const previewChartData = computed<BacktestChartData>(() => {
    const symbol = previewSymbol.value
    const candles = symbol && strategyPreview.value?.candles ? strategyPreview.value.candles[symbol] || [] : []
    return {
      candles: candles.map((item) => ({
        time: item.timestamp / 1000,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      })),
      volume: candles.map((item) => ({
        time: item.timestamp / 1000,
        value: item.volume,
        color: item.close >= item.open ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.5)',
      })),
      markers: previewMarkers.value.map((item) => ({
        time: item.time,
        kind: item.kind,
        label: item.label,
      })),
    }
  })

  const clearPreview = () => {
    strategyPreview.value = null
    previewSymbol.value = ''
  }

  const previewBacktest = async () => {
    if (isBusy() || previewLoading.value) return null
    if (!config.start_date || !config.end_date) {
      alert(t('backtest.rangeRequired'))
      return null
    }
    previewLoading.value = true
    try {
      const res = await backtestApi.previewRun(buildPreviewPayload())
      strategyPreview.value = res
      previewSymbol.value = res.symbols?.[0] || ''
      return res
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      alert(`${t('backtest.previewFailed')}: ${detail}`)
    } finally {
      previewLoading.value = false
    }
    return null
  }

  const startBacktest = async () => {
    if (isBusy()) return null
    if (!config.start_date || !config.end_date) {
      alert(t('backtest.rangeRequired'))
      return null
    }
    if (!strategyPreview.value) {
      alert(t('backtest.previewRequired'))
      return null
    }
    backtestLoading.value = true
    try {
      const res = await backtestApi.startRun(buildPayload())
      if (res.success) {
        historyMode.value = 'backtest'
        await fetchHistory()
        return { id: res.backtest_id, mode: 'backtest' as const }
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      alert(`${t('backtest.failed')}: ${detail}`)
    } finally {
      backtestLoading.value = false
    }
    return null
  }

  const startPaperRun = async () => {
    if (isBusy()) return null
    paperLoading.value = true
    try {
      const res = await backtestApi.startPaperRun(buildPaperPayload())
      if (res.success) {
        historyMode.value = 'paper'
        await fetchPaperHistory()
        return { id: res.run_id, mode: 'paper' as const }
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      alert(`${t('backtest.paperFailed')}: ${detail}`)
    } finally {
      paperLoading.value = false
    }
    return null
  }

  return {
    previewLoading,
    strategyPreview,
    previewSymbol,
    previewSymbols,
    previewChartData,
    previewMarkers,
    buildPreviewPayload,
    buildPayload,
    buildPaperPayload,
    clearPreview,
    previewBacktest,
    startBacktest,
    startPaperRun,
  }
}

