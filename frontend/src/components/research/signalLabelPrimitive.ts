import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, SeriesAttachedParameter, Time, UTCTimestamp } from 'lightweight-charts'
import type { TradingViewDataPoint, TradingViewStrategyMarker } from '../tradingViewChartPresentation'

export class SignalLabelPrimitive implements ISeriesPrimitive<Time> {
  private api: SeriesAttachedParameter<Time> | null = null
  private points: { time: UTCTimestamp; price: number; short: boolean; label: string; color: string; stack: number }[] = []
  private renderer: IPrimitivePaneRenderer = {
    draw: target => target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      if (!this.api) return
      ctx.save(); ctx.font = '14px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
      for (const p of this.points) {
        const x = this.api.chart.timeScale().timeToCoordinate(p.time), y = this.api.series.priceToCoordinate(p.price)
        if (x == null || y == null || x < -40 || x > mediaSize.width + 40) continue
        const width = ctx.measureText(p.label).width + 8, height = 22
        const tip = y + (p.short ? -1 : 1) * (4 + p.stack * 30), top = p.short ? tip - height - 5 : tip + 5
        ctx.fillStyle = p.color
        ctx.beginPath(); ctx.roundRect(x-width/2, top, width, height, 2); ctx.fill()
        ctx.beginPath(); ctx.moveTo(x,tip); ctx.lineTo(x-4,p.short ? top+height : top); ctx.lineTo(x+4,p.short ? top+height : top); ctx.closePath(); ctx.fill()
        ctx.fillStyle = '#ffffff'; ctx.fillText(p.label, x, top+height/2)
      }
      ctx.restore()
    }),
  }
  private views: IPrimitivePaneView[] = [{ zOrder: () => 'top', renderer: () => this.renderer }]
  attached(p: SeriesAttachedParameter<Time>) { this.api = p }
  detached() { this.api = null }
  paneViews() { return this.views }
  setData(markers: TradingViewStrategyMarker[], candles: TradingViewDataPoint[]) {
    const byTime = new Map(candles.map(c => [c.time, c]))
    const stacks = new Map<string, number>()
    this.points = markers.flatMap(m => {
      const time = Number(m.time)/1000 as UTCTimestamp, candle = byTime.get(time)
      if (!candle) return []
      const short = m.position === 'aboveBar' || (!m.position && m.kind === 'short_entry')
      const key = `${time}:${short}`, stack = stacks.get(key) ?? 0; stacks.set(key, stack + 1)
      return [{ time, price: short ? candle.high : candle.low, short, stack, color: m.color || (short ? '#4CAF50' : '#F23645'), label: m.label || (short ? '做空' : '做多') }]
    })
    this.api?.requestUpdate()
  }
}
