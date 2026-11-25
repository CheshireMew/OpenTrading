import { ref, watch } from 'vue'
import type { ResearchAlertResponse, ResearchAlertCreateCommand } from '@/modules/research/contracts'
import { deliverAlertEvent, enableAlertDelivery } from '@/modules/research/alertDelivery'
import type { WorkspaceReplay, ReplaySourceBar } from './workspaceReplay'
import { replayPriceAlertMatches } from './replayPriceAlerts'
import { cw, formatNumber } from './locale'

/** Ephemeral rules consume only the source bars belonging to their replay session. */
export function createReplayWorkspaceAlerts(replay: Pick<WorkspaceReplay, 'active' | 'sessionId' | 'account' | 'now' | 'subscribeSourceBars'> | undefined, deps: {
  changed: () => void; reset: () => void; failed: (cause: unknown) => void; removed: (id: string) => void
}) {
  const alerts = ref<ResearchAlertResponse[]>([])
  let disposed = false, paused = false
  function baseline(session: string) {
    if (!replay?.active.value || replay.sessionId.value !== session) throw new Error(cw('alertReplayEnded'))
    return { price: replay.account.price, time: replay.now.value }
  }
  function remove(id: string) {
    const existed = alerts.value.some(alert => alert.id === id)
    alerts.value = alerts.value.filter(alert => alert.id !== id)
    if (existed) deps.removed(id)
    deps.changed()
  }
  function save(payload: ResearchAlertCreateCommand, id: string, version: number, session: string): ResearchAlertResponse {
    const start = baseline(session), date = new Date().toISOString()
    const saved = { ...payload, enabled: true, cooldownMinutes: 1, id: id || crypto.randomUUID(), version: version + 1,
      createdAt: date, updatedAt: date, lastValue: start.price, lastEvaluatedAt: new Date(start.time).toISOString(),
      configuration: { ...payload.configuration, replaySessionId: session, replayCreatedAt: start.time } }
    alerts.value = [saved, ...alerts.value.filter(alert => alert.id !== saved.id)]
    deps.changed()
    return saved
  }
  function rebase(alert: ResearchAlertResponse) {
    const start = baseline(String(alert.configuration?.replaySessionId))
    alert.lastValue = start.price; alert.lastEvaluatedAt = new Date(start.time).toISOString(); alert.lastTriggeredAt = null
  }
  function toggle(alert: ResearchAlertResponse) {
    rebase(alert); alert.enabled = !alert.enabled
    if (alert.enabled) void enableAlertDelivery(alert.notificationChannels?.includes('sound') ?? false, alert.notificationChannels?.includes('windows') ?? false)
    deps.changed()
  }
  function move(alert: ResearchAlertResponse, price: number) {
    rebase(alert); alert.threshold = price
    alert.name = alert.name.replace(/[^·]+$/, ' ' + formatNumber(price, 10)); deps.changed()
  }
  const stop = replay ? watch([replay.active, replay.sessionId], () => {
    alerts.value = []; deps.reset(); deps.changed()
  }, { flush: 'sync' }) : () => {}
  const off = replay?.subscribeSourceBars(({ sessionId, symbolId, bar }: ReplaySourceBar) => {
    if (disposed || paused) return
    for (const alert of [...alerts.value]) {
      if (!alert.enabled || alert.configuration?.replaySessionId !== sessionId || alert.configuration.chartSymbolId !== symbolId ||
          bar.time < Number(alert.configuration.replayCreatedAt) || bar.closeTime <= Date.parse(alert.lastEvaluatedAt ?? '')) continue
      const ready = !alert.lastTriggeredAt || bar.closeTime - Date.parse(alert.lastTriggeredAt) >= alert.cooldownMinutes * 60000
      const triggered = ready && replayPriceAlertMatches(alert, bar)
      alert.lastValue = bar.close; alert.lastEvaluatedAt = new Date(bar.closeTime).toISOString()
      if (!triggered) continue
      alert.lastTriggeredAt = alert.lastEvaluatedAt
      if (alert.configuration.once !== false) remove(alert.id)
      void deliverAlertEvent({ id: crypto.randomUUID(), entityType: 'alert', entityId: alert.id, symbol: alert.symbol, kind: 'alert_triggered',
        title: `${cw('replay')} · ${alert.name}`, body: cw('alertReplayTriggered', { symbol: alert.symbol, price: formatNumber(alert.threshold, 10) }),
        occurredAt: alert.lastEvaluatedAt, createdAt: new Date().toISOString(), payload: { value: alert.threshold,
          notificationChannels: alert.notificationChannels ?? [], replaySessionId: sessionId } }).catch(deps.failed)
    }
    deps.changed()
  })
  return { alerts, baseline, save, remove, toggle, move,
    pause() { paused = true }, resume() { paused = false }, dispose() { disposed = true; stop(); off?.() } }
}
