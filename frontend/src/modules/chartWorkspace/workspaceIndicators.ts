import { computed, ref, watch, type Ref } from 'vue'
import type { Vela, InputValue } from '@luxalgo/vela'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import { registerStatePersistence } from '@luxalgo/vela/plugin'

export const WORKSPACE_INDICATORS = [
  { type: 'sma', label: 'MA', name: 'sma' },
  { type: 'ema', label: 'EMA', name: 'ema' },
  { type: 'rsi', label: 'RSI', name: 'rsi' },
  { type: 'volume', label: 'VOL', name: 'volume' },
  { type: 'bollinger-bands', label: 'BOLL', name: 'boll' },
  { type: 'macd', label: 'MACD', name: 'macd' },
  { type: 'average-true-range', label: 'ATR', name: 'atr' },
  { type: 'vwap', label: 'VWAP', name: 'vwap' },
  { type: 'average-directional-index', label: 'ADX', name: 'adx' },
] as const

type IndicatorInputs = Record<string, InputValue>
const inactive = new WeakMap<Vela, Map<string, IndicatorInputs[]>>()
function preferences(chart: Vela) {
  let saved = inactive.get(chart)
  if (!saved) { saved = new Map(); inactive.set(chart, saved) }
  return saved
}
// Keep disabled studies' settings in the layout without leaving empty panes on the chart.
registerStatePersistence({
  key: 'opentrading.indicatorShortcuts', scope: 'cell',
  serialize: ctx => Object.fromEntries(preferences(ctx.chart)),
  restore(payload, ctx) {
    const saved = new Map<string, IndicatorInputs[]>()
    if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
      for (const [type, inputs] of Object.entries(payload)) {
        if (WORKSPACE_INDICATORS.some(item => item.type === type) && Array.isArray(inputs) &&
          inputs.every(value => value && typeof value === 'object' && !Array.isArray(value))) saved.set(type, inputs)
      }
    }
    inactive.set(ctx.chart, saved)
  },
})

export function createWorkspaceIndicators(deps: {
  workspace: Readonly<Ref<VelaWorkspace | undefined>>
  onError: (error: unknown) => void
}) {
  const revision = ref(0)
  const refresh = () => { revision.value++ }
  const selected = computed(() => {
    revision.value
    return new Set(deps.workspace.value?.active?.chart.indicators()
      .filter(handle => handle.visible && handle.nativeType)
      .map(handle => handle.nativeType) ?? [])
  })
  const chartOffs = new Map<Vela, (() => void)[]>()
  let workspaceOffs: (() => void)[] = []
  function release() {
    workspaceOffs.forEach(off => off())
    workspaceOffs = []
    for (const offs of chartOffs.values()) offs.forEach(off => off())
    chartOffs.clear()
  }
  function bindCells() {
    const cells = deps.workspace.value?.cells() ?? []
    for (const [chart, offs] of chartOffs) {
      if (cells.some(cell => cell.chart === chart)) continue
      offs.forEach(off => off())
      chartOffs.delete(chart)
    }
    for (const { chart } of cells) {
      if (!chartOffs.has(chart)) chartOffs.set(chart, [
        chart.on('indicator:added', refresh), chart.on('indicator:removed', refresh),
        chart.on('indicator:visibility', refresh),
      ])
    }
    refresh()
  }
  const stopWatch = watch(deps.workspace, workspace => {
    release()
    if (workspace) {
      workspaceOffs = [workspace.on('cell:active', refresh), workspace.on('cell:created', bindCells),
        workspace.on('layout:changed', bindCells), workspace.on('state:changed', bindCells)]
      bindCells()
    }
    refresh()
  }, { immediate: true, flush: 'sync' })
  function toggle(type: string) {
    const workspace = deps.workspace.value
    if (!workspace || !WORKSPACE_INDICATORS.some(item => item.type === type)) return
    try {
      const chart = workspace.active.chart, saved = preferences(chart)
      const handles = chart.indicators().filter(handle => handle.nativeType === type)
      if (handles.some(handle => handle.visible)) {
        saved.set(type, handles.map(handle => ({ ...handle.inputValues() })))
        for (const handle of handles) handle.remove()
      } else if (handles.length) {
        // Reuse hidden instances from older layouts or the object list.
        for (const handle of handles) handle.setVisible(true)
      } else {
        for (const inputs of saved.get(type) ?? [{}]) {
          const before = new Set(chart.indicators().map(handle => handle.id))
          workspace.context().addNativeIndicator(type)
          chart.indicators().find(handle => handle.nativeType === type && !before.has(handle.id))?.setInputs(inputs)
        }
        saved.delete(type)
      }
      workspace.context().stateChanged()
      refresh()
    } catch (error) { deps.onError(error) }
  }
  function dispose() { stopWatch(); release() }
  return { selected, toggle, dispose }
}
