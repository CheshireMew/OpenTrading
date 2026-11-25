import { createBrowserPineStore, restorePineRun, PINE_STORES, type SavedPineRun } from './browserPineStore'
import { createBrowserNotificationStore } from './browserNotificationStore'
import { personalDatabase, personalTransaction } from './browserDatabase'
import { RESEARCH_STORES, researchTransaction, researchSnapshot, restoreResearch } from './browserResearchStore'
import type { ResearchState } from './researchSchema'

export const browserPineStore = createBrowserPineStore(personalDatabase)
export const browserNotificationStore = createBrowserNotificationStore(personalDatabase)
export async function browserRecords(): Promise<Record<string, unknown>> {
  const research = await researchTransaction('readonly', researchSnapshot)
  return { research, ...await browserPineStore.snapshot() }
}

export async function restoreBrowserRecords(records: Record<string, unknown>) {
  await personalTransaction([...RESEARCH_STORES, ...PINE_STORES], 'readwrite', tx => {
    return restoreBrowserRecordsInTransaction(tx, records)
  })
}
export async function restoreBrowserRecordsInTransaction(tx: IDBTransaction, records: Record<string, unknown>) {
  if (records.research) await restoreResearch(tx, records.research as ResearchState)
  for (const [key, value] of Object.entries(records)) if (key.startsWith('pine-run:')) {
    await restorePineRun(tx, value as SavedPineRun)
  }
}
