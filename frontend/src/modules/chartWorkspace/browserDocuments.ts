import type { WorkspaceDocument, WorkspaceWrite } from './generatedContracts'
import { ApiRequestError } from '@/api/request'
import { cw } from './locale'
import { personalDatabase, idbValue } from '@/modules/personal/browserDatabase'

export type BrowserDocumentKind = 'layouts' | 'watchlists' | 'scripts'
export const BROWSER_DOCUMENT_KINDS: BrowserDocumentKind[] = ['layouts', 'watchlists', 'scripts']
export type BrowserDocumentEntry = { kind: BrowserDocumentKind; document: WorkspaceDocument }
type Stored = BrowserDocumentEntry & { id: string; archived: boolean }
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value))
const conflict = () => new ApiRequestError(cw('browserDocumentConflict'), { status: 409 })

export function createBrowserDocuments(legacy: {
  list: (kind: BrowserDocumentKind) => Promise<WorkspaceDocument[]>
  version: (kind: BrowserDocumentKind, id: string, version: number) => Promise<WorkspaceDocument>
}) {
  const migrations = new Map<BrowserDocumentKind, Promise<void>>()
  const database = personalDatabase
  async function transact<T>(stores: string[], mode: IDBTransactionMode, task: (tx: IDBTransaction, done: (value: T) => void, fail: (error: Error) => void) => void): Promise<T> {
    const db = await database()
    return new Promise<T>((resolve, reject) => {
      const tx = db.transaction(stores, mode)
      let result: T, cause: Error | undefined
      tx.oncomplete = () => resolve(result)
      tx.onabort = () => reject(cause ?? new Error(cw(tx.error?.name === 'QuotaExceededError' ? 'browserStorageFull' : 'browserStorageUnavailable')))
      const fail = (error: Error) => { cause = error; tx.abort() }
      try { task(tx, value => { result = value }, fail) } catch (error) { fail(error as Error) }
    })
  }
  async function migrate(kind: BrowserDocumentKind) {
    const migrated = await transact<unknown>(['metadata'], 'readonly', (tx, done) => {
      const request = tx.objectStore('metadata').get('migrated:' + kind)
      request.onsuccess = () => done(request.result)
    })
    if (migrated) return
    const documents = await legacy.list(kind)
    await transact<void>(['documents', 'revisions', 'metadata'], 'readwrite', (tx, done) => {
      const metadata = tx.objectStore('metadata'), request = metadata.get('migrated:' + kind)
      request.onsuccess = () => {
        // Another tab can complete the import while this tab fetches the old data.
        if (!request.result) {
          for (const document of documents) {
            tx.objectStore('documents').put({ kind, id: document.id, document: copy(document), archived: false } satisfies Stored)
            tx.objectStore('revisions').put({ kind, id: document.id, version: document.version, document: copy(document) })
          }
          metadata.put(Date.now(), 'migrated:' + kind)
        }
        done()
      }
    })
  }
  function ensure(kind: BrowserDocumentKind) {
    let migration = migrations.get(kind)
    if (!migration) {
      migration = migrate(kind).catch(error => { migrations.delete(kind); throw error })
      migrations.set(kind, migration)
    }
    return migration
  }
  async function list(kind: BrowserDocumentKind) {
    await ensure(kind)
    return transact<WorkspaceDocument[]>(['documents'], 'readonly', (tx, done) => {
      const request = tx.objectStore('documents').index('kind').getAll(kind)
      request.onsuccess = () => done((request.result as Stored[]).filter(row => !row.archived).map(row => row.document).sort((a, b) => b.updated_at - a.updated_at || a.id.localeCompare(b.id)))
    })
  }
  async function get(kind: BrowserDocumentKind, id: string, version?: number): Promise<WorkspaceDocument> {
    await ensure(kind)
    const removed = await transact<unknown>(['metadata'], 'readonly', (tx, done) => {
      const query=tx.objectStore('metadata').get(`deleted:${kind}:${id}`);query.onsuccess=()=>done(query.result)
    })
    if(removed) throw new ApiRequestError(cw('browserDocumentMissing'),{status:404})
    const document = await transact<WorkspaceDocument | undefined>(['documents', 'revisions'], 'readonly', (tx, done) => {
      const query = version === undefined ? tx.objectStore('documents').get([kind, id]) : tx.objectStore('revisions').get([kind, id, version])
      query.onsuccess = () => done(query.result && !query.result.archived ? query.result.document : undefined)
    })
    if (document) return document
    // Only an old pending browser draft may need a pre-migration server revision.
    if (version !== undefined) {
      const historical = await legacy.version(kind, id, version)
      await transact<void>(['revisions'], 'readwrite', (tx, done) => {
        tx.objectStore('revisions').put({ kind, id, version, document: historical }); done()
      })
      return historical
    }
    throw new ApiRequestError(cw('browserDocumentMissing'), { status: 404 })
  }
  async function save(kind: BrowserDocumentKind, id: string, write: WorkspaceWrite) {
    await ensure(kind)
    return transact<WorkspaceDocument>(['documents', 'revisions', 'metadata'], 'readwrite', (tx, done, fail) => {
      const store = tx.objectStore('documents'), query = store.get([kind, id])
      const removed=tx.objectStore('metadata').get(`deleted:${kind}:${id}`)
      removed.onsuccess = () => {
        if(removed.result){fail(new ApiRequestError(cw('browserDocumentMissing'),{status:404}));return}
        const old = query.result as Stored | undefined
        if (old?.document.readonly) { fail(new ApiRequestError(cw('readonlyCopy'), { status: 409 })); return }
        if ((old?.document.version ?? 0) !== (write.expected_version ?? 0)) { fail(conflict()); return }
        const document: WorkspaceDocument = { id, name: write.name, data: copy(write.data), version: (write.expected_version ?? 0) + 1, updated_at: Date.now(), readonly: false }
        store.put({ kind, id, document, archived: false } satisfies Stored)
        tx.objectStore('revisions').put({ kind, id, version: document.version, document })
        done(document)
      }
    })
  }
  async function remove(kind: BrowserDocumentKind, id: string, expectedVersion:number) {
    await ensure(kind)
    return transact<void>(['documents','revisions','metadata'], 'readwrite', (tx, done, fail) => {
      const store = tx.objectStore('documents'), query = store.get([kind, id])
      query.onsuccess = () => {
        const old = query.result as Stored | undefined
        if (!old) { fail(new ApiRequestError(cw('browserDocumentMissing'), { status: 404 })); return }
        if (old.document.readonly) { fail(new ApiRequestError(cw('readonlyCopy'), { status: 409 })); return }
        if(old.document.version!==expectedVersion){fail(conflict());return}
        store.delete([kind,id])
        const revisions=tx.objectStore('revisions'), cursor=revisions.openKeyCursor(IDBKeyRange.bound([kind,id,0],[kind,id,Number.MAX_SAFE_INTEGER]))
        cursor.onsuccess=()=>{if(cursor.result){revisions.delete(cursor.result.primaryKey);cursor.result.continue()}}
        tx.objectStore('metadata').put(Date.now(),`deleted:${kind}:${id}`)
        done()
      }
    })
  }
  async function snapshot(): Promise<BrowserDocumentEntry[]> {
    await Promise.all(BROWSER_DOCUMENT_KINDS.map(ensure))
    return transact<BrowserDocumentEntry[]>(['documents'], 'readonly', (tx, done) => {
      const request = tx.objectStore('documents').getAll()
      request.onsuccess = () => done((request.result as Stored[]).filter(row => !row.archived).map(({ kind, document }) => ({ kind, document })))
    })
  }
  async function restore(entries: BrowserDocumentEntry[]) {
    return transact<Record<string, string>>(['documents', 'revisions', 'metadata'], 'readwrite', (tx, done, fail) => {
      restoreBrowserDocuments(tx, entries).then(done, fail)
    })
  }
  return { list, get, save, remove, snapshot, restore }
}

