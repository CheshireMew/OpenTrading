import { computed, reactive, ref, shallowRef, watch, type Ref } from 'vue'
import { registerWidgetAction } from '@luxalgo/vela/plugin'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import { researchApi } from '@/modules/research/api'
import type { ResearchAlertResponse, ResearchAlertCreateCommand } from '@/modules/research/contracts'
import { deliverAlertEvent, enableAlertDelivery, prepareAlertAudio } from '@/modules/research/alertDelivery'
import { WorkspaceRenderer } from './chartPresentation'
import { chartApi, type ChartSymbol } from './api'
import { fromVela } from './provider'
import { cw, formatNumber } from './locale'
import type { PriceAlertGeometry } from './priceAlertLayer'
import type { WorkspaceReplay, ReplaySourceBar } from './workspaceReplay'
import { replayPriceAlertMatches } from './replayPriceAlerts'

export function createWorkspaceAlerts(deps: { workspace: Ref<VelaWorkspace | undefined>; symbols: Ref<ChartSymbol[]>; activeCell?: Ref<string>; replay?: WorkspaceReplay }) {
  const alerts = ref<ResearchAlertResponse[]>([]), open = ref(false), editing = ref(false), saving = ref(false)
  const replayAlerts = ref<ResearchAlertResponse[]>([]), formSession = ref('')
  const error = ref(''), selectedId = ref(''), draggingId = ref('')
  const overlays = shallowRef<({ cellId: string; host: HTMLElement } & PriceAlertGeometry)[]>([])
  function fail(cause: unknown) { error.value = cause instanceof Error ? cause.message : String(cause) }
  const form = reactive({ id: '', version: 0, symbolId: '', price: '', operator: 'crosses' as ResearchAlertCreateCommand['operator'], once: true, sound: true, windows: true })
  const selectedSymbol = computed(() => deps.symbols.value.find(symbol => symbol.id === form.symbolId))
  const finished = (alert: ResearchAlertResponse) => !alert.enabled && !!alert.lastTriggeredAt && alert.configuration?.once !== false
  function currentReplay() {
    const replay = deps.replay, observedCell = deps.activeCell?.value
    const cellId = deps.workspace.value?.active?.id ?? observedCell
    return replay?.active.value && replay.cellId.value === cellId ? replay : undefined
  }
  const replayMode = computed(() => editing.value ? !!formSession.value : !!currentReplay())
  const visibleAlerts = computed(() => (currentReplay() ? replayAlerts.value : alerts.value)
    .filter(alert => !alert.archivedAt && !finished(alert) && alert.configuration?.chartSymbolId))
  function rulesForCell(cellId: string) {
    return deps.replay?.active.value && deps.replay.cellId.value === cellId ? replayAlerts.value : alerts.value
  }
  function replayBaseline() {
    const replay = deps.replay
    if (!replay?.active.value || replay.sessionId.value !== formSession.value) throw new Error(cw('alertReplayEnded'))
    return { price: replay.account.price, time: replay.now.value }
  }
  let pending: { symbolId: string; price: number } | undefined
  let pendingAlert: string | undefined
  let drag: { alert: ResearchAlertResponse; renderer: WorkspaceRenderer; cellId: string; symbolId: string; pointerId: number; startY: number; anchorY: number; price: number; moved: boolean } | undefined
  let writeEpoch = 0
  let suppressClickUntil = 0
  let disposed = false, paused = false, loading = false, timer: ReturnType<typeof setInterval> | undefined
  let offMenu: (() => void)[] = [], host: HTMLElement | undefined
  const offs: (() => void)[] = []
  function roundedPrice(price: number, symbolId: string) {
    const tick = Number(deps.symbols.value.find(symbol => symbol.id === symbolId)?.metadata?.mintick) || 0.00000001
    return Number((Math.round(price / tick) * tick).toPrecision(12))
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
      renderer.setPriceAlerts(rulesForCell(cell.id).filter(alert => alert.enabled && !alert.archivedAt && !finished(alert) && alert.configuration?.chartSymbolId === fromVela(cell.symbol))
        .map(alert => {
          const price = drag?.alert.id === alert.id ? drag.price : alert.threshold
          return { id: alert.id, price, label: cw('priceAlertLine', { price: formatNumber(price, 10) }) }
        }))
    }
  }
  async function refresh() {
    if (disposed || paused || loading || saving.value || drag) return
    loading = true
    const epoch = writeEpoch
    try {
      const result = await researchApi.getWorkbench(1, 1)
      if (!disposed && !paused && epoch === writeEpoch) { alerts.value = result.alerts ?? []; project() }
    } catch (error) { if (open.value && !disposed && !paused) fail(error) }
    finally { loading = false }
  }
  function startForm(request?: { symbolId: string; price: number }) {
    const cell = deps.workspace.value?.active
    const renderer = cell && WorkspaceRenderer.forHost(cell.host)
    const current = request ?? (cell && renderer?.latestPrice ? { symbolId: fromVela(cell.symbol), price: renderer.latestPrice } : undefined)
    if (!current) return
    error.value = ''
    formSession.value = currentReplay()?.sessionId.value ?? ''
    Object.assign(form, { id: '', version: 0, symbolId: current.symbolId, price: String(roundedPrice(current.price, current.symbolId)), operator: 'crosses', once: true, sound: true, windows: true })
    editing.value = true; open.value = true
    void prepareAlertAudio()
  }
  function edit(alert: ResearchAlertResponse) {
    error.value = ''
    formSession.value = replayAlerts.value.some(item => item.id === alert.id) ? deps.replay?.sessionId.value ?? '' : ''
    Object.assign(form, { id: alert.id, version: alert.version, symbolId: String(alert.configuration?.chartSymbolId), price: String(alert.threshold), operator: alert.operator,
      once: alert.configuration?.once !== false, sound: alert.notificationChannels?.includes('sound') ?? false, windows: alert.notificationChannels?.includes('windows') ?? false })
    editing.value = true; open.value = true; void prepareAlertAudio()
  }
  function body(alert: ResearchAlertResponse): ResearchAlertCreateCommand {
    return { symbol: alert.symbol, name: alert.name, metric: alert.metric, operator: alert.operator, threshold: alert.threshold,
      secondaryThreshold: alert.secondaryThreshold, cooldownMinutes: alert.cooldownMinutes, enabled: alert.enabled,
      notificationChannels: alert.notificationChannels, configuration: alert.configuration, watchItemId: alert.watchItemId }
  }
  async function save() {
    const symbol = selectedSymbol.value, price = roundedPrice(Number(form.price), form.symbolId)
    if (saving.value || !symbol || !Number.isFinite(price) || price <= 0) return
    saving.value = true
    writeEpoch++
    error.value = ''
    try {
      void enableAlertDelivery(form.sound, form.windows)
      const baseline = formSession.value ? replayBaseline() : undefined
      const quote = baseline ? { price: baseline.price, error: undefined } : (await chartApi.quotes([symbol.id]))[0]
      if (!quote?.price || quote.error) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
      const configuration = { chartSymbolId: symbol.id, once: form.once, initialPrice: quote.price }
      const payload: ResearchAlertCreateCommand = { symbol: symbol.name, name: `${symbol.name} · ${cw(symbol.market === 'usdm' ? 'perpetual' : symbol.market === 'index' ? 'index' : 'spot')} · ${formatNumber(price, 10)}`,
        metric: 'price', operator: form.operator, threshold: price, enabled: true, cooldownMinutes: 1,
        notificationChannels: ['in_app', ...(form.sound ? ['sound' as const] : []), ...(form.windows ? ['windows' as const] : [])], configuration }
      let saved: ResearchAlertResponse
      if (baseline) {
        const date = new Date().toISOString()
        saved = { ...payload, enabled: true, cooldownMinutes: 1, id: form.id || crypto.randomUUID(), version: form.version + 1,
          createdAt: date, updatedAt: date, lastValue: baseline.price, lastEvaluatedAt: new Date(baseline.time).toISOString(),
          configuration: { ...configuration, replaySessionId: formSession.value, replayCreatedAt: baseline.time } }
      } else saved = form.id ? await researchApi.updateAlert(form.id, { ...payload, expectedVersion: form.version }) : await researchApi.createAlert(payload)
      if (disposed) return
      if (baseline) replayAlerts.value = [saved, ...replayAlerts.value.filter(alert => alert.id !== saved.id)]
      else alerts.value = [saved, ...alerts.value.filter(alert => alert.id !== saved.id)]
      editing.value = false; open.value = false; project()
    } catch (cause) {
      if (missing(cause) && form.id) { removeLocal(form.id); editing.value = false }
      else fail(cause)
    } finally { saving.value = false }
  }
  function removeLocal(id: string) {
    alerts.value = alerts.value.filter(alert => alert.id !== id)
    replayAlerts.value = replayAlerts.value.filter(alert => alert.id !== id)
    if (selectedId.value === id) selectedId.value = ''
    if (drag?.alert.id === id) cancelDrag()
    project()
  }
  const missing = (cause: unknown) => (cause as { status?: number })?.status === 404
  async function change(alert: ResearchAlertResponse) {
    if (saving.value) return
    saving.value = true; writeEpoch++; error.value = ''
    let failed = false
    try {
      if (replayAlerts.value.some(item => item.id === alert.id)) {
        const replay = deps.replay!
        alert.enabled = !alert.enabled; alert.lastValue = replay.account.price
        alert.lastEvaluatedAt = new Date(replay.now.value).toISOString(); alert.lastTriggeredAt = null
        if (alert.enabled) void enableAlertDelivery(alert.notificationChannels?.includes('sound') ?? false, alert.notificationChannels?.includes('windows') ?? false)
        project(); return
      }
      const payload = body(alert)
      if (!alert.enabled) {
        await enableAlertDelivery(alert.notificationChannels?.includes('sound') ?? false, alert.notificationChannels?.includes('windows') ?? false)
        const quote = (await chartApi.quotes([String(alert.configuration?.chartSymbolId)]))[0]
        if (!quote?.price || quote.error) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
        payload.configuration = { ...alert.configuration, initialPrice: quote.price }
      }
      const saved = await researchApi.updateAlert(alert.id, { ...payload, enabled: !alert.enabled, expectedVersion: alert.version })
      if (!disposed) { alerts.value = alerts.value.map(item => item.id === saved.id ? saved : item); project() }
    } catch (cause) {
      if (missing(cause)) removeLocal(alert.id)
      else { fail(cause); failed = true }
    } finally { saving.value = false; if (failed) void refresh() }
  }
  async function remove(alert: ResearchAlertResponse) {
    if (saving.value) return
    saving.value = true; writeEpoch++; error.value = ''
    let failed = false
    try {
      if (replayAlerts.value.some(item => item.id === alert.id)) { removeLocal(alert.id); return }
      await researchApi.deleteAlert(alert.id, alert.version)
      if (!disposed) removeLocal(alert.id)
    } catch (cause) {
      if (missing(cause)) removeLocal(alert.id)
      else { fail(cause); failed = true }
    } finally { saving.value = false; if (failed) void refresh() }
  }
  function editId(id: string) { const alert = visibleAlerts.value.find(alert => alert.id === id); if (alert && !saving.value) edit(alert) }
  function removeId(id: string) { const alert = visibleAlerts.value.find(alert => alert.id === id); if (alert) void remove(alert) }
  async function movePrice(alert: ResearchAlertResponse, price: number) {
    if (saving.value || price === alert.threshold) { project(); return }
    if (replayAlerts.value.some(item => item.id === alert.id)) {
      const replay = deps.replay!
      alert.threshold = price; alert.lastValue = replay.account.price
      alert.lastEvaluatedAt = new Date(replay.now.value).toISOString(); alert.lastTriggeredAt = null
      alert.name = alert.name.replace(/[^·]+$/, ' ' + formatNumber(price, 10))
      project(); return
    }
    saving.value = true; writeEpoch++; error.value = ''
    // Keep the preview visible until the persisted rule replaces it.
    const previous = alert.threshold
    alerts.value = alerts.value.map(item => item.id === alert.id ? { ...item, threshold: price } : item)
    project()
    let failed = false
    try {
      const id = String(alert.configuration?.chartSymbolId), symbol = deps.symbols.value.find(symbol => symbol.id === id)
      const quote = (await chartApi.quotes([id]))[0]
      if (!quote?.price || quote.error) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
      const name = symbol ? `${symbol.name} · ${cw(symbol.market === 'usdm' ? 'perpetual' : symbol.market === 'index' ? 'index' : 'spot')} · ${formatNumber(price, 10)}` : alert.name
      const saved = await researchApi.updateAlert(alert.id, { ...body(alert), name, threshold: price,
        configuration: { ...alert.configuration, initialPrice: quote.price }, expectedVersion: alert.version })
      if (!disposed) alerts.value = alerts.value.map(item => item.id === saved.id ? saved : item)
    } catch (cause) {
      if (missing(cause)) removeLocal(alert.id)
      else {
        alerts.value = alerts.value.map(item => item.id === alert.id ? { ...item, threshold: previous } : item)
        fail(cause); failed = true
      }
    } finally { saving.value = false; project(); if (failed) void refresh() }
  }
  function hit(event: MouseEvent) {
    const target = event.target as Element | null
    const elementId = target?.closest?.('[data-price-alert-id]')?.getAttribute('data-price-alert-id')
    for (const cell of deps.workspace.value?.cells() ?? []) {
      if (target && !cell.host.contains(target)) continue
      const renderer = WorkspaceRenderer.forHost(cell.host)
      const id = elementId ?? renderer?.priceAlerts.hitAt?.(event.clientX, event.clientY)
      const alert = rulesForCell(cell.id).find(alert => alert.id === id && alert.enabled && alert.configuration?.chartSymbolId === fromVela(cell.symbol))
      if (alert && renderer) return { cell, renderer, alert }
    }
  }
  function pointerDown(event: PointerEvent) {
    suppressClickUntil = 0
    if (paused || disposed || saving.value || event.button !== 0 || !event.isPrimary) return
    const action = (event.target as Element)?.closest?.('[data-price-alert-action]')?.getAttribute('data-price-alert-action')
    if (action && action !== 'move') return
    const found = hit(event)
    if (!found) { selectedId.value = ''; project(); return }
    event.preventDefault(); event.stopImmediatePropagation()
    const { cell, renderer, alert } = found
    const line = overlays.value.find(overlay => overlay.cellId === cell.id)?.lines.find(line => line.id === alert.id)
    selectedId.value = alert.id; draggingId.value = alert.id; writeEpoch++
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
    if (price != null) { drag.price = roundedPrice(price, drag.symbolId); drag.moved = true; project() }
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
    if (finished.moved) void movePrice(finished.alert, finished.price)
    else { project(); edit(finished.alert) }
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
    if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); event.stopImmediatePropagation(); removeId(selectedId.value) }
    else if (event.key === 'Enter' && target.tagName !== 'BUTTON') { event.preventDefault(); editId(selectedId.value) }
  }
  function capture(event: MouseEvent) {
    pending = undefined; pendingAlert = hit(event)?.alert.id
    for (const cell of deps.workspace.value?.cells() ?? []) {
      const renderer = WorkspaceRenderer.forHost(cell.host)
      const price = renderer?.priceAtClient(event.clientX, event.clientY)
      if (price != null) { const symbolId = fromVela(cell.symbol); pending = { symbolId, price: roundedPrice(price, symbolId) }; deps.workspace.value?.setActiveCell(cell.id); break }
    }
  }
  function attach() {
    const workspace = deps.workspace.value
    if (!workspace || host) return
    host = workspace.context().host
    host.addEventListener('contextmenu', capture, true)
    host.addEventListener('pointerdown', pointerDown, true)
    host.addEventListener('click', click, true)
    window.addEventListener('pointermove', pointerMove, true)
    window.addEventListener('pointerup', pointerUp, true)
    window.addEventListener('pointercancel', pointerCancel, true)
    window.addEventListener('keydown', keydown, true)
    offMenu = ['context:body', 'context:price-axis'].map((target, index) => registerWidgetAction({
      id: 'opentrading-price-alert-' + index, target: target as 'context:body' | 'context:price-axis',
      get label() { return pending ? cw('addPriceAlertAt', { price: formatNumber(pending.price, 10) }) : cw('addPriceAlert') },
      when: () => !!pending && !pendingAlert,
      run: () => startForm(pending),
    }))
    for (const target of ['context:body', 'context:price-axis'] as const) for (const action of ['edit', 'delete'] as const) {
      offMenu.push(registerWidgetAction({ id: `opentrading-alert-${target}-${action}`, target,
        get label() { return cw(action === 'edit' ? 'alertEdit' : 'alertDelete') }, when: () => !!pendingAlert,
        run: () => { if (pendingAlert) action === 'edit' ? editId(pendingAlert) : removeId(pendingAlert) },
      }))
    }
    offs.push(workspace.on('state:changed', project), workspace.on('cell:created', project))
    if (!paused) { void refresh(); timer = setInterval(() => void refresh(), 10_000) }
    window.addEventListener('opentrading:alert-triggered', onTriggered)
    window.addEventListener('opentrading:open-alerts', show)
  }
  function onTriggered(event: Event) {
    const id = (event as CustomEvent<{ entityId?: string }>).detail?.entityId
    if (id && alerts.value.some(alert => alert.id === id && alert.configuration?.once !== false)) { writeEpoch++; removeLocal(id) }
    void refresh()
  }
  const stop = watch(deps.workspace, attach, { flush: 'sync' })
  const stopReplay = deps.replay ? watch([deps.replay.active, deps.replay.sessionId], () => {
    replayAlerts.value = []
    if (formSession.value) { open.value = false; editing.value = false; formSession.value = '' }
    project()
  }, { flush: 'sync' }) : () => {}
  const offReplay = deps.replay?.subscribeSourceBars(({ sessionId, symbolId, bar }: ReplaySourceBar) => {
    if (disposed || paused) return
    for (const alert of [...replayAlerts.value]) {
      if (!alert.enabled || alert.configuration?.replaySessionId !== sessionId || alert.configuration.chartSymbolId !== symbolId ||
          bar.time < Number(alert.configuration.replayCreatedAt) || bar.closeTime <= Date.parse(alert.lastEvaluatedAt ?? '')) continue
      const ready = !alert.lastTriggeredAt || bar.closeTime - Date.parse(alert.lastTriggeredAt) >= alert.cooldownMinutes * 60000
      const triggered = ready && replayPriceAlertMatches(alert, bar)
      alert.lastValue = bar.close; alert.lastEvaluatedAt = new Date(bar.closeTime).toISOString()
      if (!triggered) continue
      alert.lastTriggeredAt = alert.lastEvaluatedAt
      if (alert.configuration.once !== false) removeLocal(alert.id)
      const date = new Date().toISOString()
      void deliverAlertEvent({ id: crypto.randomUUID(), entityType: 'alert', entityId: alert.id, symbol: alert.symbol, kind: 'alert_triggered',
        title: `${cw('replay')} · ${alert.name}`, body: cw('alertReplayTriggered', { symbol: alert.symbol, price: formatNumber(alert.threshold, 10) }),
        occurredAt: alert.lastEvaluatedAt, createdAt: date, payload: { value: alert.threshold, notificationChannels: alert.notificationChannels ?? [],
          replaySessionId: sessionId } }).catch(fail)
    }
    project()
  })
  function show() { if (!paused && !disposed) { error.value = ''; open.value = true; editing.value = false; void refresh() } }
  function pause() { paused = true; clearInterval(timer); cancelDrag() }
  function resume() {
    if (disposed || !paused) return
    paused = false
    if (host) { void refresh(); timer = setInterval(() => void refresh(), 10_000) }
  }
  function dispose() {
    disposed = true; stop(); stopReplay(); offReplay?.(); clearInterval(timer); releaseDrag(); overlays.value = []
    host?.removeEventListener('pointerdown', pointerDown, true)
    host?.removeEventListener('click', click, true)
    window.removeEventListener('pointermove', pointerMove, true)
    window.removeEventListener('pointerup', pointerUp, true)
    window.removeEventListener('pointercancel', pointerCancel, true)
    window.removeEventListener('keydown', keydown, true)
    host?.removeEventListener('contextmenu', capture, true); offMenu.forEach(off => off()); offs.forEach(off => off())
    window.removeEventListener('opentrading:alert-triggered', onTriggered)
    window.removeEventListener('opentrading:open-alerts', show)
  }
  return { alerts: visibleAlerts, replayMode, overlays, selectedId, draggingId, remove, editId, removeId, open, editing, saving, error, form, selectedSymbol, refresh, startForm, edit, save, change, show, pause, resume, dispose }
}
