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

const POLL_INTERVAL_MS = 3_000

export const useDesktopAlertNotifications = () => {
  let timer: number | undefined
  let running = false
  let disposed = false
  const memoryDelivered = new Set<string>()

  const deliverPending = async () => {
      if (PUBLIC_SITE) await evaluateBrowserAlerts()
      const storage = getLocalStorage()
      let stored: string | null = null
      try { stored = storage ? readStorageValue(storage, WINDOWS_NOTIFICATION_DELIVERED_KEY) : null } catch { /* In-memory delivery remains available. */ }
      const delivered = new Set([...memoryDelivered, ...loadDeliveredNotificationIds(stored)])
      const page = await researchApi.listEvents('alert_triggered', true, 100)
      if (disposed) return
      const pending = (page.items || []).filter(event => !event.acknowledgedAt && !delivered.has(event.id)).reverse()
      for (const event of pending) {
        if (disposed) break
        await deliverAlertEvent(event)
        delivered.add(event.id)
        memoryDelivered.add(event.id)
      }
      if (pending.length > 0) {
        try { storage?.setItem(
          WINDOWS_NOTIFICATION_DELIVERED_KEY,
          JSON.stringify(Array.from(delivered).slice(-500)),
        ) } catch { /* A full/read-only store must not interrupt delivery. */ }
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
    if (timer !== undefined) window.clearInterval(timer)
    window.removeEventListener('focus', pollWhenVisible)
    document.removeEventListener('visibilitychange', pollWhenVisible)
    window.removeEventListener('opentrading:notification-permission', pollWhenVisible)
  })
}
