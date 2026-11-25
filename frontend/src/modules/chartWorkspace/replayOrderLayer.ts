import { registerRendererLayer } from '@luxalgo/vela/plugin'
import type { OrderTarget } from './replayModel'

export const REPLAY_ORDER_LAYER = 'opentrading-replay-orders'
export type ReplayLine = { target: OrderTarget; price: number; label: string; color: string; draggable: boolean; quantity?: number }
export type ReplayGeometry = { right: number; top: number; bottom: number; lines: (ReplayLine & { y: number })[] }
export interface ReplayLayerSource {
  host?: HTMLElement
  lines: ReplayLine[]
  markers?: { time: number; price: number; side: 1 | -1; color: string }[]
  geometry?: (value: ReplayGeometry) => void
  pointAt?: (x: number, y: number) => { price: number; time: number } | undefined
  hitAt?: (x: number, y: number) => OrderTarget | undefined
}

registerRendererLayer({
  id: REPLAY_ORDER_LAYER, placement: 'above-data',
  create: () => {
    let canvas: HTMLCanvasElement, context: CanvasRenderingContext2D | null
    return {
      mount(element) { canvas = element; context = element.getContext('2d') },
      render({ data, coords, bounds, scale }) {
        if (!context) return
        const ctx = context
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height)
        const source = data as ReplayLayerSource | undefined
        const host = source?.host?.getBoundingClientRect()
        if (!source || !host) return
        const rect = canvas.getBoundingClientRect(), top = rect.top - host.top
        source.pointAt = (x, y) => {
          const localY = y - rect.top, localX = x - rect.left
          if (localY < bounds.top || localY > bounds.top + bounds.height || x < host.left || x > host.right || bounds.height <= 0) return
          const price = coords.yToPrice(localY, scale, bounds)
          const time = coords.logicalToTime(Math.round(coords.xToLogical(localX)))
          return Number.isFinite(price) && price > 0 && Number.isFinite(time) ? { price, time } : undefined
        }
        const lines = source.lines.map(line => ({ ...line, y: top + coords.priceToY(line.price, scale, bounds) }))
        source.hitAt = (x, y) => {
          if (x < rect.left || x > rect.left + coords.width) return
          return lines.filter(line => line.draggable && Math.abs(y - host.top - line.y) <= 5)
            .sort((a, b) => Math.abs(y - host.top - a.y) - Math.abs(y - host.top - b.y))[0]?.target
        }
        source.geometry?.({ right: rect.left - host.left + coords.width, top: top + bounds.top, bottom: top + bounds.top + bounds.height, lines })
        ctx.save(); ctx.scale(coords.dpr, coords.dpr)
        ctx.beginPath(); ctx.rect(0, bounds.top, coords.width, bounds.height); ctx.clip()
        for (const line of lines) {
          const y = line.y - top
          ctx.strokeStyle = line.color; ctx.lineWidth = 1; ctx.setLineDash(line.target === 'entry' ? [5, 4] : [3, 3])
          ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(coords.width, y); ctx.stroke()
        }
        ctx.setLineDash([])
        for (const marker of source.markers ?? []) {
          const x = coords.timeToX(marker.time), y = coords.priceToY(marker.price, scale, bounds)
          if (x < 0 || x > coords.width) continue
          ctx.fillStyle = marker.color
          ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 5, y + marker.side * 9); ctx.lineTo(x + 5, y + marker.side * 9); ctx.closePath(); ctx.fill()
        }
        ctx.restore()
      },
    }
  },
})
