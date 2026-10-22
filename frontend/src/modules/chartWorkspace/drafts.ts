import { migrateWorkspaceState } from './legacyState'

let pending:Promise<IDBDatabase>|undefined
let legacyPending:Promise<IDBDatabase|undefined>|undefined
function database() {
  return pending ??= new Promise<IDBDatabase>((resolve,reject)=>{
    const open = indexedDB.open('opentrading-chart-workspace',1)
    open.onupgradeneeded = () => open.result.createObjectStore('drafts')
    open.onsuccess = () => resolve(open.result)
    open.onerror = () => reject(open.error)
  })
}
function legacyDatabase() {
  return legacyPending ??= new Promise<IDBDatabase|undefined>((resolve) => {
    const open = indexedDB.open('heimdall-chart-workspace')
    // An absent legacy database should stay absent.
    open.onupgradeneeded = () => open.transaction?.abort()
    open.onsuccess = () => resolve(open.result)
    open.onerror = () => resolve(undefined)
  })
}
async function getDraft(db:IDBDatabase,key:string):Promise<unknown> {
  if (!db.objectStoreNames.contains('drafts')) return undefined
  return new Promise((resolve,reject) => {
    const query = db.transaction('drafts').objectStore('drafts').get(key)
    query.onsuccess = () => resolve(query.result)
    query.onerror = () => reject(query.error)
  })
}
export async function readDraft<T>(key:string):Promise<T|undefined> {
  const db = await database()
  let value = await getDraft(db,key)
  if (value === undefined) {
    const legacy = await legacyDatabase()
    if (legacy) {
      value = await getDraft(legacy,key.replace('opentrading-v7-2','heimdall-v7-2'))
      if (value !== undefined) await writeDraft(key,migrateWorkspaceState(value))
    }
  }
  return migrateWorkspaceState(value) as T|undefined
}
export async function writeDraft(key:string,value:unknown) {
  const db = await database()
  return new Promise<void>((resolve,reject)=>{
    const transaction = db.transaction('drafts','readwrite')
    transaction.objectStore('drafts').put(JSON.parse(JSON.stringify(value)),key)
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
}
