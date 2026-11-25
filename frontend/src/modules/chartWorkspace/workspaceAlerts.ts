import { computed, reactive, ref, type Ref } from 'vue'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { ResearchAlertResponse, ResearchAlertCreateCommand } from '@/modules/research/contracts'
import { enableAlertDelivery, prepareAlertAudio } from '@/modules/research/alertDelivery'
import { chartApi, type ChartSymbol } from './api'
import { cw, formatNumber } from './locale'
import type { WorkspaceReplay } from './workspaceReplay'
import { finishedPriceAlert, alertCommand } from './priceAlertRules'
import { createLiveWorkspaceAlerts } from './workspaceLiveAlerts'
import { createReplayWorkspaceAlerts } from './workspaceReplayAlerts'
import { createWorkspaceAlertInteraction } from './workspaceAlertInteraction'

export function createWorkspaceAlerts(deps: { workspace: Ref<VelaWorkspace | undefined>; symbols: Ref<ChartSymbol[]>; activeCell?: Ref<string>; replay?: WorkspaceReplay }) {
  const open = ref(false), editing = ref(false), saving = ref(false), formSession = ref(''), error = ref('')
  let disposed = false, paused = false
  let interaction: ReturnType<typeof createWorkspaceAlertInteraction> | undefined
  const project = () => interaction?.project()
  function fail(cause: unknown) { error.value = cause instanceof Error ? cause.message : String(cause) }
  const live = createLiveWorkspaceAlerts({ changed: project, blocked: () => saving.value || !!interaction?.draggingId.value,
    failed: cause => { if (open.value) fail(cause) }, removed: id => interaction?.prune(id) })
  const replayRules = createReplayWorkspaceAlerts(deps.replay, { changed: project, failed: fail, removed: id => interaction?.prune(id), reset: () => {
    if (formSession.value) { open.value = false; editing.value = false; formSession.value = '' }
  } })
  const alerts = live.alerts, replayAlerts = replayRules.alerts, refresh = live.refresh
  const form = reactive({ id: '', version: 0, symbolId: '', price: '', operator: 'crosses' as ResearchAlertCreateCommand['operator'], once: true, sound: true, windows: true })
  const selectedSymbol = computed(() => deps.symbols.value.find(symbol => symbol.id === form.symbolId))
  function currentReplay() {
    const cellId = deps.workspace.value?.active?.id ?? deps.activeCell?.value
    return deps.replay?.active.value && deps.replay.cellId.value === cellId ? deps.replay : undefined
  }
  const replayMode = computed(() => editing.value ? !!formSession.value : !!currentReplay())
  const visibleAlerts = computed(() => (currentReplay() ? replayAlerts.value : alerts.value)
    .filter(alert => !alert.archivedAt && !finishedPriceAlert(alert) && alert.configuration?.chartSymbolId))
  function rulesForCell(cellId: string) {
    return deps.replay?.active.value && deps.replay.cellId.value === cellId ? replayAlerts.value : alerts.value
  }
  function roundedPrice(price: number, symbolId: string) {
    const tick = Number(deps.symbols.value.find(symbol => symbol.id === symbolId)?.metadata?.mintick) || 0.00000001
    return Number((Math.round(price / tick) * tick).toPrecision(12))
  }

  function startForm(request?: { symbolId: string; price: number }) {
    const current = request ?? interaction?.currentPoint()
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
  async function save() {
    const symbol = selectedSymbol.value, price = roundedPrice(Number(form.price), form.symbolId)
    if (saving.value || !symbol || !Number.isFinite(price) || price <= 0) return
    saving.value = true
    live.invalidate()
    error.value = ''
    try {
      void enableAlertDelivery(form.sound, form.windows)
      const baseline = formSession.value ? replayRules.baseline(formSession.value) : undefined
      const quote = baseline ? { price: baseline.price, error: undefined } : (await chartApi.quotes([symbol.id]))[0]
      if (!quote?.price || quote.error) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
      const configuration = { chartSymbolId: symbol.id, once: form.once, initialPrice: quote.price }
      const payload: ResearchAlertCreateCommand = { symbol: symbol.name, name: `${symbol.name} · ${cw(symbol.market === 'usdm' ? 'perpetual' : symbol.market === 'index' ? 'index' : 'spot')} · ${formatNumber(price, 10)}`,
        metric: 'price', operator: form.operator, threshold: price, enabled: true, cooldownMinutes: 1,
        notificationChannels: ['in_app', ...(form.sound ? ['sound' as const] : []), ...(form.windows ? ['windows' as const] : [])], configuration }
      let saved: ResearchAlertResponse
      if (baseline) saved = replayRules.save(payload, form.id, form.version, formSession.value)
      else saved = await live.save(form.id, form.version, payload)
      if (disposed) return
      if (!baseline) live.upsert(saved)
      editing.value = false; open.value = false; project()
    } catch (cause) {
      if (missing(cause) && form.id) { removeLocal(form.id); editing.value = false }
      else fail(cause)
    } finally { saving.value = false }
  }
  function removeLocal(id: string) { live.discard(id); replayRules.remove(id); interaction?.prune(id) }
  const missing = (cause: unknown) => (cause as { status?: number })?.status === 404
  async function change(alert: ResearchAlertResponse) {
    if (saving.value) return
    saving.value = true; live.invalidate(); error.value = ''
    let failed = false
    try {
      if (replayAlerts.value.some(item => item.id === alert.id)) {
        replayRules.toggle(alert); project(); return
      }
      const payload = alertCommand(alert)
      if (!alert.enabled) {
        await enableAlertDelivery(alert.notificationChannels?.includes('sound') ?? false, alert.notificationChannels?.includes('windows') ?? false)
        const quote = (await chartApi.quotes([String(alert.configuration?.chartSymbolId)]))[0]
        if (!quote?.price || quote.error) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
        payload.configuration = { ...alert.configuration, initialPrice: quote.price }
      }
      const saved = await live.save(alert.id, alert.version, { ...payload, enabled: !alert.enabled })
      if (!disposed) { live.upsert(saved); project() }
    } catch (cause) {
      if (missing(cause)) removeLocal(alert.id)
      else { fail(cause); failed = true }
    } finally { saving.value = false; if (failed) void refresh() }
  }
  async function remove(alert: ResearchAlertResponse) {
    if (saving.value) return
    saving.value = true; live.invalidate(); error.value = ''
    let failed = false
    try {
      if (replayAlerts.value.some(item => item.id === alert.id)) { removeLocal(alert.id); return }
      await live.remove(alert)
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
      replayRules.move(alert, price); project(); return
    }
    saving.value = true; live.invalidate(); error.value = ''
    // Keep the preview visible until the persisted rule replaces it.
    const previous = alert.threshold
    live.preview(alert.id, price)
    project()
    let failed = false
    try {
      const id = String(alert.configuration?.chartSymbolId), symbol = deps.symbols.value.find(symbol => symbol.id === id)
      const quote = (await chartApi.quotes([id]))[0]
      if (!quote?.price || quote.error) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
      const name = symbol ? `${symbol.name} · ${cw(symbol.market === 'usdm' ? 'perpetual' : symbol.market === 'index' ? 'index' : 'spot')} · ${formatNumber(price, 10)}` : alert.name
      const saved = await live.save(alert.id, alert.version, { ...alertCommand(alert), name, threshold: price,
        configuration: { ...alert.configuration, initialPrice: quote.price } })
      if (!disposed) live.upsert(saved)
    } catch (cause) {
      if (missing(cause)) removeLocal(alert.id)
      else {
        live.preview(alert.id, previous)
        fail(cause); failed = true
      }
    } finally { saving.value = false; project(); if (failed) void refresh() }
  }
  function show() { if (!paused && !disposed) { error.value = ''; open.value = true; editing.value = false; void refresh() } }
  interaction = createWorkspaceAlertInteraction({ workspace: deps.workspace, rulesForCell, roundPrice: roundedPrice,
    busy: () => saving.value, invalidate: live.invalidate, attached: () => { if (!paused) live.start() }, startForm, edit, editId, removeId, movePrice })
  window.addEventListener('opentrading:open-alerts', show)
  function pause() { paused = true; live.pause(); replayRules.pause(); interaction?.pause() }
  function resume() { if (disposed || !paused) return; paused = false; interaction?.resume(); replayRules.resume(); live.start() }
  function dispose() {
    disposed = true; live.dispose(); replayRules.dispose(); interaction?.dispose()
    window.removeEventListener('opentrading:open-alerts', show)
  }
  const { overlays, selectedId, draggingId } = interaction
  return { alerts: visibleAlerts, replayMode, overlays, selectedId, draggingId, remove, editId, removeId, open, editing, saving, error, form, selectedSymbol, refresh, startForm, edit, save, change, show, pause, resume, dispose }
}
