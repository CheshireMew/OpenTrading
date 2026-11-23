import { ref } from 'vue'
import { chartApi, type WorkspaceDocument } from './api'
import { readDraft, writeDraft } from './drafts'
import { migrateWorkspaceState } from './legacyState'
import { mergeLayout, sameLayout } from './layoutMerge'
import { cw } from './locale'

type LayoutData = Record<string, any>
type LayoutDraft = { version: number; base?: LayoutData; data: LayoutData; pending: boolean }
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value))
const isConflict = (error: unknown) => typeof error === 'object' && error !== null && 'status' in error && error.status === 409

export function createWorkspaceLayouts(deps: {
  snapshot: () => LayoutData | undefined
  apply: (data: LayoutData) => void
  requestName: (title: string, value: string) => Promise<string | null>
  onError: (error: unknown) => void
}) {
  const layouts = ref<WorkspaceDocument[]>([]), layoutId = ref('default'), saveStatus = ref('saved')
  let restoring = false, disposed = false, ready = false, selectionEpoch = 0
  let writes = Promise.resolve()
  const pending = new Map<string, LayoutData>(), observed = new Map<string, LayoutData>()
  const bases = new Map<string, WorkspaceDocument | undefined>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  const document = (id: string) => layouts.value.find(item => item.id === id)
  const baseDocument = (id: string) => bases.has(id) ? bases.get(id) : document(id)
  function remember(saved: WorkspaceDocument) { layouts.value = [saved, ...layouts.value.filter(item => item.id !== saved.id)] }
  function restore(data: LayoutData) {
    restoring = true
    try {
      deps.apply(copy(migrateWorkspaceState(data)))
      observed.set(layoutId.value, copy(deps.snapshot() ?? data))
    } finally { restoring = false }
  }
  function draft(id: string, data: LayoutData, unsaved: boolean) {
    const base = baseDocument(id)
    return writeDraft('layout:' + id, { version: base?.version ?? 0, base: base?.data ?? {}, data, pending: unsaved })
  }
  function schedule(id: string, delay = 700) {
    clearTimeout(timers.get(id))
    if (!disposed) timers.set(id, setTimeout(() => { timers.delete(id); void enqueue(id) }, delay))
  }
  function capture() {
    if (!ready || restoring || disposed) return
    const data = deps.snapshot(), id = layoutId.value
    if (!data) return
    const snapshot = copy(data)
    if (sameLayout(snapshot, observed.get(id))) return
    observed.set(id, snapshot)
    if (!pending.has(id)) bases.set(id, document(id))
    pending.set(id, snapshot)
    saveStatus.value = 'saving'
    void draft(id, snapshot, true).catch(deps.onError)
  }
  function dirty() { capture(); if (pending.has(layoutId.value)) schedule(layoutId.value) }
  async function flush(id: string) {
    const captured = pending.get(id)
    if (!captured) return
    let data = captured, previous = baseDocument(id)
    try {
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const saved = previous && sameLayout(data, previous.data) ? previous : await chartApi.save('layouts', id, {
            name: previous?.name ?? cw('defaultLayout'), data, expected_version: previous?.version ?? 0,
          })
          // Keep edits made during the request, together with any remote fields
          // merged by the conflict retry. Never acknowledge a newer local edit.
          const latest = mergeLayout(captured, pending.get(id) ?? captured, saved.data)
          remember(saved)
          if (sameLayout(latest, saved.data)) { pending.delete(id); bases.delete(id) }
          else { pending.set(id, latest); bases.set(id, saved) }
          const visible = deps.snapshot()
          if (!disposed && layoutId.value === id && visible && !sameLayout(latest, copy(visible))) restore(latest)
          await draft(id, latest, pending.has(id))
          if (!disposed && layoutId.value === id) saveStatus.value = pending.has(id) ? 'saving' : 'saved'
          if (pending.has(id)) schedule(id)
          return
        } catch (error) {
          if (!isConflict(error)) throw error
          const latest = await chartApi.document('layouts', id)
          data = mergeLayout(previous?.data ?? {}, data, latest.data)
          previous = latest
        }
      }
      // Another active window may win more than once. Retain the draft and
      // retry quietly, without refreshing or interrupting the current chart.
      schedule(id, 1500)
    } catch (error) {
      if (!disposed) { if (layoutId.value === id) saveStatus.value = 'unsaved'; deps.onError(error) }
    }
  }
  function enqueue(id: string) {
    clearTimeout(timers.get(id)); timers.delete(id)
    const operation = writes.then(() => flush(id))
    writes = operation
    return operation
  }
  async function saveNow() {
    if (!ready || restoring || disposed) return
    capture()
    await enqueue(layoutId.value)
  }
  async function switchLayout(id: string) {
    const epoch = ++selectionEpoch
    await saveNow()
    try {
      const documents = await chartApi.documents('layouts'), selected = documents.find(item => item.id === id)
      if (!selected || disposed || epoch !== selectionEpoch) return
      const local = pending.get(id)
      const merged = local ? mergeLayout(baseDocument(id)?.data ?? {}, local, selected.data) : selected.data
      layouts.value = documents
      layoutId.value = id
      restore(merged)
      if (local) { pending.set(id, merged); bases.set(id, selected); schedule(id) }
      saveStatus.value = local ? 'saving' : 'saved'
      await writeDraft('last-layout', id)
    } catch (error) { if (!disposed && epoch === selectionEpoch) deps.onError(error) }
  }
  async function saveAsLayout() {
    const epoch = selectionEpoch
    await saveNow()
    const name = await deps.requestName(cw('layoutName'), cw('myLayout'))
    if (!name || disposed || epoch !== selectionEpoch) return
    const data = deps.snapshot()
    if (!data) return
    try {
      const saved = await chartApi.save('layouts', crypto.randomUUID(), { name, data, expected_version: 0 })
      if (disposed) return
      remember(saved)
      if (epoch !== selectionEpoch) return
      layoutId.value = saved.id
      observed.set(saved.id, copy(data))
      await writeDraft('last-layout', saved.id)
      saveStatus.value = 'saved'
    } catch (error) { if (!disposed) deps.onError(error) }
  }
  async function initialize(documents: WorkspaceDocument[]) {
    ready = false
    layouts.value = documents
    const last = await readDraft<string>('last-layout')
    if (disposed) return
    const selected = layouts.value.find(item => item.id === last) ?? layouts.value[0]
    layoutId.value = selected?.id ?? 'default'
    const id = layoutId.value, local = await readDraft<LayoutDraft>('layout:' + id)
    if (disposed) return
    let data = selected?.data
    if (local?.pending) {
      const base = local.base ?? (local.version === selected?.version ? selected.data : local.version > 0
        ? (await chartApi.document('layouts', id, local.version)).data : {})
      if (disposed) return
      data = mergeLayout(base, local.data, data ?? {})
    }
    if (data) restore(data)
    else observed.set(id, copy(deps.snapshot() ?? {}))
    ready = true
    if (local?.pending && data) {
      pending.set(id, copy(data))
      bases.set(id, selected)
      saveStatus.value = 'saving'
      await enqueue(id)
    }
  }
  function retryPending() { for (const id of pending.keys()) void enqueue(id) }
  if (typeof window !== 'undefined') {
    window.addEventListener('online', retryPending)
    window.addEventListener('focus', retryPending)
  }
  function dispose() {
    if (disposed) return
    capture()
    disposed = true; selectionEpoch++
    for (const timer of timers.values()) clearTimeout(timer)
    if (typeof window !== 'undefined') {
      window.removeEventListener('online', retryPending)
      window.removeEventListener('focus', retryPending)
    }
    // Only flush actual edits. Merely closing an idle window must not create a
    // new revision or overwrite another window's more recent preferences.
    for (const id of pending.keys()) void enqueue(id)
  }
  return { layouts, layoutId, saveStatus, dirty, saveNow, saveAsLayout, switchLayout, initialize, dispose }
}
