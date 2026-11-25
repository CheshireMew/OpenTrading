import type { PineRun, PineRecords } from '@/modules/chartWorkspace/generatedContracts'
import { browserStorageError, sameStoredValue } from './browserPersistence'

export const PINE_STORES = ['pine-runs', 'pine-rows']
const [RUNS, ROWS] = ['pine-runs', 'pine-rows'] as const
export type SavedPineRun = { run: PineRun; result?: Record<string, any>; counts?: Record<string, number> }
// Only old-store upgrades and explicit backup imports accept the retired scalar.
function migrateProgress(run: PineRun): PineRun {
  return { ...run, progress: typeof run.progress === 'object' ? run.progress : null }
}
const runRange = (id: string) => IDBKeyRange.bound([id], [id, []])
const rowRange = (id: string, kind: string, offset = 0) => IDBKeyRange.bound([id, kind, offset], [id, kind, Number.MAX_SAFE_INTEGER])

function writeRun(tx: IDBTransaction, id: string, value: SavedPineRun, result?: Record<string, any>) {
  const stored = { ...value }
  if (result !== undefined) {
    stored.result = {}; stored.counts = {}
    const rows = tx.objectStore(ROWS)
    rows.delete(runRange(id))
    // Queue bounded chunks. Subsequent chunks are enqueued from an IDB success
    // event so the same atomic transaction remains active without a long UI loop.
    for (const [kind, values] of Object.entries(result)) {
      if (!Array.isArray(values)) { stored.result[kind] = values; continue }
      stored.counts[kind] = values.length
      const chunk = (offset: number) => {
        const end = Math.min(offset + 512, values.length)
        for (let index = offset; index < end; index++) {
          const request = rows.put(values[index], [id, kind, index])
          if (index === end - 1 && end < values.length) request.onsuccess = () => chunk(end)
        }
      }
      chunk(0)
    }
  }
  tx.objectStore(RUNS).put(stored, id)
  return stored
}

export function upgradePineStore(database: IDBDatabase, tx: IDBTransaction) {
  database.createObjectStore(RUNS)
  database.createObjectStore(ROWS)
  // Consume the actual v1 records one at a time. IDB upgrade rollback preserves
  // the complete old store if any metadata or row write fails.
  const records = tx.objectStore('records'), cursor = records.openCursor()
  cursor.onsuccess = () => {
    const row = cursor.result
    if (!row) return
    if (String(row.key).startsWith('pine-run:')) {
      const value = row.value as SavedPineRun
      writeRun(tx, value.run.id, { run: migrateProgress(value.run) }, value.result)
      row.delete()
    }
    row.continue()
  }
}

function transact<T>(db: IDBDatabase, stores: string[], mode: IDBTransactionMode,
  work: (tx: IDBTransaction, result: (value: T) => void, fail: (cause: unknown) => void) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(stores, mode)
    let value: T, cause: unknown
    const fail = (error: unknown) => { cause = error; tx.abort() }
    tx.oncomplete = () => resolve(value)
    tx.onabort = () => reject(browserStorageError(cause ?? tx.error))
    try { work(tx, result => { value = result }, fail) } catch (error) { fail(error) }
  })
}

function readSnapshot(tx: IDBTransaction, value: SavedPineRun, done: (value: SavedPineRun) => void) {
  const { counts, ...snapshot } = value
  if (!counts) { done(snapshot); return }
  snapshot.result = { ...value.result }
  for (const kind of Object.keys(counts)) snapshot.result[kind] = []
  const cursor = tx.objectStore(ROWS).openCursor(runRange(value.run.id))
  cursor.onsuccess = () => {
    const row = cursor.result
    if (!row) { done(snapshot); return }
    const [, kind, index] = row.key as [string, string, number]
    snapshot.result![kind][index] = row.value
    row.continue()
  }
}

