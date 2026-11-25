import { computed, ref, shallowRef, type Ref } from 'vue'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import { getLocalStorage } from '@/utils/storage'
import { WorkspaceRenderer } from './chartPresentation'
import { cursorIcons, cursorImage, cursorModes, type CursorMode } from './cursorIcons'
import { CursorTrail } from './cursorTrail'

type Cell = ReturnType<VelaWorkspace['cells']>[number]
type NavigationMode = 'cross' | 'dot' | 'arrow'
const STORAGE_KEY = 'opentrading.chart.cursor-mode'
const isNavigation = (mode: CursorMode): mode is NavigationMode => ['cross', 'dot', 'arrow'].includes(mode)

export function createWorkspaceCursor(deps: { workspace: Ref<VelaWorkspace | undefined>; host: Ref<HTMLElement | undefined> }) {
  let initial: CursorMode = 'cross', navigation: NavigationMode = 'cross'
  try {
    const saved = JSON.parse(getLocalStorage()?.getItem(STORAGE_KEY) ?? 'null')
    if (cursorModes.includes(saved?.mode)) initial = saved.mode
    if (['cross', 'dot', 'arrow'].includes(saved?.navigation)) navigation = saved.navigation
  } catch { /* A missing or invalid preference uses the standard crosshair. */ }
  const mode = ref<CursorMode>(initial), toolbarTarget = shallowRef<HTMLElement>(), version = ref(0)
  const bindings = new Map<Cell['chart'], { cell: Cell; update: () => void; clear: () => void; dispose: () => void }>()
  const disposers: (() => void)[] = []
  let applying = false, toolbarObserver: MutationObserver | undefined
  const active = computed(() => {
    void version.value
    const chart = deps.workspace.value?.active.chart
    return !!chart && !chart.drawings.getTool() && chart.drawings.getMode() !== 'measure'
  })

  function remember() {
    try { getLocalStorage()?.setItem(STORAGE_KEY, JSON.stringify({ mode: mode.value, navigation })) } catch { /* Session selection still works when storage is unavailable. */ }
  }
  function update() { version.value++; for (const binding of bindings.values()) binding.update() }
  function choose(value: CursorMode) {
    mode.value = value
    if (isNavigation(value)) navigation = value
    remember()
    for (const binding of bindings.values()) binding.clear()
    applyActive()
  }
  function applyActive() {
    const chart = deps.workspace.value?.active.chart
    if (!chart) return
    applying = true
    try {
      chart.drawings.setTool(null)
      chart.drawings.setMode(mode.value === 'eraser' ? 'eraser' : null)
    } finally { applying = false }
    update()
  }
  function nativeChanged(cell: Cell) {
    if (applying || deps.workspace.value?.active.chart !== cell.chart) return
    const tool = cell.chart.drawings.getTool(), nativeMode = cell.chart.drawings.getMode()
    if (nativeMode === 'eraser' && mode.value !== 'eraser') {
      mode.value = 'eraser'; remember()
    } else if ((tool || nativeMode === 'measure' || nativeMode === null && mode.value === 'eraser') && !isNavigation(mode.value)) {
      mode.value = navigation; remember()
    }
    for (const binding of bindings.values()) binding.clear()
    update()
  }

  function bind(cell: Cell) {
    const surface = WorkspaceRenderer.forHost(cell.host)?.cursorSurface
    if (!surface) return
    const { plot, canvas } = surface
    canvas.dataset.cwCursorLayer = ''
    plot.style.setProperty('--cw-eraser-pointer', cursorImage(cursorIcons.eraser, '5 19'))
    plot.style.setProperty('--cw-dot-pointer', cursorImage(cursorIcons.dot, '12 12'))
    const bounds = () => {
      const style = getComputedStyle(cell.host)
      return { left: parseFloat(style.getPropertyValue('--vela-toolbar-gutter')) || 0,
        right: plot.clientWidth - (parseFloat(style.getPropertyValue('--vela-scale-gutter')) || 0), bottom: Math.max(0, plot.clientHeight - 22) }
    }
    const point = (event: PointerEvent) => { const rect = plot.getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top } }
    const inPlot = (event: PointerEvent) => {
      const p = point(event), b = bounds()
      return p.x >= b.left && p.x <= b.right && p.y >= 0 && p.y < b.bottom && event.target instanceof HTMLCanvasElement
    }
    const idle = () => !cell.chart.drawings.getTool() && cell.chart.drawings.getMode() !== 'measure'
    const trail = new CursorTrail(plot, bounds)
    let pointer: number | null = null
    const finish = () => {
      if (pointer !== null && cell.host.hasPointerCapture(pointer)) cell.host.releasePointerCapture(pointer)
      pointer = null
      trail.finish()
    }
    const clear = () => { finish(); trail.clear() }
    const refresh = () => {
      const selected = idle() ? mode.value : 'drawing'
      plot.dataset.cwCursorMode = selected
      if (plot.dataset.cwPointer) plot.dataset.cwPointer = selected
    }
    const down = (event: PointerEvent) => {
      if (mode.value !== 'highlight' || !idle() || event.button !== 0 || !inPlot(event) || event.pointerType === 'mouse' && !event.altKey) return
      deps.workspace.value?.setActiveCell(cell.id)
      event.preventDefault(); event.stopImmediatePropagation()
      finish()
      pointer = event.pointerId
      cell.host.setPointerCapture(pointer)
      trail.begin(point(event))
    }
    const move = (event: PointerEvent) => {
      if (pointer !== event.pointerId) return
      event.preventDefault(); event.stopImmediatePropagation()
      for (const sample of event.getCoalescedEvents?.() ?? [event]) trail.move(point(sample))
      trail.move(point(event))
    }
    const up = (event: PointerEvent) => {
      if (pointer !== event.pointerId) return
      event.preventDefault(); event.stopImmediatePropagation()
      trail.move(point(event)); finish()
    }
    const hover = (event: PointerEvent) => {
      // The native input handles axes, pane separators and drawing hit tests
      // first. Preserve those resize/selection pointers outside ordinary data.
      const cursor = event.target instanceof HTMLElement ? event.target.style.cursor : ''
      if (idle() && inPlot(event) && !cursor.includes('resize') && (mode.value === 'eraser' || cursor !== 'pointer')) plot.dataset.cwPointer = mode.value
      else delete plot.dataset.cwPointer
    }
    const leave = () => { delete plot.dataset.cwPointer }
    const visibility = () => { if (document.hidden) clear() }
    cell.host.addEventListener('pointerdown', down, true)
    cell.host.addEventListener('pointermove', move, true)
    cell.host.addEventListener('pointerup', up, true)
    cell.host.addEventListener('pointercancel', up, true)
    cell.host.addEventListener('lostpointercapture', finish)
    plot.addEventListener('pointermove', hover)
    plot.addEventListener('pointerleave', leave)
    document.addEventListener('visibilitychange', visibility)
    const off = [cell.chart.on('drawing:tool', () => nativeChanged(cell)), cell.chart.on('drawing:mode', () => nativeChanged(cell)),
      cell.chart.on('viewport:changed', clear), cell.chart.on('load:start', clear)]
    refresh()
    bindings.set(cell.chart, { cell, update: refresh, clear, dispose: () => {
      clear(); trail.dispose(); off.forEach(dispose => dispose())
      cell.host.removeEventListener('pointerdown', down, true)
      cell.host.removeEventListener('pointermove', move, true)
      cell.host.removeEventListener('pointerup', up, true)
      cell.host.removeEventListener('pointercancel', up, true)
      cell.host.removeEventListener('lostpointercapture', finish)
      plot.removeEventListener('pointermove', hover); plot.removeEventListener('pointerleave', leave)
      document.removeEventListener('visibilitychange', visibility)
      delete plot.dataset.cwCursorMode; delete plot.dataset.cwPointer; delete canvas.dataset.cwCursorLayer
    } })
  }

  function syncCells() {
    const cells = deps.workspace.value?.cells() ?? []
    for (const [chart, binding] of bindings) if (!cells.some(cell => cell.chart === chart)) { binding.dispose(); bindings.delete(chart) }
    for (const cell of cells) if (!bindings.has(cell.chart)) bind(cell)
    update()
  }
  function initialize() {
    const workspace = deps.workspace.value, root = deps.host.value?.querySelector<HTMLElement>('.vela-ws-toolbar .vela-dtb')
    if (!workspace || !root) return
    const mount = document.createElement('div')
    mount.className = 'cw-cursor-mount'
    toolbarTarget.value = mount
    const attach = () => {
      const original = [...root.children].find(element => element.matches('button.vela-dtb-btn:not(.vela-dtb-collapse)'))
      original?.classList.add('cw-native-cursor')
      if (root.firstElementChild !== mount) root.prepend(mount)
    }
    attach()
    toolbarObserver = new MutationObserver(attach)
    toolbarObserver.observe(root, { childList: true })
    syncCells(); applyActive()
    disposers.push(workspace.on('cell:created', syncCells), workspace.on('layout:changed', syncCells),
      workspace.on('cell:active', () => { syncCells(); applyActive() }))
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || (event.target as HTMLElement)?.closest('input,textarea,select,[contenteditable=true]')) return
      if (mode.value === 'highlight' || mode.value === 'eraser') { choose(navigation); event.preventDefault() }
    }
    document.addEventListener('keydown', escape)
    disposers.push(() => document.removeEventListener('keydown', escape))
  }
  function dispose() {
    toolbarObserver?.disconnect()
    disposers.splice(0).forEach(dispose => dispose())
    for (const binding of bindings.values()) binding.dispose()
    bindings.clear(); toolbarTarget.value?.remove(); toolbarTarget.value = undefined
  }
  return { mode, active, toolbarTarget, choose, initialize, dispose }
}

export type WorkspaceCursor = ReturnType<typeof createWorkspaceCursor>
