import { registerRendererLayer } from '@luxalgo/vela/plugin'

export const INDICATOR_SELECTION_LAYER = 'opentrading-indicator-selection'
type Point = { x: number; y: number; color: string }
export type IndicatorGeometry = {
  id: string; kind: string; points: (Point | null)[]; width: number
  top: number; bottom: number; right: number; base: number; halfWidth: number
}
export type IndicatorPicking = {
  geometry: (id?: string) => IndicatorGeometry[]
  selected: () => string | null
  select: (id: string | null) => void
  menu: (id: string, x: number, y: number) => void
  blocked: (x: number, y: number) => boolean
}

function segmentDistance(x: number, y: number, a: Point, b: Point) {
  const dx = b.x - a.x, dy = b.y - a.y, length = dx * dx + dy * dy
  const t = length ? Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / length)) : 0
  return Math.hypot(x - a.x - t * dx, y - a.y - t * dy)
}

export function pickIndicator(shapes: IndicatorGeometry[], x: number, y: number, tolerance = 6) {
  let selected: string | null = null, nearest = tolerance
  for (const shape of [...shapes].reverse()) {
    if (x < 0 || x > shape.right || y < shape.top || y >= shape.bottom) continue
    const columns = shape.kind === 'histogram' || shape.kind === 'columns'
    let previous: Point | null = null
    for (const point of shape.points) {
      if (!point || point.color === 'transparent') { previous = null; continue }
      let distance = Infinity
      if (columns) {
        const left = point.x - shape.halfWidth, right = point.x + shape.halfWidth
        const top = Math.min(shape.base, point.y), bottom = Math.max(shape.base, point.y)
        distance = Math.hypot(Math.max(left - x, 0, x - right), Math.max(top - y, 0, y - bottom))
      } else if (shape.kind === 'circles' || shape.kind === 'cross') {
        distance = Math.hypot(x - point.x, y - point.y)
      } else if (previous) {
        if (shape.kind === 'step') {
          const corner = { ...point, y: previous.y }
          distance = Math.min(segmentDistance(x, y, previous, corner), segmentDistance(x, y, corner, point))
        } else distance = segmentDistance(x, y, previous, point)
      }
      if (distance <= tolerance + shape.width / 2 && (selected === null || distance < nearest)) {
        nearest = distance; selected = shape.id
      }
      previous = point
    }
  }
  return selected
}

registerRendererLayer({
  id: INDICATOR_SELECTION_LAYER, placement: 'above-data', repaintOnCursor: true,
  create: () => {
    let canvas: HTMLCanvasElement, ctx: CanvasRenderingContext2D | null
    return {
      mount(element) { canvas = element; ctx = element.getContext('2d') },
      render({ data, coords, theme }) {
        if (!ctx) return
        ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height)
        const picking = data as IndicatorPicking | undefined, selected = picking?.selected()
        if (!picking || !selected) return
        ctx.save(); ctx.scale(coords.dpr, coords.dpr)
        for (const shape of picking.geometry(selected)) {
          ctx.save(); ctx.beginPath(); ctx.rect(0, shape.top, shape.right, shape.bottom - shape.top); ctx.clip()
          let lastX = -Infinity
          for (const point of shape.points) {
            if (!point || point.x < 0 || point.x > shape.right || point.y < shape.top || point.y >= shape.bottom || point.x - lastX < 65) continue
            ctx.beginPath(); ctx.arc(point.x, point.y, 3.5, 0, Math.PI * 2)
            ctx.fillStyle = theme.background; ctx.fill(); ctx.lineWidth = 1.5
            ctx.strokeStyle = point.color; ctx.stroke(); lastX = point.x
          }
          ctx.restore()
        }
        ctx.restore()
      },
    }
  },
})

export function installIndicatorInteraction(plot: HTMLElement, picking: IndicatorPicking, deps: {
  enabled: () => boolean; activate: () => void; settings: (id: string) => void; repaint: () => void
}) {
  let down: { x: number; y: number; pointer: number; moved: boolean; enabled: boolean } | undefined
  let lastClickBlocked = false
  const hit = (event: MouseEvent) => {
    if (!deps.enabled() || !(event.target instanceof HTMLCanvasElement)) return null
    const rect = event.target.getBoundingClientRect()
    const x = event.clientX - rect.left, y = event.clientY - rect.top
    return picking.blocked(x, y) ? null : pickIndicator(picking.geometry(), x, y)
  }
  const pointerDown = (event: PointerEvent) => {
    down = event.button === 0 ? { x: event.clientX, y: event.clientY, pointer: event.pointerId, moved: false, enabled: deps.enabled() } : undefined
  }
  const pointerMove = (event: PointerEvent) => {
    if (down && event.pointerId === down.pointer && Math.hypot(event.clientX - down.x, event.clientY - down.y) > 4) down.moved = true
  }
  const hover = (event: PointerEvent) => {
    if (!(event.target instanceof HTMLCanvasElement)) return
    if (!event.buttons && hit(event)) {
      event.target.style.cursor = 'pointer'
      delete plot.dataset.cwPointer
    }
  }
  const click = (event: MouseEvent) => {
    lastClickBlocked = !!down && (!down.enabled || down.moved)
    down = undefined
    if (event.button !== 0 || lastClickBlocked || !deps.enabled()) return
    const id = hit(event)
    if (id) {
      deps.activate(); picking.select(id)
      // The native document click would otherwise immediately clear its legend selection.
      event.stopPropagation()
    } else if (event.target instanceof HTMLCanvasElement) picking.select(null)
    deps.repaint()
  }
  const doubleClick = (event: MouseEvent) => {
    if (lastClickBlocked) return
    const id = hit(event)
    if (!id || event.button !== 0) return
    event.preventDefault(); event.stopImmediatePropagation()
    deps.activate(); picking.select(id); deps.settings(id); deps.repaint()
  }
  const contextMenu = (event: MouseEvent) => {
    const id = hit(event)
    if (!id) return
    event.preventDefault(); event.stopImmediatePropagation()
    deps.activate(); picking.select(id); picking.menu(id, event.clientX, event.clientY); deps.repaint()
  }
  const cancel = () => { down = undefined }
  const keydown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') { picking.select(null); deps.repaint() }
  }
  plot.addEventListener('pointerdown', pointerDown, true)
  plot.addEventListener('pointermove', pointerMove, true)
  plot.addEventListener('pointermove', hover)
  plot.addEventListener('pointercancel', cancel, true)
  plot.addEventListener('click', click, true)
  plot.addEventListener('dblclick', doubleClick, true)
  plot.addEventListener('contextmenu', contextMenu, true)
  plot.addEventListener('keydown', keydown)
  return () => {
    plot.removeEventListener('pointerdown', pointerDown, true)
    plot.removeEventListener('pointermove', pointerMove, true)
    plot.removeEventListener('pointermove', hover)
    plot.removeEventListener('pointercancel', cancel, true)
    plot.removeEventListener('click', click, true)
    plot.removeEventListener('dblclick', doubleClick, true)
    plot.removeEventListener('contextmenu', contextMenu, true)
    plot.removeEventListener('keydown', keydown)
  }
}
