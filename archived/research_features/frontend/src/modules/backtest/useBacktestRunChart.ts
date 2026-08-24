import { reactive } from 'vue'

import { marketHistoryApi } from '@/modules/market'
import type { CandlestickData, ChartMarkerData, VolumeData } from './contracts'
import type { BacktestDetailResponse } from './contracts'
import type { OhlcvPointResponse } from '@/modules/market/contracts'

import type { BacktestChartData } from './viewTypes'

export const useBacktestRunChart = () => {
  const chartData = reactive<BacktestChartData>({ candles: [], volume: [], markers: [] })

  const loadChart = async (run: BacktestDetailResponse) => {
    const targetSymbol = Array.isArray(run?.metadata?.symbols) && run.metadata.symbols.length ? run.metadata.symbols[0] : run?.symbol
    if (!targetSymbol || targetSymbol === 'PORTFOLIO' || !run?.start_date) {
      chartData.candles = []
      chartData.volume = []
      chartData.markers = []
      return
    }
    const startDate = run.start_date.slice(0, 10)
    const endTs = run.end_date ? new Date(run.end_date).getTime() : Date.now()
    const res = await marketHistoryApi.getPriceHistory({
      symbol: targetSymbol,
      timeframe: run.timeframe,
      start_date: startDate,
      fetch_policy: 'hydrate',
    })
    const candles = (res.items || []).filter((item: OhlcvPointResponse) => item.timestamp <= endTs)
    chartData.candles = candles.map<CandlestickData>((item) => ({
      time: item.timestamp / 1000,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }))
    chartData.volume = candles.map<VolumeData>((item) => ({
      time: item.timestamp / 1000,
      value: item.volume,
      color: item.close >= item.open ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.5)',
    }))
    chartData.markers = buildRunChartMarkers(run, targetSymbol)
  }

  const clearChart = () => {
    chartData.candles = []
    chartData.volume = []
    chartData.markers = []
  }

  return {
    chartData,
    loadChart,
    clearChart,
  }
}

const buildRunChartMarkers = (run: BacktestDetailResponse, symbol: string): ChartMarkerData[] => {
  const previewMarkers = (((run.metadata?.preview as unknown as { markers?: Record<string, ChartMarkerData[]> } | null)?.markers || {})[symbol] || [])
    .map((item) => ({
      time: Number(item.time),
      kind: String(item.kind || ''),
      label: `预览 ${item.label || item.kind || ''}`,
      color: previewColor(String(item.kind || '')),
      shape: previewShape(String(item.kind || '')),
      position: previewPosition(String(item.kind || '')),
    }))

  const tradeMarkers = (run.trades || []).flatMap<ChartMarkerData>((trade) => {
    if (trade.pair && trade.pair !== symbol) return []
    const side = trade.side === 'short' ? 'short' : 'long'
    const markers: ChartMarkerData[] = []
    if (trade.opened_at) {
      markers.push({
        time: new Date(trade.opened_at).getTime(),
        kind: `executed_${side}_entry`,
        label: side === 'short' ? '成交 空' : '成交 多',
        color: side === 'short' ? '#7f1d1d' : '#064e3b',
        shape: side === 'short' ? 'arrowDown' : 'arrowUp',
        position: side === 'short' ? 'aboveBar' : 'belowBar',
      })
    }
    if (trade.closed_at) {
      markers.push({
        time: new Date(trade.closed_at).getTime(),
        kind: `executed_${side}_exit`,
        label: '成交 平',
        color: '#111827',
        shape: 'square',
        position: 'inBar',
      })
    }
    return markers
  })

  return [...previewMarkers, ...tradeMarkers]
    .filter((item) => Number.isFinite(item.time))
    .sort((left, right) => left.time - right.time)
}

const previewPosition = (kind: string): ChartMarkerData['position'] => (kind.includes('entry') ? 'belowBar' : 'aboveBar')
const previewShape = (kind: string): ChartMarkerData['shape'] => {
  if (kind === 'long_entry') return 'arrowUp'
  if (kind === 'short_entry') return 'arrowDown'
  return 'circle'
}
const previewColor = (kind: string) => {
  if (kind === 'long_entry') return '#10b981'
  if (kind === 'short_entry') return '#ef4444'
  if (kind === 'long_exit') return '#14b8a6'
  return '#fb7185'
}

