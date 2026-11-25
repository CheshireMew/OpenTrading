import type { ResearchWatchlistResponse, ResearchWatchItemResponse, ResearchNoteResponse, ResearchAlertResponse, ResearchEventResponse, SavedMarketScreenerResponse, MarketScreenerRunResponse } from '@/modules/research/generatedContracts'
import { ApiRequestError } from '@/api/request'
import { researchCommandSchemas } from '@/modules/research/generatedValidation'
import { validateSchema } from '@/utils/validateSchema'

export type ResearchRows = {
  watchlists: ResearchWatchlistResponse; items: ResearchWatchItemResponse; notes: ResearchNoteResponse
  alerts: ResearchAlertResponse; events: ResearchEventResponse; screeners: SavedMarketScreenerResponse; screenerRuns: MarketScreenerRunResponse
}
export type ResearchKind = keyof ResearchRows
export type ResearchState = { [K in ResearchKind]: ResearchRows[K][] }
export const RESEARCH_KINDS: ResearchKind[] = ['watchlists', 'items', 'notes', 'alerts', 'events', 'screeners', 'screenerRuns']
export const researchStoreName = (kind: ResearchKind) => 'research-' + kind
export const emptyResearch = (): ResearchState => ({ watchlists: [], items: [], notes: [], alerts: [], events: [], screeners: [], screenerRuns: [] })
export const plain = <T>(value: T): T => JSON.parse(JSON.stringify(value))
export const missingRecord = () => new ApiRequestError('Record does not exist in this browser', { status: 404 })
export const revisionConflict = () => new ApiRequestError('This record changed in another tab. Reload and retry.', { status: 409 })
const invalid = (field: string): never => { throw new ApiRequestError('Invalid research record: ' + field, { status: 422 }) }
const text = (value: unknown, field: string, maximum: number, required = false): string => {
  if (value === undefined && !required) return ''
  if (typeof value !== 'string' || value.length > maximum || required && !value.trim()) return invalid(field)
  return value.trim()
}
const number = (value: unknown, field: string, minimum: number, maximum = Infinity): number => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum || value > maximum) return invalid(field)
  return value
}
const object = (value: unknown, field: string): Record<string, any> => {
  if (value === undefined) return {}
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid(field)
  return plain(value)
}
export const finishedAlert = (row: ResearchAlertResponse) => !!row.archivedAt ||
  (!row.enabled && !!row.lastTriggeredAt && (row.configuration?.once ?? !!row.configuration?.chartSymbolId))

const commandNames: Partial<Record<ResearchKind, keyof typeof researchCommandSchemas>> = {
  watchlists: 'ResearchWatchlistCreateCommand', items: 'ResearchWatchItemCreateCommand', notes: 'ResearchNoteCreateCommand',
  alerts: 'ResearchAlertCreateCommand', screeners: 'SavedMarketScreenerCreateCommand',
}
/** Field constraints/defaults come from the same Pydantic models as HTTP.
 * Python's custom model validators have matching rules here and parity tests. */
