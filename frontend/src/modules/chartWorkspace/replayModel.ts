import type { ChartBar } from './generatedContracts'

export const MINUTE = 60_000
export function replayDateInput(time: number, timeZone: string) {
  const parts = new Intl.DateTimeFormat('sv-SE', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(time)
  const value = (name: string) => parts.find(part => part.type === name)?.value
  return `${value('year')}-${value('month')}-${value('day')}T${value('hour')}:${value('minute')}`
}
export function replayDateTime(value: string, timeZone: string) {
  const wall = Date.parse(value + ':00Z')
  if (!Number.isFinite(wall)) return NaN
  let time = wall
  for (let i = 0; i < 3; i++) {
    const shown = Date.parse(replayDateInput(time, timeZone) + ':00Z')
    time += wall - shown
  }
  return replayDateInput(time, timeZone) === value ? time : NaN
}
export type Side = 1 | -1
export type OrderKind = 'market' | 'limit'
export type ExitTarget = `exit:${number}`
export type OrderTarget = 'entry' | ExitTarget
export type ExitKind = 'tp' | 'sl'
export interface ReplayExit {
  target: ExitTarget; kind: ExitKind; price: number; since: number
  /** Undefined follows the entire remaining position; a number closes that many units. */
  quantity?: number
}
export interface ReplayOrder {
  side: Side; kind: OrderKind; price: number; quantity: number; createdAt: number
  exits: ReplayExit[]
}
export interface ReplayPosition {
  side: Side; price: number; quantity: number; enteredAt: number
  exits: ReplayExit[]
}
export interface ReplayTrade {
  side: Side; quantity: number; entry: number; exit: number; enteredAt: number; exitedAt: number
  profit: number; reason: 'manual' | 'tp' | 'sl'
}

export function periodStart(time: number, timeframe: string, offset = 0): number {
  if (timeframe === '1M') { const d = new Date(time); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) }
  const size = periodDuration(timeframe), origin = timeframe === '1w' ? 4 * 86_400_000 : 0
  return Math.floor((time - origin - offset) / size) * size + origin + offset
}
export function periodDuration(timeframe: string): number {
  const match = /^(\d+)([mhdw])$/.exec(timeframe)
  if (!match) throw new Error('Unsupported replay interval: ' + timeframe)
  return Number(match[1]) * ({ m: MINUTE, h: 60 * MINUTE, d: 1440 * MINUTE, w: 10080 * MINUTE }[match[2]!]!)
}
export function periodEnd(time: number, timeframe: string, offset = 0): number {
  const start = periodStart(time, timeframe, offset)
  if (timeframe === '1M') { const d = new Date(start); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) }
  return start + periodDuration(timeframe)
}
export function aggregateMinute(previous: ChartBar | undefined, minute: ChartBar, timeframe: string, offset = 0): ChartBar {
  const time = periodStart(minute.time, timeframe, offset), closeTime = periodEnd(minute.time, timeframe, offset)
  const same = previous?.time === time
  return { time, closeTime, open: same ? previous!.open : minute.open,
    high: same ? Math.max(previous!.high, minute.high) : minute.high,
    low: same ? Math.min(previous!.low, minute.low) : minute.low,
    close: minute.close, volume: (same ? previous!.volume ?? 0 : 0) + (minute.volume ?? 0),
    closed: minute.closeTime >= closeTime }
}

/** Schedules one source candle per beat. It never produces a historical timestamp. */
export class ReplayPacer {
  private anchor = 0
  private progress = 0
  speed = 1
  running = false
  private earned(tick: number) { return Math.min(1, this.progress + (this.running ? Math.max(0, tick - this.anchor) * this.speed / 1000 : 0)) }
  delay(tick: number) { return (1 - this.earned(tick)) * 1000 / this.speed }
  reset(tick: number) { this.progress = 0; this.anchor = tick }
  play(tick: number) { this.anchor = tick; this.running = true }
  pause(tick: number) { this.progress = this.earned(tick); this.anchor = tick; this.running = false }
  setSpeed(speed: number, tick: number) {
    if (!Number.isFinite(speed) || speed <= 0) throw new Error('Invalid replay speed')
    this.progress = this.earned(tick); this.anchor = tick; this.speed = speed
  }
}

