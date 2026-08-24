<template>
  <div class="relative w-full h-full" ref="chartContainer">
    <div
      v-if="tradeOverlay"
      class="pointer-events-none absolute inset-0 z-10 text-xs font-semibold"
    >
      <div
        class="absolute rounded border border-emerald-400/50 bg-emerald-400/20"
        :style="tradeOverlay.rewardBox"
      />
      <div
        class="absolute rounded border border-rose-400/50 bg-rose-400/20"
        :style="tradeOverlay.riskBox"
      />
      <div
        class="absolute rounded bg-gray-900 px-2 py-1 text-white shadow dark:bg-white dark:text-gray-900"
        :style="tradeOverlay.entryLabel"
      >
        {{ t('dashboard.entry') }} {{ chartPriceText(tradeSetup.entry) }}
      </div>
      <div
        class="absolute rounded bg-emerald-600 px-2 py-1 text-white shadow"
        :style="tradeOverlay.targetLabel"
      >
        {{ t('dashboard.target') }} {{ chartPriceText(tradeSetup.target) }}
      </div>
      <div
        class="absolute rounded bg-rose-600 px-2 py-1 text-white shadow"
        :style="tradeOverlay.stopLabel"
      >
        {{ t('dashboard.stop') }} {{ chartPriceText(tradeSetup.stop) }}
      </div>
      <div
        class="absolute rounded bg-gray-900 px-2 py-1 text-white shadow dark:bg-white dark:text-gray-900"
        :style="tradeOverlay.ratioLabel"
      >
        {{ t('dashboard.riskReward') }} {{ tradeSetup.risk_reward.toFixed(2) }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { createChart, CandlestickSeries, AreaSeries, HistogramSeries, LineStyle, createSeriesMarkers } from 'lightweight-charts'
import { useMoney } from '@/composables/useMoney'
import { formatAdaptivePrice } from '@/modules/format'

const { t } = useI18n()

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  },
  volumeData: {
    type: Array,
    default: () => []
  },
  chartType: {
    type: String,
    default: 'candlestick' // 'candlestick' | 'line' | 'area'
  },
  autoResize: {
      type: Boolean,
      default: true
  },
  colors: {
    type: Object,
    default: () => ({
      upColor: '#26a69a',
      downColor: '#ef5350',
      bg: '#1f2937', // gray-800
      text: '#9ca3af', // gray-400
      grid: '#374151'  // gray-700
    })
  },
  tradeSetup: {
    type: Object,
    default: null
  },
  strategyMarkers: {
    type: Array,
    default: () => []
  }
})

const chartContainer = ref(null)
const { displayCurrency } = useMoney()
const tradeOverlay = ref(null)
let chart = null
let mainSeries = null
let volumeSeries = null
let tradePriceLines = []
let strategyMarkerPlugin = null
let overlayFrame = 0

const resolvePricePrecision = () => {
    const prices = props.data.flatMap(item => [item.open, item.high, item.low, item.close])
        .map(Number)
        .filter(value => Number.isFinite(value) && Math.abs(value) > 0)
    if (!prices.length) return 2

    const minPrice = Math.min(...prices.map(value => Math.abs(value)))
    if (minPrice >= 100) return 2
    if (minPrice >= 1) return 4

    return Math.min(10, Math.max(2, Math.ceil(Math.abs(Math.log10(minPrice))) + 3))
}

const buildMainPriceFormat = () => {
    const precision = resolvePricePrecision()
    return {
        type: 'price',
        precision,
        minMove: 10 ** -precision,
    }
}

const syncMainPriceFormat = () => {
    if (!mainSeries) return
    mainSeries.applyOptions({
        priceFormat: buildMainPriceFormat(),
    })
}

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
        priceRange: {
            minValue: mergedMin - padding,
            maxValue: mergedMax + padding,
        },
    }
}

const syncAutoscale = () => {
    if (!mainSeries) return
    mainSeries.applyOptions({
        autoscaleInfoProvider: buildAutoscaleInfoProvider(),
    })
}

const chartPriceText = (value) => formatAdaptivePrice(value, 'USDT', '-')

const clearTradePriceLines = () => {
    if (!mainSeries) return
    tradePriceLines.forEach(line => mainSeries.removePriceLine(line))
    tradePriceLines = []
}

