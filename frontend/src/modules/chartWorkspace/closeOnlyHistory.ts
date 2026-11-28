import { registerRendererLayer } from '@luxalgo/vela/plugin'
import type { ChartBar } from './api'
import { cw } from './locale'

// Candle backends skip bars with no range. Mark the actual historic closes
// without fabricating candle bodies or changing the chart's selected style.
registerRendererLayer({
  id: 'opentrading-close-only-history', placement: 'above-data',
  create: () => {
    let canvas: HTMLCanvasElement, context: CanvasRenderingContext2D | null
    return {
      mount(element) { canvas = element; context = element.getContext('2d') },
      render({ bars, coords, bounds, scale, theme, priceStyle }) {
        if (!context) return
        const ctx = context
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height)
        if (['line', 'area', 'baseline'].includes(priceStyle)) return
        const range = coords.visibleLogicalRange()
        const first = Math.max(0, Math.floor(range.from)), last = Math.min(bars.length - 1, Math.ceil(range.to))
        let count = 0
        ctx.save(); ctx.scale(coords.dpr, coords.dpr)
        ctx.beginPath(); ctx.rect(0, bounds.top, coords.width, bounds.height); ctx.clip()
        ctx.fillStyle = theme.textColor; ctx.globalAlpha = .7
        for (let i = first; i <= last; i++) {
          const bar = bars[i] as ChartBar | undefined
          if (!bar?.closeOnly) continue
          const x = coords.logicalToX(i), y = coords.priceToY(bar.close, scale, bounds)
          ctx.beginPath(); ctx.arc(x, y, Math.min(2, Math.max(1, coords.pxPerBar() * .2)), 0, Math.PI * 2); ctx.fill()
          count++
        }
        if (count) {
          ctx.globalAlpha = 1; ctx.font = '12px Arial, "Microsoft YaHei", sans-serif'
          ctx.textAlign = 'right'
          ctx.fillText(cw('closeOnlyHistory'), coords.width - 12, bounds.top + bounds.height - 12)
        }
        ctx.restore()
      },
    }
  },
})
