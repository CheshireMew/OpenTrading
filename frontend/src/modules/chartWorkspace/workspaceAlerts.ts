import { computed, reactive, ref, watch, type Ref } from 'vue'
import { registerWidgetAction } from '@luxalgo/vela/plugin'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import { researchApi } from '@/modules/research/api'
import type { ResearchAlertResponse, ResearchAlertCreateCommand } from '@/modules/research/contracts'
import { enableAlertDelivery, prepareAlertAudio } from '@/modules/research/alertDelivery'
import { WorkspaceRenderer } from './chartPresentation'
import { chartApi, type ChartSymbol } from './api'
import { fromVela } from './provider'
import { cw, formatNumber } from './locale'

export function createWorkspaceAlerts(deps: { workspace: Ref<VelaWorkspace | undefined>; symbols: Ref<ChartSymbol[]> }) {
  const alerts = ref<ResearchAlertResponse[]>([]), open = ref(false), editing = ref(false), saving = ref(false)
  const error = ref('')
  function fail(cause: unknown) { error.value = cause instanceof Error ? cause.message : String(cause) }
  const form = reactive({ id: '', version: 0, symbolId: '', price: '', operator: 'crosses' as ResearchAlertCreateCommand['operator'], once: true, sound: true, windows: true })
  const selectedSymbol = computed(() => deps.symbols.value.find(symbol => symbol.id === form.symbolId))
  const visibleAlerts = computed(() => alerts.value.filter(alert => !alert.archivedAt && alert.configuration?.chartSymbolId))
  let pending: { symbolId: string; price: number } | undefined
  let writeEpoch = 0
  let disposed = false, loading = false, timer: ReturnType<typeof setInterval> | undefined
  let offMenu: (() => void)[] = [], host: HTMLElement | undefined
  const offs: (() => void)[] = []
  function roundedPrice(price: number, symbolId: string) {
    const tick = Number(deps.symbols.value.find(symbol => symbol.id === symbolId)?.metadata?.mintick) || 0.00000001
    return Number((Math.round(price / tick) * tick).toPrecision(12))
  }

  function project() {
    for (const cell of deps.workspace.value?.cells() ?? []) {
      const renderer = WorkspaceRenderer.forHost(cell.host)
      if (renderer) {
        renderer.setPriceAlerts(visibleAlerts.value.filter(alert => alert.enabled && alert.configuration?.chartSymbolId === fromVela(cell.symbol))
          .map(alert => ({ id: alert.id, price: alert.threshold, label: cw('priceAlertLine', { price: formatNumber(alert.threshold, 10) }) })))
      }
    }
  }
  async function refresh() {
    if (disposed || loading) return
    loading = true
    const epoch = writeEpoch
    try {
      const result = await researchApi.getWorkbench(1, 1)
      if (!disposed && epoch === writeEpoch) { alerts.value = result.alerts ?? []; project() }
    } catch (error) { if (open.value && !disposed) fail(error) }
    finally { loading = false }
  }
  function startForm(request?: { symbolId: string; price: number }) {
    const cell = deps.workspace.value?.active
    const renderer = cell && WorkspaceRenderer.forHost(cell.host)
    const current = request ?? (cell && renderer?.latestPrice ? { symbolId: fromVela(cell.symbol), price: renderer.latestPrice } : undefined)
    if (!current) return
    error.value = ''
    Object.assign(form, { id: '', version: 0, symbolId: current.symbolId, price: String(roundedPrice(current.price, current.symbolId)), operator: 'crosses', once: true, sound: true, windows: true })
    editing.value = true; open.value = true
    void prepareAlertAudio()
  }
  function edit(alert: ResearchAlertResponse) {
    error.value = ''
    Object.assign(form, { id: alert.id, version: alert.version, symbolId: String(alert.configuration?.chartSymbolId), price: String(alert.threshold), operator: alert.operator,
      once: alert.configuration?.once !== false, sound: alert.notificationChannels?.includes('sound') ?? false, windows: alert.notificationChannels?.includes('windows') ?? false })
    editing.value = true; void prepareAlertAudio()
  }
  function body(alert: ResearchAlertResponse): ResearchAlertCreateCommand {
    return { symbol: alert.symbol, name: alert.name, metric: alert.metric, operator: alert.operator, threshold: alert.threshold,
      secondaryThreshold: alert.secondaryThreshold, cooldownMinutes: alert.cooldownMinutes, enabled: alert.enabled,
      notificationChannels: alert.notificationChannels, configuration: alert.configuration, watchItemId: alert.watchItemId }
  }
  async function save() {
    const price = Number(form.price), symbol = selectedSymbol.value
    if (saving.value || !symbol || !Number.isFinite(price) || price <= 0) return
    saving.value = true
    writeEpoch++
    error.value = ''
    try {
      await enableAlertDelivery(form.sound, form.windows)
      const quotes = await chartApi.quotes([symbol.id])
      const quote = quotes[0]
      if (!quote?.price || quote.error) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
      const configuration = { chartSymbolId: symbol.id, once: form.once, initialPrice: quote.price }
      const payload: ResearchAlertCreateCommand = { symbol: symbol.name, name: `${symbol.name} · ${cw(symbol.market === 'usdm' ? 'perpetual' : symbol.market === 'index' ? 'index' : 'spot')} · ${formatNumber(price, 10)}`,
        metric: 'price', operator: form.operator, threshold: price, enabled: true, cooldownMinutes: 1,
        notificationChannels: ['in_app', ...(form.sound ? ['sound' as const] : []), ...(form.windows ? ['windows' as const] : [])], configuration }
      const saved = form.id ? await researchApi.updateAlert(form.id, { ...payload, expectedVersion: form.version }) : await researchApi.createAlert(payload)
      if (disposed) return
      alerts.value = [saved, ...alerts.value.filter(alert => alert.id !== saved.id)]
      editing.value = false; project()
    } catch (error) { fail(error) }
    finally { saving.value = false }
  }
  async function change(alert: ResearchAlertResponse, archive = false) {
    if (saving.value) return
    saving.value = true
    writeEpoch++
    try {
      const payload = body(alert)
      if (!archive && !alert.enabled) {
        await enableAlertDelivery(alert.notificationChannels?.includes('sound') ?? false, alert.notificationChannels?.includes('windows') ?? false)
        const quote = (await chartApi.quotes([String(alert.configuration?.chartSymbolId)]))[0]
        if (!quote?.price || quote.error) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
        payload.configuration = { ...alert.configuration, initialPrice: quote.price }
      }
      const saved = archive ? await researchApi.setAlertArchived(alert.id, { expectedVersion: alert.version }, true)
        : await researchApi.updateAlert(alert.id, { ...payload, enabled: !alert.enabled, expectedVersion: alert.version })
      if (!disposed) { alerts.value = alerts.value.map(item => item.id === saved.id ? saved : item); project() }
    } catch (error) { fail(error); void refresh() }
    finally { saving.value = false }
  }
  function capture(event: MouseEvent) {
    pending = undefined
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
    offMenu = ['context:body', 'context:price-axis'].map((target, index) => registerWidgetAction({
      id: 'opentrading-price-alert-' + index, target: target as 'context:body' | 'context:price-axis',
      get label() { return pending ? cw('addPriceAlertAt', { price: formatNumber(pending.price, 10) }) : cw('addPriceAlert') },
      when: () => !!pending,
      run: () => startForm(pending),
    }))
    offs.push(workspace.on('state:changed', project), workspace.on('cell:created', project))
    void refresh(); timer = setInterval(() => void refresh(), 10_000)
    window.addEventListener('opentrading:alert-triggered', onTriggered)
    window.addEventListener('opentrading:open-alerts', show)
  }
  function onTriggered() { void refresh() }
  const stop = watch(deps.workspace, attach, { flush: 'sync' })
  function show() { error.value = ''; open.value = true; editing.value = false; void refresh() }
  function dispose() {
    disposed = true; stop(); clearInterval(timer)
    host?.removeEventListener('contextmenu', capture, true); offMenu.forEach(off => off()); offs.forEach(off => off())
    window.removeEventListener('opentrading:alert-triggered', onTriggered)
    window.removeEventListener('opentrading:open-alerts', show)
  }
  return { alerts: visibleAlerts, open, editing, saving, error, form, selectedSymbol, refresh, startForm, edit, save, change, show, dispose }
}
