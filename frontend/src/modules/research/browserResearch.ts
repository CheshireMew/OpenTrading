import { browserRecord, updateBrowserRecord } from '@/modules/personal/browserStore'
import { ApiRequestError } from '@/api/request'
import type { serverResearchApi } from './api'
import type { ResearchAlertResponse, ResearchEventResponse } from './contracts'

type State = { watchlists: any[]; items: any[]; notes: any[]; alerts: any[]; events: any[]; screeners: any[]; screenerRuns: any[] }
const empty = (): State => ({ watchlists: [], items: [], notes: [], alerts: [], events: [], screeners: [], screenerRuns: [] })
const now = () => new Date().toISOString()
const uid = () => crypto.randomUUID()
const read = async () => await browserRecord<State>('research') ?? empty()
const change = <T>(action: (state: State) => T): Promise<T> => {
  let result: T
  return updateBrowserRecord<State>('research', previous => { const state = previous ?? empty(); result = action(state); return state }).then(() => structuredClone(result))
}
const missing = () => new ApiRequestError('Record does not exist in this browser', { status: 404 })
const conflict = () => new ApiRequestError('This record changed in another tab. Reload and retry.', { status: 409 })
function event(state: State, entityType: string, entity: any, kind: string, payload: any = {}) {
  const date = now()
  state.events.unshift({ id: uid(), entityType, entityId: entity.id, symbol: entity.symbol ?? null, kind,
    title: entity.name ?? entity.title ?? entity.symbol ?? '', body: '', payload, occurredAt: date, createdAt: date, acknowledgedAt: null })
}
function create(kind: keyof State, body: any, defaults: (state: State) => any = () => ({})) {
  return change(state => {
    const date = now(), row = { ...defaults(state), ...body, id: uid(), version: 1, createdAt: date, updatedAt: date, archivedAt: null }
    if (kind === 'items' && !state.watchlists.some(item => item.id === row.watchlistId && !item.archivedAt)) throw missing()
    if (kind === 'items' && state.items.some(item => !item.archivedAt && item.watchlistId === row.watchlistId && item.symbol === row.symbol)) throw new ApiRequestError('This symbol is already in the watchlist', { status: 409 })
    state[kind].push(row); event(state, kind, row, kind + '_created'); return row
  })
}
function update(kind: keyof State, id: string, body: any) {
  return change(state => {
    const row = state[kind].find(item => item.id === id)
    if (!row) throw missing()
    if (row.version !== body.expectedVersion) throw conflict()
    const { expectedVersion: _, ...values } = body
    if (kind === 'items' && body.watchlistId && !state.watchlists.some(item => item.id === body.watchlistId && !item.archivedAt)) throw missing()
    Object.assign(row, values, { version: row.version + 1, updatedAt: now() })
    if (kind === 'alerts') row.lastValue = body.configuration?.initialPrice ?? row.lastValue
    event(state, kind, row, kind + '_updated'); return row
  })
}
const archive = (kind: keyof State, id: string, expectedVersion: number, archived: boolean) => update(kind, id, { expectedVersion, archivedAt: archived ? now() : null })
let evaluating: Promise<any> | undefined
function triggers(rule: ResearchAlertResponse, price: number, time: number) {
  const threshold = rule.threshold, previous = rule.lastValue, second = rule.secondaryThreshold
  const above = previous != null && previous < threshold && price >= threshold
  const below = previous != null && previous > threshold && price <= threshold
  const matches = { gt: price > threshold, gte: price >= threshold, lt: price < threshold, lte: price <= threshold,
    crosses: above || below, crosses_above: above, crosses_below: below,
    between: second != null && threshold <= price && price <= second, outside: second != null && (price < threshold || price > second) }
  return matches[rule.operator] && (!rule.lastTriggeredAt || time - Date.parse(rule.lastTriggeredAt) >= rule.cooldownMinutes * 60000)
}
async function evaluateAlerts() {
  const state = await read(), rules: ResearchAlertResponse[] = state.alerts.filter(row => row.enabled && !row.archivedAt)
  const ids = [...new Set(rules.filter(row => row.configuration?.chartSymbolId).map(row => String(row.configuration!.chartSymbolId)))]
  const prices = new Map<string, Record<string, any>>()
  // Public prices are the only values sent across the network; rules and
  // thresholds remain in IndexedDB. Quotes are batched for each evaluation.
  for (let index = 0; index < ids.length; index += 100) {
    const response = await fetch('/api/v1/chart-workspace/quotes?' + new URLSearchParams({ symbols: ids.slice(index, index + 100).join(',') }))
    if (response.ok) for (const quote of await response.json()) if (!quote.error && Number.isFinite(quote.price)) prices.set(quote.id, quote)
  }
  // Research alerts can use normalized market symbols as well as chart IDs.
  const researchRules = rules.filter(row => !row.configuration?.chartSymbolId)
  const symbols = [...new Set(researchRules.map(row => row.symbol.toUpperCase().replace(/\//g, '')))]
  for (let index = 0; index < symbols.length; index += 100) {
    const response = await fetch('/api/v1/binance/market/observations?' + new URLSearchParams({ symbols: symbols.slice(index, index + 100).join(','), extended: String(researchRules.some(row => ['breakout_score', 'oi_change_1h_pct'].includes(row.metric))) }), { signal: AbortSignal.timeout(15_000) })
    if (response.ok) for (const [symbol, observations] of Object.entries(await response.json())) prices.set(symbol, observations as Record<string, any>)
  }
  return change(current => {
    const time = Date.now(), evaluatedAt = new Date(time).toISOString()
    let evaluatedCount = 0, triggeredCount = 0, unavailableCount = 0
    for (const rule of current.alerts.filter(row => row.enabled && !row.archivedAt) as ResearchAlertResponse[]) {
      const quote = prices.get(String(rule.configuration?.chartSymbolId ?? rule.symbol.toUpperCase().replace(/\//g, '')))
      const metric = rule.metric === 'breakout_score' && ['natural', 'momentum'].includes(String(rule.configuration?.scoreKind)) ? String(rule.configuration!.scoreKind) : rule.metric
      const price = rule.configuration?.chartSymbolId ? quote?.price : quote?.[metric]
      if (!Number.isFinite(price)) { unavailableCount++; continue }
      evaluatedCount++
      const triggered = triggers(rule, price, time)
      rule.lastValue = price; rule.lastEvaluatedAt = evaluatedAt
      if (triggered) {
        triggeredCount++; rule.lastTriggeredAt = evaluatedAt
        if (rule.configuration?.once === true) rule.enabled = false
        event(current, 'alert', rule, 'alert_triggered', { value: price, threshold: rule.threshold, notificationChannels: rule.notificationChannels, configuration: rule.configuration })
      }
    }
    return { evaluatedAt, ruleCount: rules.length, evaluatedCount, triggeredCount, unavailableCount }
  })
}
export const evaluateBrowserAlerts = () => evaluating ??= evaluateAlerts().finally(() => { evaluating = undefined })

export function createBrowserResearchApi(server: typeof serverResearchApi): typeof serverResearchApi {
  return {
    async getWorkbench(eventLimit = 100, noteLimit = 200) {
      const state = await read()
      return { ...state, events: state.events.slice(0, eventLimit), notes: state.notes.slice(-noteLimit), unacknowledgedEventCount: state.events.filter(row => !row.acknowledgedAt).length }
    },
    async listEvents(kind = 'alert_triggered', unacknowledgedOnly = true, limit = 100) {
      const rows: ResearchEventResponse[] = (await read()).events.filter(row => (!kind || row.kind === kind) && (!unacknowledgedOnly || !row.acknowledgedAt))
      return { items: rows.slice(0, limit), total: rows.length }
    },
    acknowledgeEvent: (id, body) => change(state => { const row = state.events.find(row => row.id === id); if (!row) throw missing(); row.acknowledgedAt = body.acknowledged === false ? null : now(); return row }),
    createWatchlist: body => create('watchlists', body, state => ({ description: '', position: state.watchlists.length })),
    updateWatchlist: (id, body) => update('watchlists', id, body),
    setWatchlistArchived: (id, body, archived) => archive('watchlists', id, body.expectedVersion, archived),
    createItem: body => create('items', body, state => ({ assetClass: 'crypto', displayName: body.symbol, thesis: '', tags: [], sourceContext: {}, position: state.items.length })),
    updateItem: (id, body) => update('items', id, body),
    setItemArchived: (id, body, archived) => archive('items', id, body.expectedVersion, archived),
    createNote: body => create('notes', body, () => ({ kind: 'thesis', content: '', snapshot: {}, occurredAt: body.occurredAt ?? now() })),
    updateNote: (id, body) => update('notes', id, body),
    setNoteArchived: (id, body, archived) => archive('notes', id, body.expectedVersion, archived),
    createAlert: body => create('alerts', body, () => ({ enabled: true, cooldownMinutes: 60, notificationChannels: ['in_app'], configuration: {}, lastValue: body.configuration?.initialPrice ?? null })),
    updateAlert: (id, body) => update('alerts', id, body),
    setAlertArchived: (id, body, archived) => archive('alerts', id, body.expectedVersion, archived),
    evaluateAlerts: evaluateBrowserAlerts,
    async getAsset(symbol, timeframe = '1h', historyDays = 365, context = {}) {
      const [market, state] = await Promise.all([server.getAsset(symbol, timeframe, historyDays, context), read()])
      return { ...market, watchItems: state.items.filter(row => row.symbol === market.symbol && !row.archivedAt), notes: state.notes.filter(row => row.symbol === market.symbol && !row.archivedAt), alerts: state.alerts.filter(row => row.symbol === market.symbol && !row.archivedAt), events: state.events.filter(row => row.symbol === market.symbol), signals: [] }
    },
    async listScreeners(includeArchived = false) { return { items: (await read()).screeners.filter(row => includeArchived || !row.archivedAt) } },
    createScreener: body => create('screeners', body, () => ({ description: '' })),
    updateScreener: (id, body) => update('screeners', id, body),
    setScreenerArchived: (id, version, archived) => archive('screeners', id, version, archived),
    async runScreener(id, asOf) {
      const state = await read(), row = state.screeners.find(row => row.id === id)
      if (!row) throw missing()
      if (asOf) {
        const historical = state.screenerRuns.filter(row => row.screenerId === id && row.snapshotAsOf <= asOf).sort((a, b) => b.snapshotAsOf.localeCompare(a.snapshotAsOf))[0]
        if (!historical) throw new Error('No saved snapshot exists for this date in this browser')
        return { ...historical, historicalReplay: true }
      }
      const response = await fetch('/api/v1/research/screener-preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(row.filters) })
      if (!response.ok) throw new Error(`Screener unavailable (${response.status})`)
      const result = { ...await response.json(), id: uid(), screenerId: id }
      return change(state => { state.screenerRuns.unshift(result); return result })
    },
    async listScreenerRuns(id, offset = 0, limit = 50) { const rows = (await read()).screenerRuns.filter(row => row.screenerId === id); return { items: rows.slice(offset, offset + limit), total: rows.length } },
    async listSignals(query = {}) { return { items: [], total: 0, offset: query.offset ?? 0, limit: query.limit ?? 100 } },
    async getSignalStats() { return { overall: { key: 'all', total: 0, resolved: 0, targetHits: 0, stopHits: 0, ambiguous: 0, expired: 0, winRatePct: null, averageConfidence: null, averageMfePct: null, averageMaePct: null }, bySource: [], byStrategy: [], confidenceCalibration: [] } },
    async evaluateSignals() { return { evaluatedAt: now(), candidateCount: 0, evaluatedCount: 0, resolvedCount: 0, unavailableCount: 0 } },
    async setSignalArchived() { throw missing() },
  }
}
