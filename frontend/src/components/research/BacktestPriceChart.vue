<template>
  <div ref="container" class="h-full w-full"><TradingViewChart ref="view" :data="data" :strategy-markers="[]" :colors="light ? { upColor: '#089981', downColor: '#f23645', bg: '#ffffff', text: '#363a45', grid: '#f3f3f3' } : undefined" /></div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { LineSeries, PriceScaleMode, type ISeriesApi, type MouseEventParams, type Time, type UTCTimestamp } from 'lightweight-charts'
import TradingViewChart from '@/components/TradingViewChart.vue'
import type { TradingViewDataPoint, TradingViewStrategyMarker } from '@/components/tradingViewChartPresentation'
import { TrendCloudPrimitive } from './trendCloudPrimitive'
import { SignalLabelPrimitive } from './signalLabelPrimitive'

const props = defineProps<{
  data: TradingViewDataPoint[]
  markers: TradingViewStrategyMarker[]
  levels: Record<string, unknown>[]
  indicators: Record<string, unknown>[]
  logarithmic: boolean
  timezoneOffset: number
  light?: boolean
  labelSignals?: boolean
}>()
const emit = defineEmits<{ inspect: [timestamp: number] }>()
const view = ref<InstanceType<typeof TradingViewChart> | null>(null)
const container = ref<HTMLElement | null>(null)
let resize: ResizeObserver | null = null, resizeFrame = 0
let stop: ISeriesApi<'Line', Time> | null = null
let target: ISeriesApi<'Line', Time> | null = null
let upper: ISeriesApi<'Line', Time> | null = null
let lower: ISeriesApi<'Line', Time> | null = null
let subscribed = false
const cloud = new TrendCloudPrimitive()
const labels = new SignalLabelPrimitive()
const inspect = (p: MouseEventParams<Time>) => { if (typeof p.time === 'number') emit('inspect', p.time * 1000) }
const localTime = (time: Time) => new Date((Number(time) + props.timezoneOffset * 3600) * 1000).toISOString().slice(0, 16).replace('T', ' ')
async function sync() {
  await nextTick()
  const chart = view.value?.chart
  if (!chart) return
  if (!subscribed) { chart.subscribeClick(inspect); subscribed = true }
  chart.priceScale('right').applyOptions({ mode: props.logarithmic ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal, scaleMargins: { top: 0.16, bottom: 0.1 } })
  chart.applyOptions({ localization: { timeFormatter: localTime },
    timeScale: { tickMarkFormatter: (time: Time, type: number) => type >= 3 ? localTime(time).slice(11) : localTime(time).slice(5, 10) } })
  stop ??= chart.addSeries(LineSeries, { color: '#e85c5c', lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
  target ??= chart.addSeries(LineSeries, { color: '#14b88a', lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
  const times = new Set(props.data.map(v => v.time))
  if (!upper) {
    const options = { color: 'transparent', priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }
    upper = chart.addSeries(LineSeries, options); lower = chart.addSeries(LineSeries, options)
    upper.attachPrimitive(cloud)
    upper.attachPrimitive(labels)
  }
  const points = props.indicators.filter(v => v.cloud && times.has(Number(v.timestamp) / 1000)).map(v => {
    const c = v.cloud as { upper: number; lower: number; bullish: boolean }
    return { time: Number(v.timestamp) / 1000 as UTCTimestamp, ...c }
  })
  // The label renderer needs a populated price series even for strategies that
  // emit no cloud observations (e.g. a moving-average crossover).
  upper.setData(points.length ? points.map(p => ({ time: p.time, value: p.upper }))
    : props.data.map(p => ({ time: p.time as UTCTimestamp, value: p.close })))
  lower!.setData(points.map(p => ({ time: p.time, value: p.lower })))
  cloud.setData(points, props.data.length > 1 ? props.data[1]!.time - props.data[0]!.time : 0)
  labels.setData(props.markers, props.data)
  for (const [series, key] of [[stop, 'stop'], [target, 'target']] as const) {
    series.setData(props.levels.filter(v => v[key] != null && times.has(Number(v.timestamp) / 1000))
      .map(v => ({ time: Number(v.timestamp) / 1000 as UTCTimestamp, value: Number(v[key]) })))
  }
  chart.timeScale().fitContent()
}
watch(() => [props.data, props.levels, props.indicators, props.markers, props.labelSignals, props.logarithmic, props.timezoneOffset], sync)
onMounted(() => {
  sync()
  resize = new ResizeObserver(() => {
    cancelAnimationFrame(resizeFrame)
    resizeFrame = requestAnimationFrame(() => view.value?.chart?.timeScale().fitContent())
  })
  if (container.value) resize.observe(container.value)
})
onBeforeUnmount(() => { resize?.disconnect(); cancelAnimationFrame(resizeFrame); view.value?.chart?.unsubscribeClick(inspect); upper?.detachPrimitive(cloud); upper?.detachPrimitive(labels); stop = null; target = null; upper = null; lower = null })
</script>
