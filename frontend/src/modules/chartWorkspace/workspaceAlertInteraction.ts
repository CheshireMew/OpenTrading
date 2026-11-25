import { ref, shallowRef, watch, type Ref } from 'vue'
import { registerWidgetAction } from '@luxalgo/vela/plugin'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { ResearchAlertResponse } from '@/modules/research/contracts'
import { WorkspaceRenderer } from './chartPresentation'
import { fromVela } from './provider'
import { cw, formatNumber } from './locale'
import type { PriceAlertGeometry } from './priceAlertLayer'
import { finishedPriceAlert } from './priceAlertRules'

type AlertPoint = { symbolId: string; price: number }
export function createWorkspaceAlertInteraction(deps: {
  workspace: Ref<VelaWorkspace | undefined>; rulesForCell: (id: string) => ResearchAlertResponse[]
  roundPrice: (price: number, id: string) => number; busy: () => boolean; invalidate: () => void; attached: () => void
  startForm: (point?: AlertPoint) => void; edit: (alert: ResearchAlertResponse) => void
  editId: (id: string) => void; removeId: (id: string) => void
  movePrice: (alert: ResearchAlertResponse, price: number) => Promise<void>
}) {
  const selectedId = ref(''), draggingId = ref('')
  const overlays = shallowRef<({ cellId: string; host: HTMLElement } & PriceAlertGeometry)[]>([])
  let pending: AlertPoint | undefined, pendingAlert: string | undefined
  let drag: { alert: ResearchAlertResponse; renderer: WorkspaceRenderer; cellId: string; symbolId: string; pointerId: number; startY: number; anchorY: number; price: number; moved: boolean } | undefined
  let suppressClickUntil = 0, disposed = false, paused = false
  let offMenu: (() => void)[] = [], host: HTMLElement | undefined
  const offs: (() => void)[] = []
  function currentPoint() {
    const cell = deps.workspace.value?.active
    const renderer = cell && WorkspaceRenderer.forHost(cell.host)
    return cell && renderer?.latestPrice ? { symbolId: fromVela(cell.symbol), price: renderer.latestPrice } : undefined
  }
  function project() {
    const cells = deps.workspace.value?.cells() ?? []
    overlays.value = overlays.value.filter(overlay => cells.some(cell => cell.id === overlay.cellId))
    for (const cell of cells) {
      const renderer = WorkspaceRenderer.forHost(cell.host)
      if (!renderer) continue
      renderer.priceAlerts.selectedId = selectedId.value
      renderer.priceAlerts.geometry = geometry => {
        const host = renderer.priceAlerts.host
        if (disposed || !host) return
        const old = overlays.value.find(overlay => overlay.cellId === cell.id)
        if (old && old.host === host && JSON.stringify({ ...old, host: null, cellId: null }) === JSON.stringify({ ...geometry, host: null, cellId: null })) return
        overlays.value = [...overlays.value.filter(overlay => overlay.cellId !== cell.id), { ...geometry, host, cellId: cell.id }]
      }
      renderer.setPriceAlerts(deps.rulesForCell(cell.id).filter(alert => alert.enabled && !alert.archivedAt && !finishedPriceAlert(alert) && alert.configuration?.chartSymbolId === fromVela(cell.symbol))
        .map(alert => {
          const price = drag?.alert.id === alert.id ? drag.price : alert.threshold
          return { id: alert.id, price, label: cw('priceAlertLine', { price: formatNumber(price, 10) }) }
        }))
    }
  }
  function hit(event: MouseEvent) {
    const target = event.target as Element | null
    const elementId = target?.closest?.('[data-price-alert-id]')?.getAttribute('data-price-alert-id')
    for (const cell of deps.workspace.value?.cells() ?? []) {
      if (target && !cell.host.contains(target)) continue
      const renderer = WorkspaceRenderer.forHost(cell.host)
      const id = elementId ?? renderer?.priceAlerts.hitAt?.(event.clientX, event.clientY)
      const alert = deps.rulesForCell(cell.id).find(alert => alert.id === id && alert.enabled && alert.configuration?.chartSymbolId === fromVela(cell.symbol))
      if (alert && renderer) return { cell, renderer, alert }
    }
  }
  function pointerDown(event: PointerEvent) {
    suppressClickUntil = 0
    if (paused || disposed || deps.busy() || event.button !== 0 || !event.isPrimary) return
    const action = (event.target as Element)?.closest?.('[data-price-alert-action]')?.getAttribute('data-price-alert-action')
    if (action && action !== 'move') return
    const found = hit(event)
    if (!found) { selectedId.value = ''; project(); return }
    event.preventDefault(); event.stopImmediatePropagation()
    const { cell, renderer, alert } = found
    const line = overlays.value.find(overlay => overlay.cellId === cell.id)?.lines.find(line => line.id === alert.id)
    selectedId.value = alert.id; draggingId.value = alert.id; deps.invalidate()
    drag = { alert, renderer, cellId: cell.id, symbolId: fromVela(cell.symbol), pointerId: event.pointerId, startY: event.clientY,
      anchorY: line && renderer.priceAlerts.host ? renderer.priceAlerts.host.getBoundingClientRect().top + line.y : event.clientY, price: alert.threshold, moved: false }
    deps.workspace.value?.setActiveCell(cell.id)
    host?.setPointerCapture?.(event.pointerId)
    project()
  }
  function pointerMove(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.pointerId) return
    event.preventDefault(); event.stopImmediatePropagation()
    const cell = deps.workspace.value?.cells().find(cell => cell.id === drag!.cellId)
    if (!cell || fromVela(cell.symbol) !== drag.symbolId) { cancelDrag(); return }
    if (Math.abs(event.clientY - drag.startY) < 3 && !drag.moved) return
    const price = drag.renderer.priceAtClient(event.clientX, drag.anchorY + event.clientY - drag.startY, true)
    if (price != null) { drag.price = deps.roundPrice(price, drag.symbolId); drag.moved = true; project() }
  }
  function releaseDrag() {
    const previous = drag
    drag = undefined; draggingId.value = ''
    if (previous && host?.hasPointerCapture?.(previous.pointerId)) host.releasePointerCapture(previous.pointerId)
    return previous
  }
  function cancelDrag() { releaseDrag(); project() }
  function pointerUp(event: PointerEvent) {
    if (!drag || event.pointerId !== drag.pointerId) return
    event.preventDefault(); event.stopImmediatePropagation()
    const finished = releaseDrag()!
    suppressClickUntil = Date.now() + 400
    if (finished.moved) void deps.movePrice(finished.alert, finished.price)
    else { project(); deps.edit(finished.alert) }
  }
  function click(event: MouseEvent) {
    if (Date.now() > suppressClickUntil || event.detail === 0) return
    suppressClickUntil = 0
    event.preventDefault(); event.stopImmediatePropagation()
  }
  function pointerCancel(event: PointerEvent) { if (drag?.pointerId === event.pointerId) cancelDrag() }
  function keydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement
    if (paused || disposed || target.closest?.('input,textarea,select,[contenteditable="true"]')) return
    if (event.key === 'Escape' && drag) { event.preventDefault(); event.stopImmediatePropagation(); cancelDrag(); return }
    if (!selectedId.value || !host?.contains(target)) return
    if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); event.stopImmediatePropagation(); deps.removeId(selectedId.value) }
    else if (event.key === 'Enter' && target.tagName !== 'BUTTON') { event.preventDefault(); deps.editId(selectedId.value) }
  }
  function capture(event: MouseEvent) {
    pending = undefined; pendingAlert = hit(event)?.alert.id
    for (const cell of deps.workspace.value?.cells() ?? []) {
      const renderer = WorkspaceRenderer.forHost(cell.host)
      const price = renderer?.priceAtClient(event.clientX, event.clientY)
      if (price != null) { const symbolId = fromVela(cell.symbol); pending = { symbolId, price: deps.roundPrice(price, symbolId) }; deps.workspace.value?.setActiveCell(cell.id); break }
    }
  }
  function attach() {
    const workspace = deps.workspace.value
    if (!workspace || host) return
    host = workspace.context().host
    host.addEventListener('contextmenu', capture, { capture: true })
    host.addEventListener('pointerdown', pointerDown, { capture: true })
    host.addEventListener('click', click, { capture: true })
    window.addEventListener('pointermove', pointerMove, { capture: true })
    window.addEventListener('pointerup', pointerUp, { capture: true })
    window.addEventListener('pointercancel', pointerCancel, { capture: true })
    window.addEventListener('keydown', keydown, { capture: true })
    offMenu = ['context:body', 'context:price-axis'].map((target, index) => registerWidgetAction({
      id: 'opentrading-price-alert-' + index, target: target as 'context:body' | 'context:price-axis',
      get label() { return pending ? cw('addPriceAlertAt', { price: formatNumber(pending.price, 10) }) : cw('addPriceAlert') },
      when: () => !!pending && !pendingAlert,
      run: () => deps.startForm(pending),
    }))
    for (const target of ['context:body', 'context:price-axis'] as const) for (const action of ['edit', 'delete'] as const) {
      offMenu.push(registerWidgetAction({ id: `opentrading-alert-${target}-${action}`, target,
        get label() { return cw(action === 'edit' ? 'alertEdit' : 'alertDelete') }, when: () => !!pendingAlert,
        run: () => { if (pendingAlert) action === 'edit' ? deps.editId(pendingAlert) : deps.removeId(pendingAlert) },
      }))
    }
    offs.push(workspace.on('state:changed', project), workspace.on('cell:created', project))
    deps.attached()
    project()
  }
  const stop = watch(deps.workspace, attach, { flush: 'sync', immediate: true })
  function prune(id: string) {
    if (selectedId.value === id) selectedId.value = ''
    if (drag?.alert.id === id) cancelDrag()
    project()
  }
  function pause() { paused = true; cancelDrag() }
  function resume() { paused = false; project() }
  function dispose() {
    disposed = true; stop(); releaseDrag(); overlays.value = []
    host?.removeEventListener('pointerdown', pointerDown, { capture: true })
    host?.removeEventListener('click', click, { capture: true })
    window.removeEventListener('pointermove', pointerMove, { capture: true })
    window.removeEventListener('pointerup', pointerUp, { capture: true })
    window.removeEventListener('pointercancel', pointerCancel, { capture: true })
    window.removeEventListener('keydown', keydown, { capture: true })
    host?.removeEventListener('contextmenu', capture, { capture: true }); offMenu.forEach(off => off()); offs.forEach(off => off())
  }
  return { overlays, selectedId, draggingId, currentPoint, project, prune, pause, resume, dispose }
}
