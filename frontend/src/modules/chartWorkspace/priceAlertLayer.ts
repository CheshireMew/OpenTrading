import { registerRendererLayer } from '@luxalgo/vela/plugin'

export const PRICE_ALERT_LAYER = 'opentrading-price-alerts'
export interface PriceAlertLayerSource {
  host?: HTMLElement
  alerts: { id: string; price: number; label: string }[]
  pointAt?: (clientX: number, clientY: number) => number | undefined
}

registerRendererLayer({
  id: PRICE_ALERT_LAYER,
  placement: 'above-data',
  create: () => {
    let canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D | null
    return {
      mount(element) { canvas = element; ctx = element.getContext('2d') },
      render({ data, coords, bounds, scale, theme, bars }) {
        if (!ctx) return
        ctx.setTransform(1, 0, 0, 1, 0, 0)
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        const source = data as PriceAlertLayerSource | undefined
        if (!source) return
        source.pointAt = (clientX, clientY) => {
          const host = source.host?.getBoundingClientRect(), rect = canvas.getBoundingClientRect()
          const y = clientY - rect.top
          if (!host || !bars.length || bounds.height <= 0 || clientX < host.left || clientX > host.right || y < bounds.top || y > bounds.top + bounds.height) return
          const price = coords.yToPrice(y, scale, bounds)
          return Number.isFinite(price) && price > 0 ? price : undefined
        }
        ctx.save(); ctx.scale(coords.dpr, coords.dpr)
        ctx.beginPath(); ctx.rect(0, bounds.top, coords.width, bounds.height); ctx.clip()
        ctx.font = '12px Arial, "Microsoft YaHei", sans-serif'
        ctx.textBaseline = 'middle'
        for (const alert of source.alerts) {
          const y = coords.priceToY(alert.price, scale, bounds)
          if (y < bounds.top || y > bounds.top + bounds.height) continue
          ctx.strokeStyle = '#d99a24'; ctx.lineWidth = 1; ctx.setLineDash([6, 4])
          ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(coords.width, y); ctx.stroke()
          ctx.setLineDash([])
          const width = ctx.measureText(alert.label).width + 16
          ctx.fillStyle = theme.background; ctx.fillRect(coords.width - width, y - 10, width, 20)
          ctx.fillStyle = '#d99a24'; ctx.fillText(alert.label, coords.width - width + 8, y)
        }
        ctx.restore()
      },
    }
  },
})
