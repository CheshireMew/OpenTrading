import { idbValue, personalTransaction } from './browserDatabase'
import { getLocalStorage } from '@/utils/storage'

export const isBackupPreference = (key: string) => ['locale', 'theme', 'opentrading_user_preferences', 'opentrading:macro-signals:section', 'opentrading:asset-observation-symbol'].includes(key) || key.startsWith('opentrading:layout:')
export const IMPORTED_PREFERENCES_KEY = 'imported-preferences'

/** localStorage is a mirror. The committed import remains recoverable if its
 * mirror is full, and is applied again before the next application bootstrap. */
export async function applyImportedPreferences(): Promise<void> {
  const pending = await personalTransaction(['metadata'], 'readonly', tx => idbValue(tx.objectStore('metadata').get(IMPORTED_PREFERENCES_KEY)))
  if (!pending) return
  const storage = getLocalStorage()
  if (!storage) return
  try {
    for (const [key, value] of Object.entries(pending.preferences)) if (isBackupPreference(key) && typeof value === 'string') storage.setItem(key, value)
  } catch { return }
  await personalTransaction(['metadata'], 'readwrite', async tx => {
    const store = tx.objectStore('metadata'), current = await idbValue(store.get(IMPORTED_PREFERENCES_KEY))
    if (current?.id === pending.id) store.delete(IMPORTED_PREFERENCES_KEY)
  })
}
