import { onMounted, onUnmounted, ref, watch } from 'vue'
import {
  AreaSeries,
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type AreaData,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts'

import { useMoney } from '@/composables/useMoney'
import { formatAdaptivePrice } from '@/modules/format'
import {
  buildMainPriceFormat,
  buildStrategyMarkers,
  type TradingViewDataPoint,
  type TradingViewStrategyMarker,
  type TradingViewVolumePoint,
} from './tradingViewChartPresentation'
type TradingViewMainSeries = ISeriesApi<'Candlestick'> | ISeriesApi<'Area'>


export interface TradingViewChartColors {
  upColor: string
  downColor: string
  bg: string
  text: string
  grid: string
}

export interface TradingViewChartProps {
  data: TradingViewDataPoint[]
  volumeData: TradingViewVolumePoint[]
  chartType: 'candlestick' | 'area'
  autoResize: boolean
  colors: TradingViewChartColors
  strategyMarkers: TradingViewStrategyMarker[]
}

type TradingViewChartEmit = (event: 'load-more') => void

const candleData = (items: TradingViewDataPoint[]): CandlestickData[] => (
  items.map((item) => ({ ...item, time: item.time as UTCTimestamp }))
)

const areaData = (items: TradingViewDataPoint[]): AreaData[] => (
  items.map((item) => ({ time: item.time as UTCTimestamp, value: item.close }))
)

const volumeData = (items: TradingViewVolumePoint[]): HistogramData[] => (
  items.map((item) => ({ ...item, time: item.time as UTCTimestamp }))
)

interface ComparablePoint {
  time: number
  open?: number
  high?: number
  low?: number
  close?: number
  value?: number
  color?: string
}

const samePoint = (
  left: ComparablePoint | undefined,
  right: ComparablePoint | undefined,
) => left?.time === right?.time
  && left?.open === right?.open
  && left?.high === right?.high
  && left?.low === right?.low
  && left?.close === right?.close
  && left?.value === right?.value
  && left?.color === right?.color

const incrementalStart = <T extends TradingViewDataPoint | TradingViewVolumePoint>(
  nextData: T[],
  previousData: T[],
) => {
  if (nextData.length !== previousData.length) return -1
  let index = 0
  while (index < nextData.length && samePoint(nextData[index], previousData[index])) index += 1
  if (index === nextData.length) return index
  if (nextData.length - index > 32) return -1
  for (let cursor = index; cursor < nextData.length; cursor += 1) {
    if (nextData[cursor]?.time !== previousData[cursor]?.time) return -1
  }
  return index
}

export const useTradingViewChart = (
  props: TradingViewChartProps,
  emit: TradingViewChartEmit,
  t: (key: string) => string,
) => {
  const chartContainer = ref<HTMLElement | null>(null)
  const { displayCurrency } = useMoney()
  const chartPriceText = (value: number) => formatAdaptivePrice(value, 'USDT', '-')
  let chart: IChartApi | null = null
  let mainSeries: TradingViewMainSeries | null = null
  let volumeSeries: ISeriesApi<'Histogram'> | null = null
  let strategyMarkerPlugin: ISeriesMarkersPluginApi<Time> | null = null
  let resizeObserver: ResizeObserver | null = null

  const createMainSeries = (): TradingViewMainSeries | null => {
    if (!chart) return null
    if (props.chartType === 'area') {
      return chart.addSeries(AreaSeries, {
        lineColor: '#2962FF',
        topColor: '#2962FF',
        bottomColor: 'rgba(41, 98, 255, 0.28)',
        priceFormat: buildMainPriceFormat(props.data),
      })
    }
    return chart.addSeries(CandlestickSeries, {
      upColor: props.colors.upColor,
      downColor: props.colors.downColor,
      borderVisible: false,
      wickUpColor: props.colors.upColor,
      wickDownColor: props.colors.downColor,
      priceFormat: buildMainPriceFormat(props.data),
    })
  }

  const syncVolumeSeries = () => {
    if (!chart) return
    if (props.volumeData.length > 0 && !volumeSeries) {
      volumeSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: '' })
      volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
      return
    }
    if (props.volumeData.length === 0 && volumeSeries) {
      chart.removeSeries(volumeSeries)
      volumeSeries = null
    }
  }

  const syncStrategyMarkers = () => {
    if (!mainSeries) return
    const markers = buildStrategyMarkers(props.strategyMarkers || [])
    if (!strategyMarkerPlugin) {
      strategyMarkerPlugin = createSeriesMarkers(mainSeries, markers)
      return
    }
    strategyMarkerPlugin.setMarkers(markers)
  }

  const syncCandleSeries = (next: TradingViewDataPoint[], previous: TradingViewDataPoint[]) => {
    if (!mainSeries) return
    const start = incrementalStart(next, previous)
    if (start === next.length) return
    if (props.chartType === 'area') {
      const converted = areaData(next)
      const series = mainSeries as ISeriesApi<'Area'>
      if (start >= 0) {
        for (let index = start; index < converted.length; index += 1) {
          series.update(converted[index], index < converted.length - 1)
        }
      } else series.setData(converted)
      return
    }
    const converted = candleData(next)
    const series = mainSeries as ISeriesApi<'Candlestick'>
    if (start >= 0) {
      for (let index = start; index < converted.length; index += 1) {
        series.update(converted[index], index < converted.length - 1)
      }
    } else series.setData(converted)
  }

  const syncVolumeData = (next: TradingViewVolumePoint[] = props.volumeData, previous: TradingViewVolumePoint[] = []) => {
    syncVolumeSeries()
    if (!volumeSeries) return
    const start = incrementalStart(next, previous)
    if (start === next.length) return
    const converted = volumeData(next)
    if (start >= 0) {
      for (let index = start; index < converted.length; index += 1) {
        volumeSeries.update(converted[index], index < converted.length - 1)
      }
    } else volumeSeries.setData(converted)
  }

  const syncMainData = (next: TradingViewDataPoint[] = props.data, previous: TradingViewDataPoint[] = []) => {
    if (!mainSeries && chart) {
      mainSeries = createMainSeries()
    }
    mainSeries?.applyOptions({ priceFormat: buildMainPriceFormat(next) })
    syncCandleSeries(next, previous)
    syncStrategyMarkers()
  }

  const updateData = () => {
    syncMainData(props.data, [])
    syncVolumeData(props.volumeData, [])
  }

  const initChart = () => {
    const container = chartContainer.value
    if (!container) return
    chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: { background: { color: props.colors.bg }, textColor: props.colors.text },
      grid: { vertLines: { color: props.colors.grid }, horzLines: { color: props.colors.grid } },
      timeScale: { borderColor: props.colors.grid, timeVisible: true },
      rightPriceScale: { borderColor: props.colors.grid },
    })
    mainSeries = createMainSeries()
    updateData()
    syncStrategyMarkers()
  }

  const syncColors = (colors: TradingViewChartColors) => {
    if (!chart) return
    chart.applyOptions({
      layout: { background: { color: colors.bg }, textColor: colors.text },
      grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
      timeScale: { borderColor: colors.grid },
      rightPriceScale: { borderColor: colors.grid },
    })
    if (mainSeries && props.chartType !== 'area') {
      (mainSeries as ISeriesApi<'Candlestick'>).applyOptions({
        upColor: colors.upColor,
        downColor: colors.downColor,
        wickUpColor: colors.upColor,
        wickDownColor: colors.downColor,
      })
    }
  }

  onMounted(() => {
    initChart()
    const container = chartContainer.value
    if (props.autoResize && container) {
      resizeObserver = new ResizeObserver((entries) => {
        if (!entries.length || entries[0].target !== chartContainer.value || !chart) return
        const rect = entries[0].contentRect
        chart.applyOptions({ width: rect.width, height: rect.height })
      })
      resizeObserver.observe(container)
    }
    chart?.timeScale().subscribeVisibleLogicalRangeChange(() => {
      const logicalRange = chart?.timeScale().getVisibleLogicalRange()
      if (logicalRange && logicalRange.from < 10) emit('load-more')
    })
  })

  onUnmounted(() => {
    strategyMarkerPlugin?.detach()
    strategyMarkerPlugin = null
    chart?.remove()
    chart = null
    mainSeries = null
    volumeSeries = null
    resizeObserver?.disconnect()
    resizeObserver = null
  })

  watch(() => props.data, syncMainData)
  watch(() => props.volumeData, syncVolumeData)
  watch(() => props.strategyMarkers, syncStrategyMarkers, { deep: true })
  watch(() => props.colors, syncColors, { deep: true })

  return {
    chartContainer,
    chartPriceText,
    getChart: () => chart,
  }
}