const syncTradeSetup = () => {
    clearTradePriceLines()
    if (!mainSeries || !props.tradeSetup) {
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
    tradePriceLines = lineConfig.map(item => mainSeries.createPriceLine({
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

const markerPosition = (kind) => (kind.includes('entry') ? 'belowBar' : 'aboveBar')
const markerShape = (kind) => {
    if (kind === 'long_entry') return 'arrowUp'
    if (kind === 'short_entry') return 'arrowDown'
    return 'circle'
}
const markerColor = (kind) => {
    if (kind === 'long_entry') return '#059669'
    if (kind === 'short_entry') return '#dc2626'
    if (kind === 'long_exit') return '#0f766e'
    return '#be123c'
}

const syncStrategyMarkers = () => {
    if (!mainSeries) return
    const markers = (props.strategyMarkers || [])
        .map(item => ({
            time: Math.floor(Number(item.time) / 1000),
            position: item.position || markerPosition(String(item.kind || '')),
            color: item.color || markerColor(String(item.kind || '')),
            shape: item.shape || markerShape(String(item.kind || '')),
            text: item.label || item.kind || '',
        }))
        .filter(item => Number.isFinite(item.time))
        .sort((left, right) => left.time - right.time)

    if (!strategyMarkerPlugin) {
        strategyMarkerPlugin = createSeriesMarkers(mainSeries, markers)
        return
    }
    strategyMarkerPlugin.setMarkers(markers)
}

const scheduleOverlayUpdate = () => {
    if (overlayFrame) cancelAnimationFrame(overlayFrame)
    overlayFrame = requestAnimationFrame(updateTradeOverlay)
}

const updateTradeOverlay = () => {
    overlayFrame = 0
    if (!chart || !mainSeries || !chartContainer.value || !props.tradeSetup) {
        tradeOverlay.value = null
        return
    }

    const setup = props.tradeSetup
    const width = chartContainer.value.clientWidth
    const entryY = mainSeries.priceToCoordinate(setup.entry)
    const targetY = mainSeries.priceToCoordinate(setup.target)
    const stopY = mainSeries.priceToCoordinate(setup.stop)
    if (entryY === null || targetY === null || stopY === null) {
        tradeOverlay.value = null
        return
    }

    const entryTime = Math.floor(setup.entry_time / 1000)
    const timeX = chart.timeScale().timeToCoordinate(entryTime)
    const left = Math.max(12, Math.min(width - 180, (timeX ?? width * 0.58) + 10))
    const boxWidth = Math.max(120, Math.min(260, width - left - 70))
    const labelLeft = Math.min(width - 150, left + boxWidth + 8)

    tradeOverlay.value = {
        rewardBox: {
            left: `${left}px`,
            top: `${Math.min(entryY, targetY)}px`,
            width: `${boxWidth}px`,
            height: `${Math.max(6, Math.abs(targetY - entryY))}px`,
        },
        riskBox: {
            left: `${left}px`,
            top: `${Math.min(entryY, stopY)}px`,
            width: `${boxWidth}px`,
            height: `${Math.max(6, Math.abs(stopY - entryY))}px`,
        },
        entryLabel: {
            left: `${labelLeft}px`,
            top: `${entryY - 12}px`,
        },
        targetLabel: {
            left: `${labelLeft}px`,
            top: `${targetY - 12}px`,
        },
        stopLabel: {
            left: `${labelLeft}px`,
            top: `${stopY - 12}px`,
        },
        ratioLabel: {
            left: `${left}px`,
            top: `${Math.min(entryY, targetY, stopY) - 30}px`,
        },
    }
}

const syncVolumeSeries = () => {
    if (!chart) return

    if (props.volumeData.length > 0 && !volumeSeries) {
        volumeSeries = chart.addSeries(HistogramSeries, {
            priceFormat: { type: 'volume' },
            priceScaleId: '',
        })
        volumeSeries.priceScale().applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        })
        return
    }

    if (props.volumeData.length === 0 && volumeSeries) {
        chart.removeSeries(volumeSeries)
        volumeSeries = null
    }
}

const initChart = () => {
    if (!chartContainer.value) return

    chart = createChart(chartContainer.value, {
        width: chartContainer.value.clientWidth,
        height: chartContainer.value.clientHeight,
        layout: {
            background: { color: props.colors.bg },
            textColor: props.colors.text,
        },
        grid: {
            vertLines: { color: props.colors.grid },
            horzLines: { color: props.colors.grid },
        },
        timeScale: {
            borderColor: props.colors.grid,
            timeVisible: true
        },
        rightPriceScale: {
            borderColor: props.colors.grid,
        },
    })

    // Main Series
    if (props.chartType === 'area') {
        mainSeries = chart.addSeries(AreaSeries, {
            lineColor: '#2962FF', topColor: '#2962FF', bottomColor: 'rgba(41, 98, 255, 0.28)',
            priceFormat: buildMainPriceFormat(),
        });
    } else {
        mainSeries = chart.addSeries(CandlestickSeries, {
            upColor: props.colors.upColor,
            downColor: props.colors.downColor,
            borderVisible: false,
            wickUpColor: props.colors.upColor,
            wickDownColor: props.colors.downColor,
            priceFormat: buildMainPriceFormat(),
        })
    }

    syncAutoscale()
    updateData()
    syncTradeSetup()
    syncStrategyMarkers()
}

const updateData = () => {
    if (!mainSeries && chart) {
        if (props.chartType === 'area') {
            mainSeries = chart.addSeries(AreaSeries, {
                lineColor: '#2962FF', topColor: '#2962FF', bottomColor: 'rgba(41, 98, 255, 0.28)',
                priceFormat: buildMainPriceFormat(),
            })
        } else {
            mainSeries = chart.addSeries(CandlestickSeries, {
                upColor: props.colors.upColor,
                downColor: props.colors.downColor,
                borderVisible: false,
                wickUpColor: props.colors.upColor,
                wickDownColor: props.colors.downColor,
                priceFormat: buildMainPriceFormat(),
            })
        }
        syncTradeSetup()
    }
    syncVolumeSeries()
    syncMainPriceFormat()
    if (mainSeries && props.data.length > 0) mainSeries.setData(props.data)
    if (volumeSeries && props.volumeData.length > 0) volumeSeries.setData(props.volumeData)
    syncAutoscale()
    scheduleOverlayUpdate()
    syncStrategyMarkers()
}

// Resize Observer
let resizeObserver = null

onMounted(() => {
    initChart()
    
    if (props.autoResize) {
        resizeObserver = new ResizeObserver(entries => {
            if (entries.length === 0 || entries[0].target !== chartContainer.value) { return }
            const newRect = entries[0].contentRect
            chart.applyOptions({ width: newRect.width, height: newRect.height })
            scheduleOverlayUpdate()
        })
        resizeObserver.observe(chartContainer.value)
    }
    
    // Infinite Scroll / Load More
    chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (!range) return
        // If scrolled near the beginning (left side)
        // logical range < 0 means we are scrolling into the past relative to initial data
        // But simpler check: if range.from is small (e.g. < 0 or close to min index)
        // Actually, logic is: pass event to parent, parent decides if need to load.
        // We just emit the range.
        const logicalRange = chart.timeScale().getVisibleLogicalRange();
        scheduleOverlayUpdate()
        if (logicalRange !== null && logicalRange.from < 10) {
             emit('load-more')
        }
    })
})

const emit = defineEmits(['load-more'])

onUnmounted(() => {
    if (overlayFrame) cancelAnimationFrame(overlayFrame)
    if (chart) {
        clearTradePriceLines()
        if (strategyMarkerPlugin) {
            strategyMarkerPlugin.detach()
            strategyMarkerPlugin = null
        }
        chart.remove()
        chart = null
    }
    if (resizeObserver) {
        resizeObserver.disconnect()
    }
})

watch(() => props.data, updateData, { deep: true })
watch(() => props.volumeData, updateData, { deep: true })
watch(() => props.tradeSetup, syncTradeSetup, { deep: true })
watch(() => props.strategyMarkers, syncStrategyMarkers, { deep: true })
watch(displayCurrency, syncTradeSetup)

watch(() => props.colors, (newColors) => {
    if (!chart) return
    chart.applyOptions({
        layout: {
            background: { color: newColors.bg },
            textColor: newColors.text,
        },
        grid: {
            vertLines: { color: newColors.grid },
            horzLines: { color: newColors.grid },
        },
        timeScale: {
            borderColor: newColors.grid,
        },
        rightPriceScale: {
            borderColor: newColors.grid,
        },
    })
    
    // Update Candlestick colors if needed
    if (mainSeries && props.chartType !== 'area') {
        mainSeries.applyOptions({
            upColor: newColors.upColor,
            downColor: newColors.downColor,
            wickUpColor: newColors.upColor,
            wickDownColor: newColors.downColor,
        })
    }
    syncTradeSetup()
}, { deep: true })

defineExpose({
    get chart() { return chart }
})

</script>
