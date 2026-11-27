import { NativeRenderer, type ChartConfig, type OHLCV, type VelaTheme, type VisibleRange } from '@luxalgo/vela'
import { registerRendererLayer } from '@luxalgo/vela/plugin'
import { DARK_PALETTE, LIGHT_PALETTE } from '@/theme/palette.mjs'
import { PRICE_ALERT_LAYER, type PriceAlertLayerSource } from './priceAlertLayer'
import { localizeCanvasDates } from './canvasLocale'
import { REPLAY_ORDER_LAYER, type ReplayLayerSource } from './replayOrderLayer'
import { INDICATOR_SELECTION_LAYER, installIndicatorInteraction, type IndicatorPicking } from './indicatorInteraction'

export const CHART_FONT = 'Arial, "Microsoft YaHei", sans-serif'
// Native candle bodies occupy 70% of this pitch: 14px gives a roughly 10px
// body, instead of the previous 4px body at a 7px pitch.
export const DEFAULT_CANDLE_SPACING = 14
const RIGHT_MARGIN_BARS = 6
export const chartPalette = (mode: 'light' | 'dark') => mode === 'dark' ? DARK_PALETTE : LIGHT_PALETTE
export function chartTheme(mode: 'light' | 'dark'): VelaTheme {
  const colors = chartPalette(mode)
  return { background: colors.panel, textColor: colors.text, gridColor: colors.grid,
    borderColor: colors.border, upColor: colors.positive, downColor: colors.negative, fontFamily: CHART_FONT }
}

const GRID_LAYER = 'opentrading-dense-grid'
const GRID_SPACING = 72
const MINUTE = 60000, HOUR = 60 * MINUTE, DAY = 24 * HOUR
const TIME_STEPS = [1000, 5000, 15000, 30000, MINUTE, 5 * MINUTE, 15 * MINUTE,
  30 * MINUTE, HOUR, 2 * HOUR, 4 * HOUR, 6 * HOUR, 12 * HOUR, DAY, 2 * DAY,
  7 * DAY, 30 * DAY, 90 * DAY, 365 * DAY]

