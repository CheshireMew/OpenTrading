import { computed, ref, watch } from 'vue'
import { chartApi, type WorkspaceDocument } from './api'
import { deleteDraft, readDraft, writeDraft } from './drafts'
import { cw } from './locale'

type Dependencies = {
  requestName: (title: string, value: string) => Promise<string | null>
  openEditor: () => void
  onError: (error: unknown) => void
}
type ScriptDraft = { source: string; version?: number; base?: string; pending?: boolean }

export function createPineDocuments(deps: Dependencies) {
  const scripts = ref<WorkspaceDocument[]>([])
  const scriptId = ref('opentrading-v7-2'), source = ref(''), scriptDirty = ref(false), scriptLoading = ref(false)
  const selectedScript = computed(() => scripts.value.find(script => script.id === scriptId.value))
  const scriptConflict = ref(false)
  const managing = ref(false)
  let baseVersion = 0, baseSource = ''
  let disposed = false, editorReady = false, epoch = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let pendingDraft: { id: string; draft: ScriptDraft } | undefined
  let writes: Promise<WorkspaceDocument | undefined> = Promise.resolve(undefined)
  let draftWrites = Promise.resolve()

  const captureDraft = (): ScriptDraft => ({ source: source.value, version: baseVersion, base: baseSource, pending: source.value !== baseSource })
  const storeDraft = (id: string, draft: ScriptDraft) => {
    const result = draftWrites.then(() => writeDraft('script:' + id, draft, 'window'))
    draftWrites = result.catch(deps.onError)
    return result
  }
  async function flushDraft() {
    clearTimeout(timer)
    const draft = pendingDraft
    pendingDraft = undefined
    if (draft) await storeDraft(draft.id, draft.draft)
  }
  async function openScript() {
    const request = ++epoch, script = selectedScript.value
    editorReady = false
    scriptLoading.value = true
    try {
      await flushDraft()
      if (!script) return
      const draft = await readDraft<ScriptDraft>('script:' + script.id, 'window')
      if (disposed || request !== epoch || scriptId.value !== script.id) return
      const remote = String(script.data.source)
      const pending = draft && draft.pending !== false && draft.source !== remote && (!script.readonly || draft.source.trim())
      baseVersion = pending ? draft.version ?? 0 : script.version
      baseSource = pending ? draft.base ?? remote : remote
      scriptConflict.value = Boolean(pending && (baseVersion !== script.version || baseSource !== remote))
      source.value = pending ? draft.source : remote
      editorReady = true
      scriptDirty.value = source.value !== script.data.source
    } catch (error) { if (!disposed && request === epoch) deps.onError(error) }
    finally { if (request === epoch) scriptLoading.value = false }
  }
  async function saveScript(asNew: boolean): Promise<WorkspaceDocument | undefined> {
    if (scriptLoading.value || managing.value || disposed) return
    const old = selectedScript.value, originId = scriptId.value, request = epoch, code = source.value
    const needsName = asNew || !old || old.readonly || scriptConflict.value
    const name = needsName ? await deps.requestName(cw('scriptName'), old ? cw('copyName', { name: old.name }) : cw('myScript')) : old.name
    if (!name || disposed) return
    const id = needsName ? crypto.randomUUID() : old!.id
    const operation = writes.then(async () => {
      try {
        const previous = scripts.value.find(item => item.id === id)
        const saved = await chartApi.save('scripts', id, { name, data: { source: code, language: 'pine' }, expected_version: needsName ? 0 : previous?.version ?? old!.version })
        if (disposed) return saved
        scripts.value = [saved, ...scripts.value.filter(item => item.id !== id)]
        const active = request === epoch && scriptId.value === originId
        if (active) {
          baseVersion = saved.version; baseSource = code; scriptConflict.value = false
          scriptId.value = id; scriptDirty.value = source.value !== code
          pendingDraft = undefined; clearTimeout(timer)
        }
        if (active || needsName) await storeDraft(id, { source: active ? source.value : code, version: saved.version, base: code, pending: active && source.value !== code })
        return saved
      } catch (error) {
        if (!disposed && request === epoch) {
          if ((error as { status?: number }).status === 409) scriptConflict.value = true
          deps.onError(error)
        }
      }
    })
    writes = operation
    return operation
  }
  function setNewSource(code: string) {
    baseVersion = 0; baseSource = ''; scriptConflict.value = false
    editorReady = true
    scriptId.value = ''
    source.value = code
    scriptDirty.value = true
    deps.openEditor()
  }
  async function renameScript() {
    const old=selectedScript.value
    if(!old||old.readonly||managing.value||scriptLoading.value)return
    const name=await deps.requestName(cw('scriptName'),old.name)
    if(!name||disposed)return
    managing.value=true
    const operation=writes.then(async()=>{
      const latest=scripts.value.find(item=>item.id===old.id)!
      const saved=await chartApi.save('scripts',old.id,{name,data:latest.data,expected_version:latest.version})
      scripts.value=scripts.value.map(item=>item.id===saved.id?saved:item)
      if(scriptId.value===saved.id){baseVersion=saved.version;await storeDraft(saved.id,captureDraft())}
      return saved
    }).catch(error=>{deps.onError(error);return undefined})
    writes=operation
    try{await operation}finally{managing.value=false}
  }
  async function deleteScript() {
    const old=selectedScript.value
    if(!old||old.readonly||managing.value||scriptLoading.value)return
    managing.value=true
    try{
      await writes
      const latest=scripts.value.find(item=>item.id===old.id)!
      await chartApi.remove('scripts',old.id,latest.version)
      if(scriptId.value===old.id){epoch++;editorReady=false;pendingDraft=undefined;clearTimeout(timer)}
      await draftWrites;await deleteDraft('script:'+old.id)
      scripts.value=scripts.value.filter(item=>item.id!==old.id)
      if(scriptId.value===old.id){scriptId.value=scripts.value[0]?.id??'';source.value='';scriptDirty.value=false;scriptConflict.value=false;await openScript()}
    }catch(error){deps.onError(error)}finally{managing.value=false}
  }
  async function useSavedScript() {
    const id = scriptId.value, request = ++epoch
    scriptLoading.value = true
    try {
      await flushDraft()
      const saved = await chartApi.document('scripts', id)
      if (disposed || request !== epoch) return
      editorReady = false
      scripts.value = [saved, ...scripts.value.filter(item => item.id !== id)]
      baseVersion = saved.version; baseSource = String(saved.data.source)
      source.value = baseSource; scriptConflict.value = false; scriptDirty.value = false
      editorReady = true
      await storeDraft(id, captureDraft())
    } catch (error) { if (!disposed && request === epoch) deps.onError(error) }
    finally { if (request === epoch) scriptLoading.value = false }
  }
  function newScript(kind: string) {
    epoch++
    scriptLoading.value = false
    void flushDraft().catch(deps.onError)
    setNewSource(kind === 'indicator'
      ? '//@version=6\nindicator("' + cw('myIndicator') + '", overlay=true)\nlength = input.int(20, "' + cw('timeframe') + '")\nplot(ta.ema(close, length), color=color.orange)\n'
      : '//@version=6\nstrategy("' + cw('crossStrategy') + '", overlay=true, initial_capital=10000)\nfast = ta.ema(close, input.int(10, "' + cw('fast') + '"))\nslow = ta.ema(close, input.int(30, "' + cw('slow') + '"))\nplot(fast, color=color.orange)\nplot(slow, color=color.blue)\nif ta.crossover(fast, slow)\n    strategy.entry("Long", strategy.long)\nif ta.crossunder(fast, slow)\n    strategy.close("Long")\n')
  }
  async function importScript(event: Event) {
    const input = event.target as HTMLInputElement, file = input.files?.[0]
    if (!file) return
    const request = ++epoch
    await flushDraft()
    const code = await file.text()
    input.value = ''
    if (!disposed && request === epoch) setNewSource(code)
  }
  function exportScript() {
    const url = URL.createObjectURL(new Blob([source.value], { type: 'text/plain;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = (selectedScript.value?.name ?? 'indicator') + '.pine'
    link.click()
    URL.revokeObjectURL(url)
  }
  async function initialize(documents: WorkspaceDocument[]) {
    if (disposed) return
    scripts.value = documents
    const last = await readDraft<string>('last-script', 'window')
    if (disposed) return
    if (last === '') {
      const draft = await readDraft<ScriptDraft>('script:new', 'window')
      if (disposed) return
      if (draft) { setNewSource(draft.source); return }
    }
    if (last && scripts.value.some(script => script.id === last)) scriptId.value = last
    if(!scripts.value.some(script=>script.id===scriptId.value))scriptId.value=scripts.value[0]?.id??''
    await openScript()
  }
  const stopSource = watch(source, value => {
    if (!editorReady || disposed) return
    scriptDirty.value = value !== selectedScript.value?.data.source
    pendingDraft = { id: scriptId.value || 'new', draft: captureDraft() }
    clearTimeout(timer)
    timer = setTimeout(() => void flushDraft().catch(deps.onError), 400)
  }, { flush: 'sync' })
  const stopSelection = watch(scriptId, value => { if (!disposed) void writeDraft('last-script', value, 'window').catch(deps.onError) })
  function dispose() {
    disposed = true
    epoch++
    stopSource(); stopSelection()
    if (editorReady && scriptDirty.value) pendingDraft = { id: scriptId.value || 'new', draft: captureDraft() }
    void flushDraft().catch(deps.onError)
  }
  return { scripts, scriptId, source, scriptDirty, scriptLoading, scriptConflict, useSavedScript, selectedScript, managing, renameScript, deleteScript, openScript, saveScript,
    newScript, importScript, exportScript, initialize, dispose, selectionEpoch: () => epoch, isDisposed: () => disposed }
}

export type PineDocuments = ReturnType<typeof createPineDocuments>
