import { browserWorkspaceDocuments, waitForWorkspaceWrites } from './api'
import { BROWSER_DOCUMENT_KINDS, restoreBrowserDocuments, type BrowserDocumentEntry } from './browserDocuments'
import { readDraft, draftStorageKey } from './drafts'
import { cw } from './locale'
import { getLocalStorage } from '@/utils/storage'
import { browserRecords, restoreBrowserRecordsInTransaction } from '@/modules/personal/browserStore'
import { personalTransaction } from '@/modules/personal/browserDatabase'
import { RESEARCH_STORES } from '@/modules/personal/browserResearchStore'
import { validateResearchBackup } from '@/modules/personal/researchSchema'
import { PINE_STORES } from '@/modules/personal/browserPineStore'
import { isBackupPreference, applyImportedPreferences, IMPORTED_PREFERENCES_KEY } from '@/modules/personal/browserPreferences'

type Backup = {
  format: 'opentrading-personal-data'
  version: 1
  createdAt: number
  documents: BrowserDocumentEntry[]
  preferences: Record<string, string>
  selection: { layout?: string; script?: string }
  records?: Record<string, unknown>
}
const preferenceKey = isBackupPreference

export async function exportBrowserData(): Promise<Backup> {
  await waitForWorkspaceWrites()
  const documents = await browserWorkspaceDocuments.snapshot(), preferences: Record<string, string> = {}
  const storage = getLocalStorage()
  if (storage) for (let index = 0; index < storage.length; index++) {
    const key = storage.key(index)
    if (key && preferenceKey(key)) preferences[key] = storage.getItem(key)!
  }
  return { format: 'opentrading-personal-data', version: 1, createdAt: Date.now(), documents, preferences,
    records: await browserRecords(),
    selection: { layout: await readDraft<string>('last-layout'), script: await readDraft<string>('last-script', 'window') } }
}

export async function importBrowserData(text: string) {
  let backup: Backup
  try {
    backup = JSON.parse(text, (key, value) => {
      if (['__proto__', 'prototype', 'constructor'].includes(key)) throw new Error('Invalid object key')
      return value
    })
  } catch { throw new Error(cw('browserBackupInvalid')) }
  const valid = backup && backup.format === 'opentrading-personal-data' && backup.version === 1 && Array.isArray(backup.documents)
  if (!valid) throw new Error(cw('browserBackupInvalid'))
  const keys = new Set<string>()
  for (const row of backup.documents) {
    const doc = row?.document, key = row?.kind + ':' + doc?.id
    if (!BROWSER_DOCUMENT_KINDS.includes(row?.kind) || !doc || typeof doc.id !== 'string' || !doc.id || typeof doc.name !== 'string' || !doc.name.trim()
      || !Number.isInteger(doc.version) || doc.version < 1 || !Number.isFinite(doc.updated_at) || !doc.data || typeof doc.data !== 'object' || Array.isArray(doc.data)
      || (doc.readonly !== undefined && typeof doc.readonly !== 'boolean') || keys.has(key)
      || (row.kind === 'scripts' && typeof doc.data.source !== 'string')) throw new Error(cw('browserBackupInvalid'))
    keys.add(key)
  }
  if (backup.records) {
    if (typeof backup.records !== 'object' || Array.isArray(backup.records)) throw new Error(cw('browserBackupInvalid'))
    for (const [key, record] of Object.entries(backup.records) as [string, any][]) {
      if (key === 'research') {
        validateResearchBackup(record)
      } else {
        const run = record?.run, request = run?.request
        if (!key.startsWith('pine-run:') || key !== 'pine-run:' + run?.id || !request || !Number.isFinite(run.created_at)
          || !['queued', 'loading', 'running', 'completed', 'failed', 'cancelled', 'interrupted'].includes(run.status)
          || typeof request.script_id !== 'string' || !Number.isInteger(request.script_version) || request.script_version < 1
          || typeof request.symbol !== 'string' || typeof request.timeframe !== 'string' || !Number.isFinite(request.start) || !Number.isFinite(request.end) || request.start >= request.end
          || !run.summary || !run.provenance || run.status === 'completed' && !record.result) throw new Error(cw('browserBackupInvalid'))
      }
    }
  }
  await waitForWorkspaceWrites()
  await personalTransaction(['documents', 'revisions', 'metadata', 'drafts', ...RESEARCH_STORES, ...PINE_STORES], 'readwrite', async tx => {
    const ids = await restoreBrowserDocuments(tx, backup.documents)
    if (backup.records) await restoreBrowserRecordsInTransaction(tx, backup.records)
    const preferences = Object.fromEntries(Object.entries(backup.preferences ?? {}).filter(([key, value]) => preferenceKey(key) && typeof value === 'string'))
    tx.objectStore('metadata').put({ id: crypto.randomUUID(), preferences }, IMPORTED_PREFERENCES_KEY)
    if (typeof backup.selection?.layout === 'string') tx.objectStore('drafts').put(ids['layouts:' + backup.selection.layout] ?? backup.selection.layout, draftStorageKey('last-layout'))
    if (typeof backup.selection?.script === 'string') tx.objectStore('drafts').put(ids['scripts:' + backup.selection.script] ?? backup.selection.script, draftStorageKey('last-script', 'window'))
  })
  // Preferences cannot turn a committed data import into a reported failure.
  await applyImportedPreferences().catch(() => {})
  return backup.documents.length
}
