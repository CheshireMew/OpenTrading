import { browserStorageError } from './browserPersistence'

export const NOTIFICATION_STORE = 'notification-deliveries'
type DeliveryState = { cursor: string | null; migrated: boolean }
export function createBrowserNotificationStore(database: () => Promise<IDBDatabase>) {
  async function read<T>(action: (store: IDBObjectStore) => () => T): Promise<T> {
    const db = await database()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(NOTIFICATION_STORE)
      const result = action(tx.objectStore(NOTIFICATION_STORE))
      tx.oncomplete = () => resolve(result())
      tx.onabort = () => reject(browserStorageError(tx.error))
    })
  }
  return {
    state: () => read<DeliveryState>(store => {
      const request = store.get('state')
      return () => request.result ?? { cursor: null, migrated: false }
    }),
    delivered: (ids: string[]) => read(store => {
      const requests = ids.map(id => store.get('receipt:' + id))
      return () => new Set(ids.filter((_id, index) => requests[index]!.result === true))
    }),
    async commit(ids: string[], cursor: string | null) {
      const db = await database()
      return new Promise<void>((resolve, reject) => {
        const tx = db.transaction(NOTIFICATION_STORE, 'readwrite'), store = tx.objectStore(NOTIFICATION_STORE)
        tx.oncomplete = () => resolve()
        tx.onabort = () => reject(browserStorageError(tx.error))
        for (const id of ids) store.put(true, 'receipt:' + id)
        store.put({ cursor, migrated: true } satisfies DeliveryState, 'state')
      })
    },
  }
}
