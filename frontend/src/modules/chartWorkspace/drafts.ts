let pending:Promise<IDBDatabase>|undefined
function database() {
  return pending ??= new Promise<IDBDatabase>((resolve,reject)=>{
    const open = indexedDB.open('heimdall-chart-workspace',1)
    open.onupgradeneeded = () => open.result.createObjectStore('drafts')
    open.onsuccess = () => resolve(open.result)
    open.onerror = () => reject(open.error)
  })
}
export async function readDraft<T>(key:string):Promise<T|undefined> {
  const db = await database()
  return new Promise((resolve,reject)=>{
    const query = db.transaction('drafts').objectStore('drafts').get(key)
    query.onsuccess = () => resolve(query.result)
    query.onerror = () => reject(query.error)
  })
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
