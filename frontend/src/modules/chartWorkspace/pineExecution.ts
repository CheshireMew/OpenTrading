import { ref } from 'vue'
import type { IndicatorHandle } from '@luxalgo/vela'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { PineDocuments } from './pineDocuments'
import { markScript } from './persistence'
import { checkPine } from './pineCompatibility.mjs'
import { cw } from './locale'
import type { WorkspaceDocument } from './api'

export function createPineExecution(deps: {
  workspace: () => VelaWorkspace | undefined
  documents: Pick<PineDocuments, 'selectedScript' | 'source' | 'scriptDirty' | 'scriptLoading' | 'saveScript' | 'selectionEpoch'>
  onError: (error: unknown) => void
  log: (message: string) => void
  dirty: () => void
}) {
  const executing = ref(false), scriptRunning = ref('')
  const pineError = ref<{ message: string; line?: number; column?: number } | null>(null)
  const pending = new Set<() => void>()
  let disposed = false, runEpoch = 0
  async function addPine() {
    const workspace = deps.workspace(), cell = workspace?.active, docs = deps.documents
    if (!cell || docs.scriptLoading.value || disposed) return
    const documentEpoch = docs.selectionEpoch()
    let script = docs.selectedScript.value
    if (docs.scriptDirty.value || !script) { script = await docs.saveScript(false); if (!script) return }
    if (disposed || documentEpoch !== docs.selectionEpoch() || deps.workspace()?.active !== cell || docs.source.value !== script.data.source) return
    return runScript(workspace!, cell, script)
  }
  async function addSavedScript(script: WorkspaceDocument) {
    const workspace = deps.workspace(), cell = workspace?.active
    if (!workspace || !cell || disposed || executing.value) return
    return runScript(workspace, cell, script)
  }
  async function runScript(workspace: VelaWorkspace, cell: NonNullable<VelaWorkspace['active']>, script: WorkspaceDocument) {
    const code = String(script.data.source), epoch = ++runEpoch
    executing.value = true
    pineError.value = null
    try {
      checkPine(code)
      const id = crypto.randomUUID()
      workspace!.context().addIndicator({ script: code, name: script.name, id, language: 'pine' })
      const handle = cell.chart.indicators().find(handle => handle.id === id)
      if (!handle) throw new Error(cw('cannotCreateIndicator'))
      const result = await waitForIndicator(handle)
      if (disposed || epoch !== runEpoch) { result?.remove(); return }
      markScript(cell.chart, id, script.id, script.version)
      scriptRunning.value = cw('scriptAdded', { version: script.version, cell: cell.id })
      deps.log(cw('scriptRunLog', { name: script.name, version: script.version, cell: cell.id }))
      deps.dirty()
      return true
    } catch (error) {
      if (disposed || epoch !== runEpoch) return
      const value = error as Error & { line?: number; column?: number }
      pineError.value = { message: value.message ?? String(error), line: value.line, column: value.column }
      scriptRunning.value = cw('keptPrevious')
      deps.onError(error)
      return false
    } finally { if (epoch === runEpoch) executing.value = false }
  }
  function waitForIndicator(handle: IndicatorHandle) {
    return new Promise<IndicatorHandle>((resolve, reject) => {
      let settled = false
      let ready = () => {}, failed = () => {}
      const finish = (error: Error | null) => {
        if (settled) return
        settled = true
        clearTimeout(timer); ready(); failed(); pending.delete(cancel)
        if (error) { handle.remove(); reject(error) } else resolve(handle)
      }
      const cancel = () => finish(new Error(cw('runCancelled')))
      const timer = setTimeout(() => finish(new Error(cw('scriptTimeout'))), 65000)
      ready = handle.on('ready', () => finish(null))
      failed = handle.on('error', ({ error }) => finish(error))
      pending.add(cancel)
    })
  }
  function cancelPine() {
    runEpoch++
    executing.value = false
    for (const cancel of pending) cancel()
    pending.clear()
    if (!disposed) deps.log(cw('stoppedAdding'))
  }
  function dispose() { disposed = true; cancelPine() }
  return { executing, scriptRunning, pineError, addPine, addSavedScript, cancelPine, dispose }
}
