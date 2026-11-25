import { ApiRequestError } from '@/api/request'
import type { serverResearchApi } from './api'
import type { ResearchAlertResponse } from './contracts'
import { idbValue } from '@/modules/personal/browserDatabase'
import { browserJson } from '@/modules/personal/browserRequest'
import { researchTransaction, researchGet, researchPut, researchAll, researchPage, researchObjectStore, researchCreate, researchUpdate, researchSetArchived, researchRemove, researchEvent, prefixRange } from '@/modules/personal/browserResearchStore'
import { finishedAlert, missingRecord, revisionConflict, type ResearchKind } from '@/modules/personal/researchSchema'

const now = () => new Date().toISOString()
const archive = (kind: ResearchKind, id: string, expectedVersion: number, archived: boolean) => researchSetArchived(kind, id, expectedVersion, archived)

export function alertTriggers(rule: ResearchAlertResponse, price: number, time: number) {
  const threshold = rule.threshold, previous = rule.lastValue, second = rule.secondaryThreshold
  const above = previous != null && previous < threshold && price >= threshold
  const below = previous != null && previous > threshold && price <= threshold
  const matches = { gt: price > threshold, gte: price >= threshold, lt: price < threshold, lte: price <= threshold,
    crosses: above || below, crosses_above: above, crosses_below: below,
    between: second != null && threshold <= price && price <= second, outside: second != null && (price < threshold || price > second) }
  return matches[rule.operator] && (!rule.lastTriggeredAt || time - Date.parse(rule.lastTriggeredAt) >= rule.cooldownMinutes * 60000)
}
async function evaluateAlerts(signal?: AbortSignal) {
  const started = Date.now()
  const rules = await researchTransaction('readonly', tx => researchAll(tx, 'alerts', 'enabled', 1))
  if (!rules.length) return { evaluatedAt: now(), ruleCount: 0, evaluatedCount: 0, triggeredCount: 0, unavailableCount: 0 }
  const ids = [...new Set(rules.filter(row => row.configuration?.chartSymbolId).map(row => String(row.configuration!.chartSymbolId)))]
  const prices = new Map<string, Record<string, any>>()
  for (let index = 0; index < ids.length; index += 100) {
    const quotes = await browserJson<Record<string, any>[]>('/api/v1/chart-workspace/quotes?' + new URLSearchParams({ symbols: ids.slice(index, index + 100).join(',') }), {}, 15000, signal)
    for (const quote of quotes) if (!quote.error && Number.isFinite(quote.price)) prices.set(quote.id, quote)
  }
  const researchRules = rules.filter(row => !row.configuration?.chartSymbolId)
  const symbols = [...new Set(researchRules.map(row => row.symbol.toUpperCase().replace(/\//g, '')))]
  for (let index = 0; index < symbols.length; index += 100) {
    const observations = await browserJson<Record<string, Record<string, any>>>('/api/v1/binance/market/observations?' + new URLSearchParams({
      symbols: symbols.slice(index, index + 100).join(','), extended: String(researchRules.some(row => ['breakout_score', 'oi_change_1h_pct'].includes(row.metric))) }), {}, 15000, signal)
    for (const [symbol, observation] of Object.entries(observations)) prices.set(symbol, observation)
  }
  if (signal?.aborted) throw signal.reason
  return researchTransaction('readwrite', async tx => {
    const evaluatedAt = new Date(started).toISOString()
    let evaluatedCount = 0, triggeredCount = 0, unavailableCount = 0
    for (const snapshot of rules) {
      const rule = await researchGet(tx, 'alerts', snapshot.id)
      if (!rule || !rule.enabled || rule.archivedAt || rule.version !== snapshot.version) continue
      if (rule.lastEvaluatedAt && Date.parse(rule.lastEvaluatedAt) >= started) continue
      const quote = prices.get(String(rule.configuration?.chartSymbolId ?? rule.symbol.toUpperCase().replace(/\//g, '')))
      const metric = rule.metric === 'breakout_score' && ['natural', 'momentum'].includes(String(rule.configuration?.scoreKind)) ? String(rule.configuration!.scoreKind) : rule.metric
      const price = rule.configuration?.chartSymbolId ? quote?.price : quote?.[metric]
      if (!Number.isFinite(price)) { unavailableCount++; continue }
      evaluatedCount++
      const triggered = alertTriggers(rule, price, started)
      rule.lastValue = price; rule.lastEvaluatedAt = evaluatedAt
      if (triggered) {
        triggeredCount++; rule.lastTriggeredAt = evaluatedAt
        if (rule.configuration?.once ?? !!rule.configuration?.chartSymbolId) rule.enabled = false
        await researchEvent(tx, 'alert', rule, 'alert_triggered', { value: price, threshold: rule.threshold, notificationChannels: rule.notificationChannels, configuration: rule.configuration })
      }
      if (finishedAlert(rule)) researchObjectStore(tx, 'alerts').delete(rule.id)
      else await researchPut(tx, 'alerts', rule)
    }
    return { evaluatedAt, ruleCount: rules.length, evaluatedCount, triggeredCount, unavailableCount }
  })
}
let evaluating: Promise<Awaited<ReturnType<typeof evaluateAlerts>>> | undefined
export function evaluateBrowserAlerts(signal?: AbortSignal) {
  return evaluating ??= (async () => {
    if (navigator.locks) return await navigator.locks.request('opentrading:alert-evaluation', { signal }, () => evaluateAlerts(signal))
    return await evaluateAlerts(signal)
  })().finally(() => { evaluating = undefined })
}

async function listNotes(symbol: string, offset = 0, limit = 200) {
  return researchTransaction('readonly', async tx => {
    const range = prefixRange([symbol.toUpperCase()])
    const items = await researchPage(tx, 'notes', 'symbolTimeline', range, offset, limit)
    const total = await idbValue(researchObjectStore(tx, 'notes').index('symbolTimeline').count(range))
    return { items, total, offset, limit }
  })
}

export function createBrowserResearchApi(server: typeof serverResearchApi): typeof serverResearchApi {
  return {
    deleteWatchlist: (id, version) => researchRemove('watchlists', id, version),
    deleteItem: (id, version) => researchRemove('items', id, version),
    deleteNote: (id, version) => researchRemove('notes', id, version),
    deleteScreener: (id, version) => researchRemove('screeners', id, version),
    deleteAlert: (id, version) => researchRemove('alerts', id, version),
    listNotes,
    async getWorkbench(eventLimit = 100, noteLimit = 200) {
      return researchTransaction('readonly', async tx => ({
        watchlists: (await researchAll(tx, 'watchlists')).sort((a,b)=>Number(!!a.archivedAt)-Number(!!b.archivedAt)||a.position-b.position||a.createdAt.localeCompare(b.createdAt)), items: (await researchAll(tx, 'items')).sort((a,b)=>a.position-b.position||a.createdAt.localeCompare(b.createdAt)),
        alerts: (await researchAll(tx, 'alerts')).filter(row => !finishedAlert(row)),
        notes: await researchPage(tx, 'notes', 'timeline', undefined, 0, noteLimit),
        events: await researchPage(tx, 'events', 'timeline', undefined, 0, eventLimit),
        unacknowledgedEventCount: await idbValue(researchObjectStore(tx, 'events').index('pending').count(1)),
      }))
    },
    async listEvents(kind = 'alert_triggered', unacknowledgedOnly = true, limit = 100, cursor?: string, signal?: AbortSignal) {
      if (signal?.aborted) throw signal.reason
      const before = cursor?.split('|')
      if (before && (before.length !== 4 || before[0] !== '1' || !Number.isFinite(Date.parse(before[1]!)) || !Number.isFinite(Date.parse(before[2]!)))) throw new ApiRequestError('Invalid event cursor', { status: 422 })
      return researchTransaction('readonly', async tx => {
        const index = unacknowledgedOnly ? kind ? 'pendingKindTimeline' : 'pendingTimeline' : kind ? 'kindTimeline' : 'timeline'
        const prefix: IDBValidKey[] = [...(unacknowledgedOnly ? [1] : []), ...(kind ? [kind] : [])]
        const all = prefix.length ? prefixRange(prefix) : undefined
        const range = before ? IDBKeyRange.bound(prefix, [...prefix, ...before.slice(1)], false, true) : all
        const page = await researchPage(tx, 'events', index, range, 0, limit + 1), items = page.slice(0, limit), last = items[items.length - 1]
        return { items, total: await idbValue(researchObjectStore(tx, 'events').index(index).count(all)),
          nextCursor: page.length > limit && last ? ['1', last.occurredAt, last.createdAt, last.id].join('|') : null }
      })
    },
    acknowledgeEvent: (id, body) => researchTransaction('readwrite', async tx => {
      const row = await researchGet(tx, 'events', id)
      if (!row) throw missingRecord()
      row.acknowledgedAt = body.acknowledged === false ? null : now(); await researchPut(tx, 'events', row); return row
    }),
    createWatchlist: body => researchCreate('watchlists', body),
    updateWatchlist: (id, body) => researchUpdate('watchlists', id, body),
    setWatchlistArchived: (id, body, archived) => archive('watchlists', id, body.expectedVersion, archived) as ReturnType<typeof server.setWatchlistArchived>,
    createItem: body => researchCreate('items', body),
    updateItem: (id, body) => researchUpdate('items', id, body),
    setItemArchived: (id, body, archived) => archive('items', id, body.expectedVersion, archived) as ReturnType<typeof server.setItemArchived>,
    createNote: body => researchCreate('notes', body),
    updateNote: (id, body) => researchUpdate('notes', id, body),
    setNoteArchived: (id, body, archived) => archive('notes', id, body.expectedVersion, archived) as ReturnType<typeof server.setNoteArchived>,
    createAlert: body => researchCreate('alerts', body),
    updateAlert: (id, body) => researchUpdate('alerts', id, body),
    evaluateAlerts: evaluateBrowserAlerts,
    async getAsset(symbol, timeframe = '1h', historyDays = 365, context = {}) {
      const market = await server.getAsset(symbol, timeframe, historyDays, context)
      const records = await researchTransaction('readonly', async tx => {
        const key = market.symbol.toUpperCase()
        return { watchItems: (await researchAll(tx, 'items', 'symbol', key)).filter(row => !row.archivedAt),
          alerts: (await researchAll(tx, 'alerts', 'symbol', key)).filter(row => !finishedAlert(row)),
          events: (await researchAll(tx, 'events', 'symbol', key)) }
      })
      const notes = await listNotes(market.symbol)
      return { ...market, ...records, notes: notes.items, notesTotal: notes.total, signals: [] }
    },
    async listScreeners(includeArchived = false) {
      return { items: (await researchTransaction('readonly', tx => researchAll(tx, 'screeners'))).filter(row => includeArchived || !row.archivedAt) }
    },
    createScreener: body => researchCreate('screeners', body),
    updateScreener: (id, body) => researchUpdate('screeners', id, body),
    setScreenerArchived: (id, version, archived) => archive('screeners', id, version, archived) as ReturnType<typeof server.setScreenerArchived>,
    async runScreener(id, asOf) {
      const row = await researchTransaction('readonly', tx => researchGet(tx, 'screeners', id))
      if (!row) throw missingRecord()
      if (asOf) return researchTransaction('readonly', async tx => {
        const range = IDBKeyRange.bound([id], [id, new Date(asOf).toISOString(), []])
        const historical = (await researchPage(tx, 'screenerRuns', 'screenerTimeline', range, 0, 1))[0]
        if (!historical) throw new Error('No saved snapshot exists for this date in this browser')
        return { ...historical, historicalReplay: true }
      })
      if (row.archivedAt) throw revisionConflict()
      const preview = await browserJson<any>('/api/v1/research/screener-preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(row.filters) }, 120000)
      return researchTransaction('readwrite', async tx => {
        const current = await researchGet(tx, 'screeners', id)
        if (!current) throw missingRecord()
        if (current.version !== row.version || current.archivedAt) throw revisionConflict()
        const result = { ...preview, id: crypto.randomUUID(), screenerId: id }
        await researchPut(tx, 'screenerRuns', result); return result
      })
    },
    async listScreenerRuns(id, offset = 0, limit = 50) {
      return researchTransaction('readonly', async tx => {
        const range = prefixRange([id])
        return { items: await researchPage(tx, 'screenerRuns', 'screenerTimeline', range, offset, limit),
          total: await idbValue(researchObjectStore(tx, 'screenerRuns').index('screenerTimeline').count(range)) }
      })
    },
    async listSignals(query = {}, _signal?: AbortSignal) { return { items: [], total: 0, offset: query.offset ?? 0, limit: query.limit ?? 100 } },
    async getSignalStats(_signal?: AbortSignal) { return { overall: { key: 'all', total: 0, resolved: 0, targetHits: 0, stopHits: 0, ambiguous: 0, expired: 0, winRatePct: null, averageConfidence: null, averageMfePct: null, averageMaePct: null }, bySource: [], byStrategy: [], confidenceCalibration: [] } },
    async evaluateSignals() { return { evaluatedAt: now(), candidateCount: 0, evaluatedCount: 0, resolvedCount: 0, unavailableCount: 0 } },
    async setSignalArchived() { throw missingRecord() },
  }
}
