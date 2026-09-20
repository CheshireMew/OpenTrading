import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, SeriesAttachedParameter, Time, UTCTimestamp } from 'lightweight-charts'

export interface CloudPoint { time: UTCTimestamp; upper: number; lower: number; bullish: boolean }

/** A filled band which follows the chart's real time and price transforms. */
export class TrendCloudPrimitive implements ISeriesPrimitive<Time> {
  private attachedTo: SeriesAttachedParameter<Time> | null = null
  private points: CloudPoint[] = []
  private step = 0
  private renderer: IPrimitivePaneRenderer = {
    draw: target => target.useMediaCoordinateSpace(({ context: ctx }) => {
      const api = this.attachedTo
      if (!api) return
      const coords = this.points.map(p => ({ ...p, x: api.chart.timeScale().timeToCoordinate(p.time),
        top: api.series.priceToCoordinate(p.upper), bottom: api.series.priceToCoordinate(p.lower) }))
      ctx.save()
      for (let i = 1; i < coords.length; i++) {
        const a = coords[i - 1]!, b = coords[i]!
        if (a.x == null || b.x == null || a.top == null || b.top == null || a.bottom == null || b.bottom == null) continue
        // Missing observations must not be joined into a fictitious continuous cloud.
        if (this.step > 0 && Number(b.time) - Number(a.time) !== this.step) continue
        ctx.fillStyle = b.bullish ? 'rgba(76,175,80,0.4)' : 'rgba(242,54,69,0.35)'
        ctx.beginPath(); ctx.moveTo(a.x, a.top); ctx.lineTo(b.x, b.top)
        ctx.lineTo(b.x, b.bottom); ctx.lineTo(a.x, a.bottom); ctx.closePath(); ctx.fill()
      }
      ctx.restore()
    }),
  }
  private views: IPrimitivePaneView[] = [{ zOrder: () => 'bottom', renderer: () => this.renderer }]
  attached(p: SeriesAttachedParameter<Time>) { this.attachedTo = p }
  detached() { this.attachedTo = null }
  paneViews() { return this.views }
  setData(points: CloudPoint[], step: number) { this.points = points; this.step = step; this.attachedTo?.requestUpdate() }
}
