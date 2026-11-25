import { ref } from 'vue'
import { researchApi } from '@/modules/research/api'
import type { ResearchAlertResponse, ResearchAlertCreateCommand } from '@/modules/research/contracts'

/** Own persistent rules, refresh generations and the lifetime of their polling. */
export function createLiveWorkspaceAlerts(deps: {
  changed: () => void; blocked: () => boolean; failed: (cause: unknown) => void; removed: (id: string) => void
}) {
  const alerts = ref<ResearchAlertResponse[]>([])
  let epoch = 0, disposed = false, paused = false, loading = false
  let timer: ReturnType<typeof setInterval> | undefined
  const invalidate = () => { epoch++ }
  function upsert(alert: ResearchAlertResponse) {
    if (disposed) return
    alerts.value = [alert, ...alerts.value.filter(item => item.id !== alert.id)]
    deps.changed()
  }
  function preview(id: string, price: number) {
    alerts.value = alerts.value.map(item => item.id === id ? { ...item, threshold: price } : item)
    deps.changed()
  }
  function discard(id: string) {
    alerts.value = alerts.value.filter(item => item.id !== id)
    deps.changed()
  }
  async function refresh() {
    if (disposed || paused || loading || deps.blocked()) return
    loading = true
    const current = epoch
    try {
      const result = await researchApi.getWorkbench(1, 1)
      if (!disposed && !paused && current === epoch) { alerts.value = result.alerts ?? []; deps.changed() }
    } catch (cause) { if (!disposed && !paused) deps.failed(cause) }
    finally { loading = false }
  }
  async function save(id: string, version: number, payload: ResearchAlertCreateCommand) {
    invalidate()
    return id ? researchApi.updateAlert(id, { ...payload, expectedVersion: version }) : researchApi.createAlert(payload)
  }
  async function remove(alert: ResearchAlertResponse) {
    invalidate()
    await researchApi.deleteAlert(alert.id, alert.version)
    if (!disposed) discard(alert.id)
  }
  function onTriggered(event: Event) {
    const id = (event as CustomEvent<{ entityId?: string }>).detail?.entityId
    if (id && alerts.value.some(alert => alert.id === id && alert.configuration?.once !== false)) {
      invalidate(); discard(id); deps.removed(id)
    }
    void refresh()
  }
  window.addEventListener('opentrading:alert-triggered', onTriggered)
  function start() {
    if (disposed) return
    paused = false
    clearInterval(timer)
    void refresh(); timer = setInterval(() => void refresh(), 10_000)
  }
  function pause() { paused = true; clearInterval(timer); invalidate() }
  function dispose() { disposed = true; clearInterval(timer); invalidate(); window.removeEventListener('opentrading:alert-triggered', onTriggered) }
  return { alerts, invalidate, upsert, preview, discard, refresh, save, remove, start, pause, dispose }
}