export function gridStep(span: number, target: number): number {
  const raw = span / Math.max(1, target)
  if (!Number.isFinite(raw) || raw <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  return [1, 2, 2.5, 5, 10].reduce((best, value) =>
    Math.abs(Math.log(value * magnitude / raw)) < Math.abs(Math.log(best * magnitude / raw)) ? value : best) * magnitude
}

export function readableCandleRange(bars: readonly OHLCV[], width: number) {
  if (bars.length < 2 || !Number.isFinite(width) || width <= 0) return null
  const count = Math.min(bars.length, Math.max(2, Math.floor(width / DEFAULT_CANDLE_SPACING) - RIGHT_MARGIN_BARS + 1))
  const last = bars[bars.length - 1].time
  const interval = last - bars[bars.length - 2].time
  if (interval <= 0) return null
  return { from: bars[bars.length - count].time, to: last + interval * RIGHT_MARGIN_BARS }
}

type GridSource = () => { config: ChartConfig; visible: boolean; onViewport: (range: VisibleRange) => void }

// Add coordinate-bound minor lines through Vela's public layer API. The native
// major grid, axis labels and every indicator keep their existing rendering path.
registerRendererLayer({
  id: GRID_LAYER,
  placement: 'below-data',
  create: () => {
    let canvas: HTMLCanvasElement, context: CanvasRenderingContext2D | null
    let zoneKey = '', offset = 0
    return {
      mount(element) { canvas = element; context = element.getContext('2d') },
      render({ coords, bounds, scale, data }) {
        if (!context || !canvas) return
        context.setTransform(1, 0, 0, 1, 0, 0)
        context.clearRect(0, 0, canvas.width, canvas.height)
        const source = typeof data === 'function' ? (data as GridSource)() : null
        if (!source || coords.barCount < 1) return
        // The native viewport event clips to loaded candles, and disappears
        // entirely when a fast pan leaves them offscreen. Keep the full range
        // available to history loading, including the empty space to the left.
        source.onViewport(coords.visibleTimeRange())
        if (!source.visible || bounds.height <= 0 || coords.barCount < 2) return
        const { config } = source, { from, to } = coords.visibleTimeRange()
        if (!(to > from)) return
        const midpoint = (from + to) / 2
        const nextZoneKey = `${config.timeScale.timezone}:${Math.floor(midpoint / DAY)}`
        if (nextZoneKey !== zoneKey) {
          zoneKey = nextZoneKey
          const part = new Intl.DateTimeFormat('en', { timeZone: config.timeScale.timezone,
            timeZoneName: 'longOffset' }).formatToParts(midpoint).find(item => item.type === 'timeZoneName')?.value
          const match = part?.match(/GMT([+-])(\d{1,2}):(\d{2})/)
          offset = match ? (match[1] === '-' ? -1 : 1) * (Number(match[2]) * HOUR + Number(match[3]) * MINUTE) : 0
        }
        context.save()
        context.scale(coords.dpr, coords.dpr)
        context.beginPath()
        context.rect(0, 0, coords.width, coords.height)
        context.clip()
        context.lineWidth = 1
        context.globalAlpha = 0.35
        const pixel = (value: number) => Math.round(value) + 0.5
        const target = (to - from) / Math.max(2, coords.width / GRID_SPACING)
        const timeStep = target > TIME_STEPS[TIME_STEPS.length - 1] ? gridStep(to - from, coords.width / GRID_SPACING)
          : TIME_STEPS.reduce((best, value) => Math.abs(Math.log(value / target)) < Math.abs(Math.log(best / target)) ? value : best)
        // Use the actual projected time spacing for both axes, then snap price
        // steps to readable values. The axes remain meaningful, not locked 1:1.
        const timeSpacing = Math.abs(coords.timeToX(midpoint + timeStep) - coords.timeToX(midpoint))
        const gridSpacing = Number.isFinite(timeSpacing) && timeSpacing > 0
          ? Math.max(48, Math.min(100, timeSpacing)) : GRID_SPACING
        if (config.grid.vertLines.visible) {
          context.strokeStyle = config.grid.vertLines.color
          context.beginPath()
          let lastX = -Infinity
          for (let t = Math.ceil((from + offset) / timeStep) * timeStep - offset, count = 0; t <= to && count < 256; t += timeStep, count++) {
            const x = pixel(coords.timeToX(t))
            if (x < 0 || x > coords.width || x - lastX < 32) continue
            context.moveTo(x, 0); context.lineTo(x, coords.height)
            lastX = x
          }
          context.stroke()
        }
        if (config.grid.horzLines.visible && scale.max > scale.min) {
          // Logarithmic coordinates use equal log steps; each line is still projected
          // through the chart's own transform, including an inverted price axis.
          const logarithmic = scale.log && scale.min > 0
          const lower = logarithmic ? Math.log10(scale.min) : scale.min
          const upper = logarithmic ? Math.log10(scale.max) : scale.max
          const step = gridStep(upper - lower, bounds.height / gridSpacing)
          context.strokeStyle = config.grid.horzLines.color
          context.beginPath()
          for (let value = Math.ceil(lower / step) * step, count = 0; value <= upper && count < 256; value += step, count++) {
            const price = logarithmic ? 10 ** value : value
            const y = pixel(coords.priceToY(price, scale, bounds))
            if (y < bounds.top || y > bounds.top + bounds.height) continue
            context.moveTo(0, y); context.lineTo(coords.width, y)
          }
          context.stroke()
        }
        context.restore()
      },
    }
  },
})

export class WorkspaceRenderer extends NativeRenderer {
  private static mounted = new Set<WorkspaceRenderer>()
  static forHost(host: HTMLElement) {
    return [...this.mounted].find(renderer => renderer.chartHost && host.contains(renderer.chartHost))
  }
  readonly priceAlerts: PriceAlertLayerSource = { alerts: [] }
  readonly replayOrders: ReplayLayerSource = { lines: [] }
  setReplayOrders(source: Pick<ReplayLayerSource, 'lines' | 'geometry' | 'markers'>) {
    Object.assign(this.replayOrders, { markers: [], ...source })
    this.setNativeData(REPLAY_ORDER_LAYER, this.replayOrders)
  }
  setPriceAlerts(alerts: PriceAlertLayerSource['alerts']) {
    this.priceAlerts.alerts = alerts
    this.setNativeData(PRICE_ALERT_LAYER, this.priceAlerts)
  }
  priceAtClient(x: number, y: number, clamp = false) { return this.priceAlerts.pointAt?.(x, y, clamp) }
  get latestPrice() { return this.priceBars[this.priceBars.length - 1]?.close }
  private chartHost?: HTMLElement
  private priceBars: readonly OHLCV[] = []
  private framed = false
  private disposeLocale?: () => void
  private disposeIndicatorInteraction?: () => void
  private historyViewport?: (range: VisibleRange) => void
  cursorSurface?: { plot: HTMLElement; canvas: HTMLCanvasElement }
  get hasReadableViewport() { return this.framed }

  onHistoryViewport(listener: (range: VisibleRange) => void) {
    this.historyViewport = listener
    return () => { if (this.historyViewport === listener) this.historyViewport = undefined }
  }

  bindIndicatorInteraction(deps: { enabled: () => boolean; activate: () => void }) {
    this.disposeIndicatorInteraction?.()
    const picking = this.readFeature('opentrading.indicatorPicking') as IndicatorPicking | undefined
    if (!picking || !this.cursorSurface) return
    this.setNativeData(INDICATOR_SELECTION_LAYER, picking)
    this.disposeIndicatorInteraction = installIndicatorInteraction(this.cursorSurface.plot, picking, {
      ...deps, settings: id => this.openIndicatorSettings(id),
      repaint: () => this.setNativeData(INDICATOR_SELECTION_LAYER, picking),
    })
  }

  override mount(container: HTMLElement, theme: VelaTheme) {
    this.chartHost = container
    super.mount(container, theme)
    // Vela 0.7 paints the crosshair and axis chips on the final plot canvas.
    // Keep this DOM bridge here beside the renderer integration, rather than
    // changing the user's saved crosshair colors or width for cursor modes.
    const canvases = container.querySelectorAll('canvas'), canvas = canvases[canvases.length - 1]
    if (canvas?.parentElement) this.cursorSurface = { plot: canvas.parentElement, canvas }
    this.disposeLocale = localizeCanvasDates(container, () => this.applyConfig({}))
    WorkspaceRenderer.mounted.add(this)
    this.priceAlerts.host = container
    this.replayOrders.host = container
    this.setNativeData(REPLAY_ORDER_LAYER, this.replayOrders)
    this.setNativeData(PRICE_ALERT_LAYER, this.priceAlerts)
    this.setNativeData(GRID_LAYER, () => ({ config: this.getConfig(), visible: this.readFeature('gridlines') !== false,
      onViewport: (range: VisibleRange) => this.historyViewport?.(range) }))
  }

  override setBars(bars: OHLCV[], options?: { preserveView?: boolean }) {
    super.setBars(bars, options)
    this.priceBars = bars
    if (!this.framed) this.frameRecentCandles()
  }

  override destroy() {
    this.historyViewport = undefined
    this.disposeIndicatorInteraction?.()
    this.disposeLocale?.()
    WorkspaceRenderer.mounted.delete(this)
    super.destroy()
  }

  frameRecentCandles() {
    if (!this.chartHost) return
    const style = getComputedStyle(this.chartHost)
    const width = this.chartHost.clientWidth - (parseFloat(style.getPropertyValue('--vela-toolbar-gutter')) || 0)
      - (parseFloat(style.getPropertyValue('--vela-scale-gutter')) || 0)
    if (width <= 0) return
    const range = readableCandleRange(this.priceBars, width)
    if (!range) return
    this.framed = true
    this.setVisibleRange(range)
  }
}
