import { browserWorkspaceDocuments, waitForWorkspaceWrites } from './api'
import { BROWSER_DOCUMENT_KINDS, type BrowserDocumentEntry } from './browserDocuments'
import { readDraft, writeDraft } from './drafts'
import { cw } from './locale'
import { getLocalStorage } from '@/utils/storage'
import { browserRecords, restoreBrowserRecords } from '@/modules/personal/browserStore'

type Backup = {
  format: 'opentrading-personal-data'
  version: 1
  createdAt: number
  documents: BrowserDocumentEntry[]
  preferences: Record<string, string>
  selection: { layout?: string; script?: string }
  records?: Record<string, unknown>
}
const preferenceKey = (key: string) => ['locale', 'theme', 'opentrading_user_preferences', 'opentrading:macro-signals:section', 'opentrading:asset-observation-symbol'].includes(key) || key.startsWith('opentrading:layout:')

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
        if (!record || typeof record !== 'object') throw new Error(cw('browserBackupInvalid'))
        for (const kind of ['watchlists', 'items', 'notes', 'alerts', 'events', 'screeners', 'screenerRuns']) {
          if (!Array.isArray(record[kind]) || record[kind].some((row: any) => !row || typeof row.id !== 'string' || !row.id)) throw new Error(cw('browserBackupInvalid'))
        }
      } else if (!key.startsWith('pine-run:') || !record?.run || key !== 'pine-run:' + record.run.id || !record.run.request || typeof record.run.status !== 'string') throw new Error(cw('browserBackupInvalid'))
    }
  }
  await waitForWorkspaceWrites()
  const ids = await browserWorkspaceDocuments.restore(backup.documents)
  if (backup.records) await restoreBrowserRecords(backup.records)
  const storage = getLocalStorage()
  for (const [key, value] of Object.entries(backup.preferences ?? {})) if (storage && preferenceKey(key) && typeof value === 'string') storage.setItem(key, value)
  if (typeof backup.selection?.layout === 'string') await writeDraft('last-layout', ids['layouts:' + backup.selection.layout] ?? backup.selection.layout)
  if (typeof backup.selection?.script === 'string') await writeDraft('last-script', ids['scripts:' + backup.selection.script] ?? backup.selection.script, 'window')
  return backup.documents.length
}
