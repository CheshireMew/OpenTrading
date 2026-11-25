import { onBeforeUnmount, onMounted } from 'vue'
import { getLocalStorage, readStorageValue } from '@/utils/storage'

import { researchApi } from './api'
import {
  loadDeliveredNotificationIds,
  WINDOWS_NOTIFICATION_DELIVERED_KEY,
} from './notificationEvents'
import { deliverAlertEvent } from './alertDelivery'
import { PUBLIC_SITE } from '@/app/publicSite'
import { evaluateBrowserAlerts } from './browserResearch'
import { browserNotificationStore } from '@/modules/personal/browserStore'

const POLL_INTERVAL_MS = 3_000

export const useDesktopAlertNotifications = () => {
  let timer: number | undefined
  let running = false
  let disposed = false
  const controller = new AbortController()
  const memoryDelivered = new Set<string>(), pendingReceipts = new Set<string>()
  let memoryCursor: string | null = null, migrated = false, pendingState = false
  const commit = async (ids: string[], cursor: string | null) => {
    for (const id of ids) { memoryDelivered.add(id); pendingReceipts.add(id) }
    memoryCursor = cursor; migrated = true; pendingState = true
    try {
      await browserNotificationStore.commit([...pendingReceipts], cursor)
      pendingReceipts.clear()
      pendingState = false
    } catch { /* Retain session receipts until persistent storage recovers. */ }
  }
  const deliverPending = async () => {
      if (PUBLIC_SITE) await evaluateBrowserAlerts(controller.signal)
      const state = await browserNotificationStore.state().catch(() => ({ cursor: memoryCursor, migrated }))
      if (!state.migrated && !migrated) {
        const storage = getLocalStorage()
        let stored: string | null = null
        try { stored = storage ? readStorageValue(storage, WINDOWS_NOTIFICATION_DELIVERED_KEY) : null } catch { /* No legacy receipts to migrate. */ }
        await commit(loadDeliveredNotificationIds(stored), state.cursor)
      }
      let cursor = pendingState ? memoryCursor : state.cursor
      // Bound each poll without returning to the head until the backlog is drained.
      // Delivery receipts are independent of the user's acknowledgement state.
      for (let batch = 0; batch < 5 && !disposed; batch++) {
        const page = await researchApi.listEvents('alert_triggered', true, 100, cursor ?? undefined, controller.signal)
        if (disposed) return
        const items = page.items ?? []
        const delivered = await browserNotificationStore.delivered(items.map(event => event.id)).catch(() => new Set<string>())
        const pending = items.filter(event => !event.acknowledgedAt && !delivered.has(event.id) && !memoryDelivered.has(event.id)).reverse()
        let next = cursor
        try {
          for (const event of pending) {
            if (disposed) break
            await deliverAlertEvent(event)
            memoryDelivered.add(event.id); pendingReceipts.add(event.id)
          }
          next = disposed ? cursor : page.nextCursor ?? null
        } finally {
          // A receipt failure must not suppress delivery or repeat an event
          // already delivered earlier in this poll or session.
          await commit([], next)
        }
        cursor = next
        if (!cursor) break
      }
  }

  const poll = async () => {
    if (running || disposed) return
    running = true
    try {
      if (navigator.locks) {
        await navigator.locks.request('opentrading:alert-delivery', { ifAvailable: true }, async lock => {
          if (lock) await deliverPending()
        })
      } else await deliverPending()
    } catch {
      // 后台轮询不应打断当前页面，下一轮会自动重试。
    } finally {
      running = false
    }
  }

  const pollWhenVisible = () => {
    if (document.visibilityState === 'visible') void poll()
  }

  onMounted(() => {
    void poll()
    timer = window.setInterval(() => void poll(), POLL_INTERVAL_MS)
    window.addEventListener('focus', pollWhenVisible)
    document.addEventListener('visibilitychange', pollWhenVisible)
    window.addEventListener('opentrading:notification-permission', pollWhenVisible)
  })

  onBeforeUnmount(() => {
    disposed = true
    controller.abort()
    if (timer !== undefined) window.clearInterval(timer)
    window.removeEventListener('focus', pollWhenVisible)
    document.removeEventListener('visibilitychange', pollWhenVisible)
    window.removeEventListener('opentrading:notification-permission', pollWhenVisible)
  })
}
