import { onMounted, onUnmounted, ref, watch } from 'vue'
import {
  AreaSeries,
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
} from 'lightweight-charts'

import { useMoney } from '@/composables/useMoney'
import { formatAdaptivePrice } from '@/modules/format'
import { buildMainPriceFormat, buildStrategyMarkers } from './tradingViewChartPresentation'
import { useTradingViewTradeOverlay } from './useTradingViewTradeOverlay'


export const useTradingViewChart = (props, emit, t) => {
  const chartContainer = ref(null)
  const { displayCurrency } = useMoney()
  const chartPriceText = (value) => formatAdaptivePrice(value, 'USDT', '-')
  let chart = null
  let mainSeries = null
  let volumeSeries = null
  let strategyMarkerPlugin = null
  let resizeObserver = null

  const overlay = useTradingViewTradeOverlay({
    props,
    t,
    chartContainer,
    getChart: () => chart,
    getMainSeries: () => mainSeries,
    chartPriceText,
  })

  const createMainSeries = () => {
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

  const samePoint = (left, right) => left?.time === right?.time
    && left?.open === right?.open
    && left?.high === right?.high
    && left?.low === right?.low
    && left?.close === right?.close
    && left?.value === right?.value
    && left?.color === right?.color

  const incrementalStart = (nextData, previousData) => {
    if (!Array.isArray(previousData) || nextData.length !== previousData.length) return -1
    let index = 0
    while (index < nextData.length && samePoint(nextData[index], previousData[index])) index += 1
    if (index === nextData.length) return index
    if (nextData.length - index > 32) return -1
    for (let cursor = index; cursor < nextData.length; cursor += 1) {
      if (nextData[cursor]?.time !== previousData[cursor]?.time) return -1
    }
    return index
  }

  const syncSeriesData = (series, nextData, previousData) => {
    const start = incrementalStart(nextData, previousData)
    if (start === nextData.length) return
    if (start >= 0) {
      for (let index = start; index < nextData.length; index += 1) {
        series.update(nextData[index], index < nextData.length - 1)
      }
      return
    }
    series.setData(nextData)
  }

  const syncMainData = (nextData = props.data, previousData = []) => {
    if (!mainSeries && chart) {
      mainSeries = createMainSeries()
      overlay.syncTradeSetup()
    }
    mainSeries?.applyOptions({ priceFormat: buildMainPriceFormat(nextData) })
    if (mainSeries) syncSeriesData(mainSeries, nextData, previousData)
    overlay.syncAutoscale()
    overlay.scheduleOverlayUpdate()
    syncStrategyMarkers()
  }

  const syncVolumeData = (nextData = props.volumeData, previousData = []) => {
    syncVolumeSeries()
    if (volumeSeries) syncSeriesData(volumeSeries, nextData, previousData)
  }

  const updateData = () => {
    syncMainData(props.data, [])
    syncVolumeData(props.volumeData, [])
  }

  const initChart = () => {
    if (!chartContainer.value) return
    chart = createChart(chartContainer.value, {
      width: chartContainer.value.clientWidth,
      height: chartContainer.value.clientHeight,
      layout: { background: { color: props.colors.bg }, textColor: props.colors.text },
      grid: { vertLines: { color: props.colors.grid }, horzLines: { color: props.colors.grid } },
      timeScale: { borderColor: props.colors.grid, timeVisible: true },
      rightPriceScale: { borderColor: props.colors.grid },
    })
    mainSeries = createMainSeries()
    updateData()
    overlay.syncTradeSetup()
    syncStrategyMarkers()
  }

  const syncColors = (colors) => {
    if (!chart) return
    chart.applyOptions({
      layout: { background: { color: colors.bg }, textColor: colors.text },
      grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
      timeScale: { borderColor: colors.grid },
      rightPriceScale: { borderColor: colors.grid },
    })
    if (mainSeries && props.chartType !== 'area') {
      mainSeries.applyOptions({
        upColor: colors.upColor,
        downColor: colors.downColor,
        wickUpColor: colors.upColor,
        wickDownColor: colors.downColor,
      })
    }
    overlay.syncTradeSetup()
  }

  onMounted(() => {
    initChart()
    if (props.autoResize) {
      resizeObserver = new ResizeObserver((entries) => {
        if (!entries.length || entries[0].target !== chartContainer.value || !chart) return
        const rect = entries[0].contentRect
        chart.applyOptions({ width: rect.width, height: rect.height })
        overlay.scheduleOverlayUpdate()
      })
      resizeObserver.observe(chartContainer.value)
    }
    chart?.timeScale().subscribeVisibleLogicalRangeChange(() => {
      const logicalRange = chart?.timeScale().getVisibleLogicalRange()
      overlay.scheduleOverlayUpdate()
      if (logicalRange !== null && logicalRange !== undefined && logicalRange.from < 10) emit('load-more')
    })
  })

  onUnmounted(() => {
    overlay.disposeTradeOverlay()
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
  watch(() => props.tradeSetup, overlay.syncTradeSetup, { deep: true })
  watch(() => props.strategyMarkers, syncStrategyMarkers, { deep: true })
  watch(displayCurrency, overlay.syncTradeSetup)
  watch(() => props.colors, syncColors, { deep: true })

  return {
    chartContainer,
    tradeOverlay: overlay.tradeOverlay,
    chartPriceText,
    getChart: () => chart,
  }
}
