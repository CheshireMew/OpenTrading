import { registerRendererLayer } from '@luxalgo/vela/plugin'

export const PRICE_ALERT_LAYER = 'opentrading-price-alerts'
export type PriceAlertLine = { id: string; price: number; label: string }
export type PriceAlertGeometry = { left: number; right: number; top: number; bottom: number; lines: (PriceAlertLine & { y: number })[] }
export interface PriceAlertLayerSource {
  host?: HTMLElement
  alerts: PriceAlertLine[]
  selectedId?: string
  geometry?: (value: PriceAlertGeometry) => void
  hitAt?: (clientX: number, clientY: number) => string | undefined
  pointAt?: (clientX: number, clientY: number, clamp?: boolean) => number | undefined
}

registerRendererLayer({
  id: PRICE_ALERT_LAYER,
  placement: 'above-data',
  create: () => {
    let canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D | null
    return {
      mount(element) { canvas = element; ctx = element.getContext('2d') },
      render({ data, coords, bounds, scale, bars }) {
        if (!ctx) return
        ctx.setTransform(1, 0, 0, 1, 0, 0)
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        const source = data as PriceAlertLayerSource | undefined
        if (!source) return
        const host = source.host?.getBoundingClientRect(), rect = canvas.getBoundingClientRect()
        if (!host) return
        const offset = rect.top - host.top
        const lines = bars.length ? source.alerts.map(alert => ({ ...alert, y: offset + coords.priceToY(alert.price, scale, bounds) }))
          .filter(line => Number.isFinite(line.y) && line.y >= offset + bounds.top && line.y <= offset + bounds.top + bounds.height) : []
        source.geometry?.({ left: rect.left - host.left, right: rect.left - host.left + coords.width,
          top: offset + bounds.top, bottom: offset + bounds.top + bounds.height, lines })
        source.pointAt = (clientX, clientY, clamp = false) => {
          let y = clientY - rect.top
          if (!bars.length || bounds.height <= 0) return
          if (!clamp && (clientX < host.left || clientX > host.right || y < bounds.top || y > bounds.top + bounds.height)) return
          if (clamp) y = Math.max(bounds.top, Math.min(bounds.top + bounds.height, y))
          const price = coords.yToPrice(y, scale, bounds)
          return Number.isFinite(price) && price > 0 ? price : undefined
        }
        source.hitAt = (x, y) => {
          if (x < rect.left || x > rect.left + coords.width) return
          return lines.map(line => ({ id: line.id, distance: Math.abs(y - host.top - line.y) }))
            .filter(line => line.distance <= 7).sort((a, b) => a.distance - b.distance)[0]?.id
        }
        ctx.save(); ctx.scale(coords.dpr, coords.dpr)
        ctx.beginPath(); ctx.rect(0, bounds.top, coords.width, bounds.height); ctx.clip()
        for (const alert of lines) {
          const y = alert.y - offset
          ctx.strokeStyle = '#d99a24'; ctx.lineWidth = alert.id === source.selectedId ? 2 : 1; ctx.setLineDash([6, 4])
          ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(coords.width, y); ctx.stroke()
        }
        ctx.restore()
      },
    }
  },
})
