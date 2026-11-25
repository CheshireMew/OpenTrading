import { personalTransaction, idbValue } from './browserDatabase'
import { RESEARCH_KINDS, researchStoreName, indexedRow, publicRow, emptyResearch, validateResearchBody, missingRecord, revisionConflict, finishedAlert, type ResearchKind, type ResearchRows, type ResearchState } from './researchSchema'
import { sameStoredValue } from './browserPersistence'
import { ApiRequestError } from '@/api/request'

export const RESEARCH_STORES = RESEARCH_KINDS.map(researchStoreName)
export const researchTransaction = <T>(mode: IDBTransactionMode, action: (tx: IDBTransaction) => T | Promise<T>) => personalTransaction(RESEARCH_STORES, mode, action)
export const researchObjectStore = (tx: IDBTransaction, kind: ResearchKind) => tx.objectStore(researchStoreName(kind))
export async function researchGet<K extends ResearchKind>(tx: IDBTransaction, kind: K, id: string): Promise<ResearchRows[K] | undefined> {
  return publicRow(await idbValue(researchObjectStore(tx, kind).get(id)))
}
export async function researchPut<K extends ResearchKind>(tx: IDBTransaction, kind: K, row: ResearchRows[K]): Promise<void> {
  await idbValue(researchObjectStore(tx, kind).put(indexedRow(row)))
}
export async function researchAll<K extends ResearchKind>(tx: IDBTransaction, kind: K, index?: string, range?: IDBValidKey | IDBKeyRange): Promise<ResearchRows[K][]> {
  const source = index ? researchObjectStore(tx, kind).index(index) : researchObjectStore(tx, kind)
  return (await idbValue(source.getAll(range))).map(publicRow)
}
export function researchPage<K extends ResearchKind>(tx: IDBTransaction, kind: K, index: string, range: IDBKeyRange | undefined, offset: number, limit: number): Promise<ResearchRows[K][]> {
  return new Promise((resolve, reject) => {
    const request = researchObjectStore(tx, kind).index(index).openCursor(range, 'prev'), rows: ResearchRows[K][] = []
    let advanced = false
    request.onerror = () => reject(request.error)
    request.onsuccess = () => {
      const cursor = request.result
      if (!cursor || rows.length >= limit) { resolve(rows); return }
      if (offset && !advanced) { advanced = true; cursor.advance(offset); return }
      rows.push(publicRow(cursor.value)); if (rows.length === limit) resolve(rows); else cursor.continue()
    }
  })
}
export const prefixRange = (prefix: IDBValidKey[]) => IDBKeyRange.bound(prefix, [...prefix, []])
export async function validateResearchLinks(tx: IDBTransaction, kind: ResearchKind, row: any) {
  if (kind === 'items') {
    const parent = await researchGet(tx, 'watchlists', row.watchlistId)
    if (!parent || parent.archivedAt) throw missingRecord()
    const duplicates = await researchAll(tx, 'items', 'identity', [row.watchlistId, row.symbol])
    if (duplicates.some(item => item.id !== row.id)) throw new ApiRequestError('This symbol is already in the watchlist', { status: 409 })
  }
  if ((kind === 'notes' || kind === 'alerts') && row.watchItemId) {
    const parent = await researchGet(tx, 'items', row.watchItemId)
    if (!parent) throw missingRecord()
    if (parent.symbol !== row.symbol) throw new ApiRequestError('The linked item has a different symbol', { status: 409 })
  }
  if (kind === 'screenerRuns' && !await researchGet(tx, 'screeners', row.screenerId)) throw missingRecord()
}
export async function researchEvent(tx: IDBTransaction, entityType: string, entity: any, kind: string, payload: any = {}) {
  const date = new Date().toISOString()
  await researchPut(tx, 'events', { id: crypto.randomUUID(), entityType, entityId: entity.id, symbol: entity.symbol ?? null,
    kind, title: entity.name ?? entity.title ?? entity.symbol ?? '', body: '', payload, occurredAt: date, createdAt: date, acknowledgedAt: null })
}
export async function researchCreate<K extends ResearchKind>(kind: K, body: Record<string, any>, defaults: Record<string, any> = {}): Promise<ResearchRows[K]> {
  const values = validateResearchBody(kind, { ...defaults, ...body })
  return researchTransaction('readwrite', async tx => {
    const date = new Date().toISOString(), row = { ...values, id: crypto.randomUUID(), version: 1, createdAt: date, updatedAt: date, archivedAt: null } as any
    if (kind === 'items' || kind === 'watchlists') row.position = await idbValue(researchObjectStore(tx, kind).count())
    if (kind === 'notes') row.occurredAt ??= date
    if (kind === 'alerts') { row.lastValue = row.configuration?.initialPrice ?? null; row.lastEvaluatedAt = null; row.lastTriggeredAt = null }
    await validateResearchLinks(tx, kind, row)
    await researchPut(tx, kind, row); await researchEvent(tx, kind, row, kind + '_created')
    return row
  })
}
export async function researchUpdate<K extends ResearchKind>(kind: K, id: string, body: Record<string, any>): Promise<ResearchRows[K]> {
  const { expectedVersion, ...command } = body
  const values = validateResearchBody(kind, command)
  return researchTransaction('readwrite', async tx => {
    const row = await researchGet(tx, kind, id) as any
    if (!row) throw missingRecord()
    if (row.version !== expectedVersion) throw revisionConflict()
    const next = { ...row, ...values, version: row.version + 1, updatedAt: new Date().toISOString() } as any
    if (kind === 'alerts' && body.configuration) next.lastValue = body.configuration.initialPrice ?? row.lastValue
    await validateResearchLinks(tx, kind, next)
    await researchPut(tx, kind, next); await researchEvent(tx, kind, next, kind + '_updated')
    return next
  })
}
export async function researchSetArchived<K extends ResearchKind>(kind: K, id: string, expectedVersion: number, archived: boolean): Promise<ResearchRows[K]> {
  return researchTransaction('readwrite', async tx => {
    const row = await researchGet(tx, kind, id) as any
    if (!row) throw missingRecord()
    if (row.version !== expectedVersion) throw revisionConflict()
    row.archivedAt = archived ? new Date().toISOString() : null
    row.version++; row.updatedAt = new Date().toISOString()
    await researchPut(tx, kind, row); await researchEvent(tx, kind, row, kind + (archived ? '_archived' : '_restored'))
    return row
  })
}
export async function researchRemove(kind: 'watchlists' | 'items' | 'notes' | 'alerts' | 'screeners', id: string, expectedVersion: number) {
  return researchTransaction('readwrite', async tx => {
    const row = await researchGet(tx, kind, id) as any
    if (!row) throw missingRecord()
    if (row.version !== expectedVersion) throw revisionConflict()
    const entities = new Set([id])
    const items = kind === 'watchlists' ? await researchAll(tx, 'items', 'watchlist', id) : kind === 'items' ? [row] : []
    for (const item of items) {
      entities.add(item.id)
      for (const child of ['notes', 'alerts'] as const) for (const linked of await researchAll(tx, child, 'watchItem', item.id)) {
        entities.add(linked.id); researchObjectStore(tx, child).delete(linked.id)
      }
      researchObjectStore(tx, 'items').delete(item.id)
    }
    if (kind === 'screeners') for (const run of await researchAll(tx, 'screenerRuns', 'screenerTimeline', prefixRange([id]))) {
      entities.add(run.id); researchObjectStore(tx, 'screenerRuns').delete(run.id)
    }
    researchObjectStore(tx, kind).delete(id)
    // Trigger events are durable notifications even after a one-shot rule exits.
    if (kind !== 'alerts') for (const entity of entities) for (const event of await researchAll(tx, 'events', 'entity', entity)) researchObjectStore(tx, 'events').delete(event.id)
    return { deleted: true }
  })
}
export async function researchSnapshot(tx: IDBTransaction): Promise<ResearchState> {
  const state = emptyResearch()
  for (const kind of RESEARCH_KINDS) (state as any)[kind] = await researchAll(tx, kind)
  return state
}
export async function restoreResearch(tx: IDBTransaction, incoming: ResearchState) {
  const remap = new Map<ResearchKind, Map<string, string>>()
  const kinds: ResearchKind[] = ['watchlists', 'screeners', 'items', 'notes', 'alerts', 'screenerRuns', 'events']
  const parents: Record<string, ResearchKind> = { watchlistId: 'watchlists', watchItemId: 'items', screenerId: 'screeners' }
  const entities: Record<string, ResearchKind> = { watchlist: 'watchlists', watchlists: 'watchlists', watch_item: 'items', item: 'items', items: 'items', note: 'notes', notes: 'notes', alert: 'alerts', alerts: 'alerts', screener: 'screeners', screeners: 'screeners', market_screener: 'screeners', screener_run: 'screenerRuns' }
  const copyLists = new Set<string>()
  for (const item of incoming.items ?? []) {
    const old = await researchGet(tx, 'items', item.id)
    const collisions = await researchAll(tx, 'items', 'identity', [item.watchlistId, item.symbol])
    if (old && !sameStoredValue(old, item) || collisions.some(row => row.id !== item.id)) copyLists.add(item.watchlistId)
  }
  for (const kind of kinds) {
    const ids = new Map<string, string>(); remap.set(kind, ids)
    for (const original of incoming[kind] ?? []) {
      const row: any = publicRow(indexedRow(original)), originalId = row.id
      if (kind !== 'events' && kind !== 'screenerRuns') Object.assign(row, validateResearchBody(kind, row, true))
      for (const [field, parent] of Object.entries(parents)) if (row[field]) row[field] = remap.get(parent)?.get(row[field]) ?? row[field]
      if (row.entityId) row.entityId = remap.get(entities[row.entityType])?.get(row.entityId) ?? row.entityId
      const old = await researchGet(tx, kind, row.id)
      if (old && (!sameStoredValue(old, row) || kind === 'watchlists' && copyLists.has(originalId))) row.id = crypto.randomUUID()
      ids.set(originalId, row.id)
      if (old && row.id === originalId) continue
      if (kind === 'alerts' && finishedAlert(row)) continue
      await validateResearchLinks(tx, kind, row)
      await researchPut(tx, kind, row)
    }
  }
}
