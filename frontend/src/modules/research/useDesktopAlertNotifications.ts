import { onBeforeUnmount, onMounted } from 'vue'
import { getLocalStorage, readStorageValue } from '@/utils/storage'

import { researchApi } from './api'
import {
  isWindowsNotificationEvent,
  loadDeliveredNotificationIds,
  WINDOWS_NOTIFICATION_DELIVERED_KEY,
} from './notificationEvents'

const POLL_INTERVAL_MS = 15_000

export const useDesktopAlertNotifications = () => {
  let timer: number | undefined
  let running = false

  const poll = async () => {
    if (running || !('Notification' in window) || Notification.permission !== 'granted') return
    running = true
    try {
      const storage = getLocalStorage()
      const delivered = new Set(loadDeliveredNotificationIds(storage ? readStorageValue(storage, WINDOWS_NOTIFICATION_DELIVERED_KEY) : null))
      const page = await researchApi.listEvents('alert_triggered', true, 100)
      const pending = (page.items || []).filter((event) => isWindowsNotificationEvent(event, delivered)).reverse()
      for (const event of pending) {
        new Notification(event.title, { body: event.body || event.symbol || '' })
        delivered.add(event.id)
      }
      if (pending.length > 0) {
        storage?.setItem(
          WINDOWS_NOTIFICATION_DELIVERED_KEY,
          JSON.stringify(Array.from(delivered).slice(-500)),
        )
      }
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
    if (timer !== undefined) window.clearInterval(timer)
    window.removeEventListener('focus', pollWhenVisible)
    document.removeEventListener('visibilitychange', pollWhenVisible)
    window.removeEventListener('opentrading:notification-permission', pollWhenVisible)
  })
}
