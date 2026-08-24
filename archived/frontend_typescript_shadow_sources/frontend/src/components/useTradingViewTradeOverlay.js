import { ref } from 'vue'
import { LineStyle } from 'lightweight-charts'


export const useTradingViewTradeOverlay = ({
  props,
  t,
  chartContainer,
  getChart,
  getMainSeries,
  chartPriceText,
}) => {
  const tradeOverlay = ref(null)
  let tradePriceLines = []
  let overlayFrame = 0

  const buildAutoscaleInfoProvider = () => (baseImplementation) => {
    const baseInfo = baseImplementation()
    const setup = props.tradeSetup
    if (!setup) return baseInfo

    const setupPrices = [setup.entry, setup.target, setup.stop].filter(Number.isFinite)
    if (!setupPrices.length) return baseInfo
    const setupMin = Math.min(...setupPrices)
    const setupMax = Math.max(...setupPrices)
    const baseMin = baseInfo?.priceRange?.minValue ?? setupMin
    const baseMax = baseInfo?.priceRange?.maxValue ?? setupMax
    const mergedMin = Math.min(baseMin, setupMin)
    const mergedMax = Math.max(baseMax, setupMax)
    const span = Math.max(mergedMax - mergedMin, mergedMax * 0.01, 1)
    const padding = span * 0.08
    return {
      ...baseInfo,
      priceRange: { minValue: mergedMin - padding, maxValue: mergedMax + padding },
    }
  }

  const syncAutoscale = () => {
    getMainSeries()?.applyOptions({ autoscaleInfoProvider: buildAutoscaleInfoProvider() })
  }

  const clearTradePriceLines = () => {
    const series = getMainSeries()
    if (!series) return
    tradePriceLines.forEach((line) => series.removePriceLine(line))
    tradePriceLines = []
  }

  const updateTradeOverlay = () => {
    overlayFrame = 0
    const chart = getChart()
    const series = getMainSeries()
    if (!chart || !series || !chartContainer.value || !props.tradeSetup) {
      tradeOverlay.value = null
      return
    }

    const setup = props.tradeSetup
    const width = chartContainer.value.clientWidth
    const entryY = series.priceToCoordinate(setup.entry)
    const targetY = series.priceToCoordinate(setup.target)
    const stopY = series.priceToCoordinate(setup.stop)
    if (entryY === null || targetY === null || stopY === null) {
      tradeOverlay.value = null
      return
    }

    const timeX = chart.timeScale().timeToCoordinate(Math.floor(setup.entry_time / 1000))
    const left = Math.max(12, Math.min(width - 180, (timeX ?? width * 0.58) + 10))
    const boxWidth = Math.max(120, Math.min(260, width - left - 70))
    const labelLeft = Math.min(width - 150, left + boxWidth + 8)
    tradeOverlay.value = {
      rewardBox: {
        left: `${left}px`, top: `${Math.min(entryY, targetY)}px`, width: `${boxWidth}px`, height: `${Math.max(6, Math.abs(targetY - entryY))}px`,
      },
      riskBox: {
        left: `${left}px`, top: `${Math.min(entryY, stopY)}px`, width: `${boxWidth}px`, height: `${Math.max(6, Math.abs(stopY - entryY))}px`,
      },
      entryLabel: { left: `${labelLeft}px`, top: `${entryY - 12}px` },
      targetLabel: { left: `${labelLeft}px`, top: `${targetY - 12}px` },
      stopLabel: { left: `${labelLeft}px`, top: `${stopY - 12}px` },
      ratioLabel: { left: `${left}px`, top: `${Math.min(entryY, targetY, stopY) - 30}px` },
    }
  }

  const scheduleOverlayUpdate = () => {
    if (overlayFrame) cancelAnimationFrame(overlayFrame)
    overlayFrame = requestAnimationFrame(updateTradeOverlay)
  }

  const syncTradeSetup = () => {
    clearTradePriceLines()
    const series = getMainSeries()
    if (!series || !props.tradeSetup) {
      syncAutoscale()
      tradeOverlay.value = null
      return
    }
    const setup = props.tradeSetup
    const lineConfig = [
      { price: setup.entry, title: t('dashboard.entry'), color: '#111827', style: LineStyle.Dashed },
      { price: setup.target, title: t('dashboard.target'), color: '#059669', style: LineStyle.Solid },
      { price: setup.stop, title: t('dashboard.stop'), color: '#e11d48', style: LineStyle.Solid },
    ]
    tradePriceLines = lineConfig.map((item) => series.createPriceLine({
      price: item.price,
      color: item.color,
      lineWidth: 2,
      lineStyle: item.style,
      axisLabelVisible: true,
      title: `${item.title} ${chartPriceText(item.price)}`,
    }))
    syncAutoscale()
    scheduleOverlayUpdate()
  }

  const disposeTradeOverlay = () => {
    if (overlayFrame) cancelAnimationFrame(overlayFrame)
    clearTradePriceLines()
    tradeOverlay.value = null
  }

  return {
    tradeOverlay,
    scheduleOverlayUpdate,
    syncAutoscale,
    syncTradeSetup,
    disposeTradeOverlay,
  }
}