export function createBrowserPineStore(database: () => Promise<IDBDatabase>) {
  return {
    async get(id: string): Promise<SavedPineRun | undefined> {
      return transact(await database(), [RUNS], 'readonly', (tx, done) => {
        const request = tx.objectStore(RUNS).get(id)
        request.onsuccess = () => done(request.result)
      })
    },
    async list(): Promise<SavedPineRun[]> {
      return transact(await database(), [RUNS], 'readonly', (tx, done) => {
        const request = tx.objectStore(RUNS).getAll()
        request.onsuccess = () => done(request.result)
      })
    },
    async update(id: string, change: (previous: SavedPineRun | undefined) => SavedPineRun, result?: Record<string, any>) {
      return transact<SavedPineRun>(await database(), [RUNS, ROWS], 'readwrite', (tx, done, fail) => {
        const request = tx.objectStore(RUNS).get(id)
        request.onsuccess = () => {
          try {
            const previous = request.result as SavedPineRun | undefined
            const next = change(previous)
            // A terminal-state rejection must not replace its report either.
            done(next === previous ? next : writeRun(tx, id, next, result))
          } catch (error) { fail(error) }
        }
      })
    },
    async records(id: string, kind: string, offset = 0, limit = 200, sampled = false): Promise<PineRecords> {
      offset = Math.max(0, Math.trunc(offset)); limit = Math.max(1, Math.trunc(limit))
      return transact(await database(), [RUNS, ROWS], 'readonly', (tx, done, fail) => {
        const request = tx.objectStore(RUNS).get(id)
        request.onsuccess = () => {
          if (!request.result) { fail(new Error('Backtest does not exist in this browser')); return }
          const total = request.result.counts?.[kind] ?? 0
          const items: Record<string, any>[] = []
          if (!total || offset >= total) { done({ items, total, offset }); return }
          const rows = tx.objectStore(ROWS)
          if (sampled && total > limit) {
            for (let index = 0; index < limit; index++) {
              const position = limit === 1 ? 0 : Math.round(index * (total - 1) / (limit - 1))
              const row = rows.get([id, kind, position])
              row.onsuccess = () => { items[index] = row.result }
            }
            done({ items, total, offset })
          } else {
            const cursor = rows.openCursor(rowRange(id, kind, offset))
            cursor.onsuccess = () => {
              const row = cursor.result
              if (row) items.push(row.value)
              if (row && items.length < limit) row.continue()
              else done({ items, total, offset })
            }
          }
        }
      })
    },
    async snapshot(): Promise<Record<string, unknown>> {
      return transact(await database(), [RUNS, ROWS], 'readonly', (tx, done) => {
        const snapshots: Record<string, unknown> = {}
        const request = tx.objectStore(RUNS).openCursor()
        request.onsuccess = () => {
          const row = request.result
          if (!row) { done(snapshots); return }
          readSnapshot(tx, row.value, snapshot => {
            snapshots['pine-run:' + snapshot.run.id] = snapshot
            row.continue()
          })
        }
      })
    },
    async restore(value: SavedPineRun) {
      return transact<void>(await database(), [RUNS, ROWS], 'readwrite', (tx, done, fail) => {
        restorePineRun(tx, value).then(done, fail)
      })
    },
  }
}

export function restorePineRun(tx: IDBTransaction, value: SavedPineRun): Promise<void> {
  return new Promise((resolve, reject) => {
    const incoming = structuredClone(value)
    incoming.run = migrateProgress(incoming.run)
    if (['queued', 'loading', 'running'].includes(incoming.run.status)) incoming.run.status = 'interrupted'
    const request = tx.objectStore(RUNS).get(incoming.run.id)
    const save = (previous?: SavedPineRun) => {
      try {
        if (previous && sameStoredValue(previous, incoming)) { resolve(); return }
        if (previous) incoming.run.id = crypto.randomUUID()
        writeRun(tx, incoming.run.id, { run: incoming.run }, incoming.result)
        resolve()
      } catch (error) { reject(error) }
    }
    request.onsuccess = () => {
      if (request.result) readSnapshot(tx, request.result, save)
      else save()
    }
    request.onerror = () => reject(request.error)
  })
}