/** A single simulated order/position. No exchange account or server session. */
export class ReplayAccount {
  draft?: ReplayOrder
  pending?: ReplayOrder
  position?: ReplayPosition
  trades: ReplayTrade[] = []
  price = 0
  realized = 0
  private sequence = 0
  get order() { return this.position ?? this.pending ?? this.draft }
  get unrealized() { const p = this.position; return p ? (this.price - p.price) * p.side * p.quantity : 0 }
  reset(price = 0) { this.draft = this.pending = this.position = undefined; this.trades = []; this.price = price; this.realized = 0 }
  prepare(side: Side, kind: OrderKind, price: number, quantity: number, time: number) {
    if (this.pending || this.position || !Number.isFinite(price) || price <= 0 || !Number.isFinite(quantity) || quantity <= 0) return false
    this.draft = { side, kind, price: kind === 'market' ? this.price : price, quantity, createdAt: time, exits: [] }
    return true
  }
  place(side: Side, kind: OrderKind, price: number, quantity: number, time: number) {
    if (this.draft || !this.prepare(side, kind, price, quantity, time)) return false
    if (this.submit(time)) return true
    this.draft = undefined
    return false
  }
  private enter(order: ReplayOrder, price: number, time: number) {
    this.position = { side: order.side, quantity: order.quantity, price, enteredAt: time,
      exits: order.exits.map(exit => ({ ...exit, since: time })) }
    this.pending = undefined
  }
  submit(time: number) {
    const order = this.draft
    if (!order || this.position || this.pending || !(this.price > 0) || !Number.isFinite(order.quantity) || order.quantity <= 0) return false
    if (order.kind === 'market') order.price = this.price
    if (order.exits.some(exit => !this.validExit(exit.kind, exit.price, order.price, order.side) ||
        !this.validQuantity(exit.quantity, order.quantity))) return false
    order.createdAt = time
    if (order.kind === 'market' || (this.price - order.price) * order.side <= 0) this.enter(order, this.price, time)
    else this.pending = { ...order }
    this.draft = undefined
    return true
  }
  move(target: OrderTarget, price: number, time: number) {
    if (!Number.isFinite(price) || price <= 0) return false
    const order = this.order
    if (!order) return false
    if (target === 'entry') {
      if (this.position || !('kind' in order) || order.kind !== 'limit') return false
      if (order.exits.some(exit => !this.validExit(exit.kind, exit.price, price, order.side))) return false
      order.price = price; order.createdAt = time
      if (this.pending && (this.price - price) * order.side <= 0) this.enter(order, this.price, time)
    } else {
      const exit = order.exits.find(exit => exit.target === target)
      return !!exit && this.updateExit(target, price, exit.quantity, time)
    }
    return true
  }
  private reference() { const order = this.order; return this.position || this.draft?.kind === 'market' ? this.price : order?.price ?? this.price }
  private validExit(kind: ExitKind, price: number, reference: number, side: Side) {
    return Number.isFinite(price) && price > 0 && (price - reference) * side * (kind === 'tp' ? 1 : -1) > 0
  }
  private validQuantity(quantity: number | undefined, available: number) {
    return quantity === undefined || (Number.isFinite(quantity) && quantity > 0 && quantity <= available)
  }
  exitKind(price: number): ExitKind | undefined {
    const order = this.order
    if (!order || !Number.isFinite(price) || price <= 0) return
    const delta = (price - this.reference()) * order.side
    return delta > 0 ? 'tp' : delta < 0 ? 'sl' : undefined
  }
  addExit(price: number, time: number, quantity?: number): ExitTarget | undefined {
    const order = this.order, kind = this.exitKind(price)
    if (!order || !kind || !this.validQuantity(quantity, order.quantity)) return
    const protection = quantity === undefined ? order.exits.find(exit => exit.kind === kind && exit.quantity === undefined) : undefined
    if (protection) { this.updateExit(protection.target, price, undefined, time); return protection.target }
    const target: ExitTarget = `exit:${++this.sequence}`
    order.exits.push({ target, kind, price, quantity, since: time })
    return target
  }
  updateExit(target: ExitTarget, price: number, quantity: number | undefined, time: number) {
    const order = this.order, exit = order?.exits.find(exit => exit.target === target)
    if (!order || !exit || !this.validExit(exit.kind, price, this.reference(), order.side) || !this.validQuantity(quantity, order.quantity)) return false
    if (exit.price !== price || exit.quantity !== quantity) exit.since = time
    exit.price = price; exit.quantity = quantity
    return true
  }
  cancel(target: OrderTarget) {
    if (target === 'entry') { this.draft = this.pending = undefined; return }
    const order = this.order
    if (order) order.exits = order.exits.filter(exit => exit.target !== target)
  }
  close(time: number, reason: ReplayTrade['reason'] = 'manual', price = this.price, quantity = this.position?.quantity ?? 0) {
    const p = this.position
    if (!p || !Number.isFinite(quantity) || quantity <= 0) return
    quantity = Math.min(quantity, p.quantity)
    const profit = (price - p.price) * quantity * p.side
    this.trades.push({ side: p.side, quantity, entry: p.price, exit: price,
      enteredAt: p.enteredAt, exitedAt: time, profit, reason })
    this.realized += profit
    const remaining = Number((p.quantity - quantity).toPrecision(12))
    if (remaining <= p.quantity * 1e-12) this.position = undefined
    else {
      p.quantity = remaining
      for (const exit of p.exits) if (exit.quantity !== undefined) exit.quantity = Math.min(exit.quantity, remaining)
    }
  }
  /** A live update only reveals this quote, never the earlier wick of its candle. */
  quote(price: number, time: number) {
    if (!Number.isFinite(price) || price <= 0) return
    this.consume({ time, closeTime: time, open: price, high: price, low: price, close: price, volume: 0, closed: false })
  }
  consume(bar: ChartBar) {
    this.price = bar.close
    const pending = this.pending
    let enteredHere = false
    let enteredWithFullMinute = false
    if (pending) {
      // A newly changed order cannot use earlier, unseen parts of this minute.
      const full = pending.createdAt <= bar.time
      const touched = (pending.side === 1 ? (full ? bar.low : bar.close) <= pending.price : (full ? bar.high : bar.close) >= pending.price)
      if (touched) {
        const price = full ? (pending.side === 1 ? Math.min(bar.open, pending.price) : Math.max(bar.open, pending.price)) : bar.close
        this.enter(pending, price, bar.closeTime)
        enteredHere = true
        enteredWithFullMinute = full
      }
    }
    const p = this.position
    if (!p) return
    // Same-minute ambiguity: stops first, then targets; within each side, nearest level first.
    const exits = [...p.exits].sort((a, b) => a.kind !== b.kind ? (a.kind === 'sl' ? -1 : 1) :
      (a.price - b.price) * p.side * (a.kind === 'sl' ? -1 : 1))
    for (const exit of exits) {
      if (!this.position) break
      const full = exit.kind === 'sl' ? enteredWithFullMinute || exit.since <= bar.time : !enteredHere && exit.since <= bar.time
      const stop = exit.kind === 'sl', upwards = (p.side === 1) !== stop
      const observed = full ? (upwards ? bar.high : bar.low) : bar.close
      if (upwards ? observed < exit.price : observed > exit.price) continue
      const price = full ? (upwards ? Math.max(bar.open, exit.price) : Math.min(bar.open, exit.price)) : bar.close
      p.exits = p.exits.filter(item => item.target !== exit.target)
      this.close(bar.closeTime, exit.kind, price, exit.quantity ?? p.quantity)
    }
  }
}