export function validateResearchBody(kind: ResearchKind, input: Record<string, any>, stored = false): Record<string, any> {
  const name = commandNames[kind]
  if (!name) return plain(input)
  const schema = researchCommandSchemas[name] as any, raw = plain(input)
  const command = stored ? Object.fromEntries(Object.entries(raw).filter(([key]) => key in schema.properties)) : raw
  const factoryDefaults: Record<string, any> = kind === 'items' ? { tags: [], sourceContext: {} }
    : kind === 'notes' ? { snapshot: {} } : kind === 'alerts' ? { notificationChannels: ['in_app'], configuration: {} } : {}
  const body = validateSchema({ ...factoryDefaults, ...command }, schema)
  for (const key of ['name', 'description', 'displayName', 'thesis', 'title', 'content', 'metric']) if (typeof body[key] === 'string') body[key] = body[key].trim()
  if (body.symbol) body.symbol = body.assetClass === 'web3' ? body.symbol.trim() : body.symbol.trim().toUpperCase()
  if (kind === 'items') {
    const seen = new Set<string>()
    body.tags = body.tags.map((tag: unknown) => text(tag, 'tag', 40)).filter((tag: string) => {
      if (!tag || seen.has(tag.toLowerCase())) return false
      seen.add(tag.toLowerCase()); return true
    })
  }
  if (kind === 'screeners') body.filters = validateScreenerFilters(body.filters)
  if (kind === 'alerts') {
    if (body.metric === 'portfolio_drift_pct') invalid('metric')
    const configuration = body.configuration
    if (configuration.chartSymbolId) {
      if (typeof configuration.chartSymbolId !== 'string' || body.metric !== 'price' || body.threshold <= 0) invalid('chartSymbolId/price')
      if (configuration.initialPrice != null) number(configuration.initialPrice, 'initialPrice', Number.MIN_VALUE)
    }
    if (['between', 'outside'].includes(body.operator) && (body.secondaryThreshold == null || body.secondaryThreshold <= body.threshold)) invalid('secondaryThreshold')
  }
  return stored ? { ...raw, ...body } : body
}
export function validateScreenerFilters(value: unknown): Record<string, any> {
  const filters = validateSchema({ symbols: [], ...object(value, 'filters') }, researchCommandSchemas.MarketScreenerFilters)
  filters.quoteAsset = filters.quoteAsset.trim().toUpperCase()
  filters.symbols = [...new Set(filters.symbols.map((symbol: string) => symbol.trim().toUpperCase().replace(/\//g, '')).filter(Boolean))]
  if (filters.minRsi != null && filters.maxRsi != null && filters.minRsi > filters.maxRsi) invalid('RSI range')
  if (filters.minPriceChangePct != null && filters.maxPriceChangePct != null && filters.minPriceChangePct > filters.maxPriceChangePct) invalid('price range')
  return filters
}

export function indexedRow<T extends { id: string }>(row: T): T {
  const value = plain(row) as any
  for (const key of ['createdAt', 'updatedAt', 'occurredAt', 'lastEvaluatedAt', 'lastTriggeredAt', 'acknowledgedAt', 'archivedAt', 'snapshotAsOf', 'evaluatedAt'])
    if (typeof value[key] === 'string' && Number.isFinite(Date.parse(value[key]))) value[key] = new Date(value[key]).toISOString()
  value._index = { archive: value.archivedAt ? 1 : 0, enabled: value.enabled && !value.archivedAt ? 1 : 0,
    unacknowledged: value.acknowledgedAt ? 0 : 1, symbol: String(value.symbol ?? '').toUpperCase() }
  return value
}
export function publicRow<T>(value: T): T {
  if (!value) return value
  const { _index: _, ...row } = value as any
  return row
}

export function upgradeResearch(db: IDBDatabase, tx: IDBTransaction) {
  for (const kind of RESEARCH_KINDS) {
    const store = db.createObjectStore(researchStoreName(kind), { keyPath: 'id' })
    store.createIndex('symbol', '_index.symbol')
    store.createIndex('created', ['createdAt', 'id'])
    if (kind === 'items') { store.createIndex('watchlist', 'watchlistId'); store.createIndex('identity', ['watchlistId', 'symbol']) }
    if (kind === 'notes' || kind === 'alerts') store.createIndex('watchItem', 'watchItemId')
    if (kind === 'notes') { store.createIndex('timeline', ['occurredAt', 'createdAt', 'id']); store.createIndex('symbolTimeline', ['_index.symbol', 'occurredAt', 'createdAt', 'id']) }
    if (kind === 'alerts') store.createIndex('enabled', '_index.enabled')
    if (kind === 'screenerRuns') store.createIndex('screenerTimeline', ['screenerId', 'snapshotAsOf', 'id'])
    if (kind === 'events') {
      store.createIndex('timeline', ['occurredAt', 'createdAt', 'id'])
      store.createIndex('kindTimeline', ['kind', 'occurredAt', 'createdAt', 'id'])
      store.createIndex('pendingTimeline', ['_index.unacknowledged', 'occurredAt', 'createdAt', 'id'])
      store.createIndex('pendingKindTimeline', ['_index.unacknowledged', 'kind', 'occurredAt', 'createdAt', 'id'])
      store.createIndex('pending', '_index.unacknowledged'); store.createIndex('entity', 'entityId')
    }
  }
  const records = tx.objectStore('records'), old = records.get('research')
  old.onsuccess = () => {
    if (!old.result) return
    for (const kind of RESEARCH_KINDS) for (const row of old.result[kind] ?? []) {
      if (kind === 'alerts' && finishedAlert(row)) continue
      tx.objectStore(researchStoreName(kind)).put(indexedRow(row))
    }
    records.delete('research')
  }
}

export function validateResearchBackup(value: unknown): asserts value is ResearchState {
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalid('research')
  const state = value as ResearchState
  for (const kind of RESEARCH_KINDS) {
    if (!Array.isArray(state[kind])) invalid(kind)
    const seen = new Set<string>()
    for (const row of state[kind] as any[]) {
      if (!row || typeof row.id !== 'string' || !row.id || seen.has(row.id)) invalid('id')
      seen.add(row.id)
      if (kind === 'events') {
        for (const key of ['entityId', 'entityType', 'kind', 'title', 'body']) if (typeof row[key] !== 'string') invalid(key)
        for (const key of ['occurredAt', 'createdAt']) if (!Number.isFinite(Date.parse(row[key]))) invalid(key)
        if (row.acknowledgedAt != null && !Number.isFinite(Date.parse(row.acknowledgedAt))) invalid('acknowledgedAt')
        object(row.payload, 'payload')
      } else if (kind === 'screenerRuns') {
        text(row.screenerId, 'screenerId', 120, true); validateScreenerFilters(row.filters)
        if (!Array.isArray(row.resultItems) || row.resultCount !== row.resultItems.length) invalid('resultItems')
        for (const key of ['snapshotAsOf', 'evaluatedAt']) if (!Number.isFinite(Date.parse(row[key]))) invalid(key)
      } else {
        validateResearchBody(kind, row, true)
        if (!Number.isInteger(row.version) || row.version < 1) invalid('version')
        for (const key of ['createdAt', 'updatedAt']) if (!Number.isFinite(Date.parse(row[key]))) invalid(key)
        if (row.archivedAt != null && !Number.isFinite(Date.parse(row.archivedAt))) invalid('archivedAt')
      }
    }
  }
}
