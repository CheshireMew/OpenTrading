// One read/write transaction per update keeps concurrent browser tabs from
// overwriting each other's data. None of these records are sent to the API.
let pending: Promise<IDBDatabase> | undefined
function database() {
  return pending ??= new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('opentrading-browser-records', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('records')
    request.onsuccess = () => {
      request.result.onversionchange = () => { request.result.close(); pending = undefined }
      resolve(request.result)
    }
    request.onerror = () => { pending = undefined; reject(new Error('Browser storage is unavailable')) }
    request.onblocked = () => { pending = undefined; reject(new Error('Close other OpenTrading tabs and retry')) }
  })
}
export async function browserRecord<T>(key: string): Promise<T | undefined> {
  const db = await database()
  return new Promise((resolve, reject) => {
    const request = db.transaction('records').objectStore('records').get(key)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}
export async function updateBrowserRecord<T>(key: string, change: (previous: T | undefined) => T): Promise<T> {
  const db = await database()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('records', 'readwrite'), store = tx.objectStore('records')
    let result: T, cause: unknown
    tx.oncomplete = () => resolve(result)
    tx.onabort = () => reject(cause ?? new Error(tx.error?.name === 'QuotaExceededError' ? 'Browser storage is full; export your data first' : 'Browser storage is unavailable'))
    const request = store.get(key)
    request.onsuccess = () => {
      try { result = change(request.result); store.put(result, key) }
      catch (error) { cause = error; tx.abort() }
    }
  })
}
export async function browserRecords(): Promise<Record<string, unknown>> {
  const db = await database()
  return new Promise((resolve, reject) => {
    const tx = db.transaction('records'), store = tx.objectStore('records')
    const keys = store.getAllKeys(), values = store.getAll()
    tx.oncomplete = () => resolve(Object.fromEntries(keys.result.map((key, index) => [String(key), values.result[index]])))
    tx.onabort = () => reject(tx.error)
  })
}

export async function restoreBrowserRecords(records: Record<string, unknown>) {
  // Keep current data on conflicts. Resolve IDs before copying relationships.
  if (records.research) await updateBrowserRecord<any>('research', previous => {
    const incoming = structuredClone(records.research) as Record<string, any[]>
    const current = previous ?? {}, remap = new Map<string, string>()
    const kinds = ['watchlists', 'items', 'notes', 'alerts', 'screeners', 'screenerRuns', 'events']
    for (const kind of kinds) {
      current[kind] ??= []
      for (const row of incoming[kind] ?? []) {
        const existing = current[kind].find((item: any) => item.id === row.id)
        remap.set(row.id, existing && JSON.stringify(existing) !== JSON.stringify(row) ? crypto.randomUUID() : row.id)
      }
    }
    for (const kind of kinds) for (const row of incoming[kind] ?? []) {
      const originalId = row.id
      row.id = remap.get(originalId)
      for (const field of ['watchlistId', 'watchItemId', 'screenerId', 'entityId']) if (typeof row[field] === 'string') row[field] = remap.get(row[field]) ?? row[field]
      if (!current[kind].some((item: any) => item.id === row.id)) current[kind].push(row)
    }
    return current
  })
  for (const [key, value] of Object.entries(records)) if (key.startsWith('pine-run:')) {
    const row = structuredClone(value) as any
    if (['queued', 'loading', 'running'].includes(row.run.status)) row.run.status = 'interrupted'
    const previous = await browserRecord(key)
    if (previous && JSON.stringify(previous) === JSON.stringify(row)) continue
    if (previous) row.run.id = crypto.randomUUID()
    await updateBrowserRecord('pine-run:' + row.run.id, existing => existing ?? row)
  }
}
