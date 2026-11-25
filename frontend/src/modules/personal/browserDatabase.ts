import { upgradePineStore } from './browserPineStore'
import { NOTIFICATION_STORE } from './browserNotificationStore'
import { upgradeResearch } from './researchSchema'
import { browserStorageError } from './browserPersistence'

let pending: Promise<IDBDatabase> | undefined
let migration: Promise<void> | undefined
export function idbValue<T = any>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => { request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error) })
}
export function transactOn<T>(db: IDBDatabase, stores: string[], mode: IDBTransactionMode, work: (tx: IDBTransaction) => T | Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(stores, mode)
    let result: T, cause: unknown
    tx.oncomplete = () => resolve(result)
    tx.onabort = () => reject(browserStorageError(cause ?? tx.error))
    try { Promise.resolve(work(tx)).then(value => { result = value }, error => { cause = error; try { tx.abort() } catch { reject(browserStorageError(error)) } }) }
    catch (error) { cause = error; tx.abort() }
  })
}
async function legacyDatabase(name: string): Promise<IDBDatabase | undefined> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(name)
    let absent = false
    let abandoned = false
    request.onupgradeneeded = () => { absent = true; request.transaction!.abort() }
    request.onsuccess = () => { if (abandoned) request.result.close(); else resolve(request.result) }
    request.onerror = () => absent ? resolve(undefined) : reject(browserStorageError(request.error))
    request.onblocked = () => { abandoned = true; reject(new Error('Close other OpenTrading tabs and retry')) }
  })
}
async function migrateExternal(db: IDBDatabase) {
  for (const [name, stores] of [['opentrading-personal-data', ['documents', 'revisions', 'metadata']], ['opentrading-chart-workspace', ['drafts']]] as const) {
    const marker = 'migrated-database:' + name
    if (await transactOn(db, ['metadata'], 'readonly', tx => idbValue(tx.objectStore('metadata').get(marker)))) continue
    const old = await legacyDatabase(name)
    const entries: Record<string, [IDBValidKey, any][]> = {}
    try {
      if (old) for (const store of stores) {
        if (!old.objectStoreNames.contains(store)) continue
        entries[store] = await transactOn(old, [store], 'readonly', async tx => {
          const source = tx.objectStore(store), keys = idbValue(source.getAllKeys()), values = idbValue(source.getAll())
          const [storedKeys, storedValues] = await Promise.all([keys, values])
          return storedKeys.map((key, index) => [key, storedValues[index]] as [IDBValidKey, any])
        })
      }
      await transactOn(db, [...stores, 'metadata'].filter((store, index, values) => values.indexOf(store) === index), 'readwrite', async tx => {
        const metadata = tx.objectStore('metadata')
        if (await idbValue(metadata.get(marker))) return
        for (const [name, rows] of Object.entries(entries)) for (const [key, value] of rows) {
          const target = tx.objectStore(name)
          if (target.keyPath) target.put(value); else target.put(value, key)
        }
        metadata.put(true, marker)
      })
    } finally { old?.close() }
  }
}
export async function personalDatabase(): Promise<IDBDatabase> {
  const db = await (pending ??= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('opentrading-browser-records', 3)
    let abandoned = false
    request.onupgradeneeded = event => {
      const db = request.result, tx = request.transaction!
      if (event.oldVersion < 1) db.createObjectStore('records')
      if (event.oldVersion < 2) { upgradePineStore(db, tx); db.createObjectStore(NOTIFICATION_STORE) }
      if (event.oldVersion < 3) {
        db.createObjectStore('documents', { keyPath: ['kind', 'id'] }).createIndex('kind', 'kind')
        db.createObjectStore('revisions', { keyPath: ['kind', 'id', 'version'] })
        db.createObjectStore('metadata'); db.createObjectStore('drafts')
        upgradeResearch(db, tx)
      }
    }
    request.onsuccess = () => {
      if (abandoned) { request.result.close(); return }
      request.result.onversionchange = () => { request.result.close(); pending = undefined; migration = undefined }
      resolve(request.result)
    }
    request.onerror = () => { pending = undefined; reject(browserStorageError(request.error)) }
    request.onblocked = () => { abandoned = true; pending = undefined; reject(new Error('Close other OpenTrading tabs and retry')) }
  }))
  await (migration ??= migrateExternal(db).catch(error => { migration = undefined; throw error }))
  return db
}
export async function personalTransaction<T>(stores: string[], mode: IDBTransactionMode, work: (tx: IDBTransaction) => T | Promise<T>): Promise<T> {
  return transactOn(await personalDatabase(), stores, mode, work)
}
