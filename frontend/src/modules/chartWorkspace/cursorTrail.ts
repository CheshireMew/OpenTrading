type Point = { x: number; y: number }
type Trail = { points: Point[]; ended: number | null }
const HOLD_MS = 900, FADE_MS = 1800

/** Screen-space demonstration marks. These never enter the drawing document. */
export class CursorTrail {
  readonly canvas = document.createElement('canvas')
  private context: CanvasRenderingContext2D | null
  private trails: Trail[] = []
  private current?: Trail
  private frame = 0
  private width = 0
  private height = 0
  private dpr = 1
  private observer: ResizeObserver

  constructor(private plot: HTMLElement, private bounds: () => { left: number; right: number; bottom: number }) {
    this.canvas.className = 'cw-cursor-trail'
    this.canvas.setAttribute('aria-hidden', 'true')
    this.context = this.canvas.getContext('2d')
    plot.appendChild(this.canvas)
    this.observer = new ResizeObserver(() => this.clear())
    this.observer.observe(plot)
  }

  begin(point: Point) {
    this.finish()
    this.current = { points: [point], ended: null }
    this.trails.push(this.current)
    this.trails = this.trails.slice(-40)
    this.schedule()
  }

  move(point: Point) {
    const points = this.current?.points
    if (!points) return
    const previous = points[points.length - 1]!
    if (Math.hypot(point.x - previous.x, point.y - previous.y) >= 1.5) points.push(point)
    // A long uninterrupted gesture still has bounded memory.
    if (points.length > 6000) points.splice(1, points.length - 6000)
    this.schedule()
  }

  finish() {
    if (this.current) this.current.ended = performance.now()
    this.current = undefined
    if (this.trails.length) this.schedule()
  }

  clear = () => {
    cancelAnimationFrame(this.frame)
    this.frame = 0
    this.trails = []
    this.current = undefined
    this.context?.clearRect(0, 0, this.canvas.width, this.canvas.height)
  }

  private schedule() { if (!this.frame) this.frame = requestAnimationFrame(this.paint) }

  private paint = (now: number) => {
    this.frame = 0
    const context = this.context
    if (!context) return
    const width = this.plot.clientWidth, height = this.plot.clientHeight, dpr = window.devicePixelRatio || 1
    if (width !== this.width || height !== this.height || dpr !== this.dpr) {
      this.width = width; this.height = height; this.dpr = dpr
      this.canvas.width = Math.round(width * dpr)
      this.canvas.height = Math.round(height * dpr)
    }
    context.setTransform(1, 0, 0, 1, 0, 0)
    context.clearRect(0, 0, this.canvas.width, this.canvas.height)
    context.save()
    context.scale(dpr, dpr)
    const bounds = this.bounds()
    context.beginPath()
    context.rect(bounds.left, 0, Math.max(0, bounds.right - bounds.left), bounds.bottom)
    context.clip()
    context.lineWidth = 5
    context.lineCap = 'round'
    context.lineJoin = 'round'
    context.strokeStyle = '#f5b832'
    context.fillStyle = '#f5b832'
    this.trails = this.trails.filter(trail => trail.ended === null || now - trail.ended < HOLD_MS + FADE_MS)
    for (const trail of this.trails) {
      context.globalAlpha = trail.ended === null ? .85 : .85 * Math.max(0, 1 - Math.max(0, now - trail.ended - HOLD_MS) / FADE_MS)
      const first = trail.points[0]!
      context.beginPath()
      if (trail.points.length === 1) {
        context.arc(first.x, first.y, 5, 0, Math.PI * 2)
        context.fill()
      } else {
        context.moveTo(first.x, first.y)
        for (const point of trail.points.slice(1)) context.lineTo(point.x, point.y)
        context.stroke()
      }
    }
    context.restore()
    // No animation loop is needed while a stationary stroke is held down.
    if (this.trails.some(trail => trail.ended !== null)) this.schedule()
  }

  dispose() { this.clear(); this.observer.disconnect(); this.canvas.remove() }
}