export async function restoreBrowserDocuments(tx: IDBTransaction, entries: BrowserDocumentEntry[]) {
  const documents = tx.objectStore('documents')
  const existing = new Map((await idbValue(documents.getAll()) as Stored[]).map(row => [row.kind + ':' + row.id, row]))
  const ids: Record<string, string> = {}, planned: BrowserDocumentEntry[] = []
  const remapLayout = (data: WorkspaceDocument['data']) => {
    if (typeof data.watchlistId === 'string') data.watchlistId = ids['watchlists:' + data.watchlistId] ?? data.watchlistId
    if (Array.isArray(data.favoriteIndicators)) data.favoriteIndicators = data.favoriteIndicators.map(value =>
      typeof value === 'string' && value.startsWith('script:') ? 'script:' + (ids['scripts:' + value.slice(7)] ?? value.slice(7)) : value)
    const charts = (data.state as { charts?: { ext?: Record<string, unknown> }[] } | undefined)?.charts
    for (const chart of charts ?? []) {
      const scripts = chart.ext?.['opentrading.pine']
      if (Array.isArray(scripts)) for (const script of scripts) if (typeof script.scriptId === 'string') {
        const next = ids['scripts:' + script.scriptId]
        if (next && next !== script.scriptId) { script.scriptId = next; script.version = 1 }
      }
    }
  }
  // Resolve referenced watchlists and scripts before comparing layouts.
  for (const entry of [...entries.filter(row => row.kind !== 'layouts'), ...entries.filter(row => row.kind === 'layouts')]) {
    const incoming = copy(entry.document), key = entry.kind + ':' + incoming.id, old = existing.get(key)
    if (entry.kind === 'layouts') remapLayout(incoming.data)
    if (old && (old.document.readonly || JSON.stringify([old.document.name, old.document.data]) === JSON.stringify([incoming.name, incoming.data]))) { ids[key] = old.id; continue }
    if (old) { incoming.id = crypto.randomUUID(); incoming.name = cw('browserImportedCopy', { name: incoming.name }); incoming.version = 1 }
    incoming.updated_at = Date.now()
    ids[key] = incoming.id
    planned.push({ kind: entry.kind, document: incoming })
  }
  for (const entry of planned) {
    const { kind, document } = entry
    documents.put({ kind, id: document.id, document, archived: false } satisfies Stored)
    tx.objectStore('revisions').put({ kind, id: document.id, version: document.version, document })
    tx.objectStore('metadata').delete(`deleted:${kind}:${document.id}`)
  }
  for (const kind of BROWSER_DOCUMENT_KINDS) tx.objectStore('metadata').put(Date.now(), 'migrated:' + kind)
  return ids
}
