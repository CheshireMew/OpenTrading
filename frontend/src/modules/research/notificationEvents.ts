import type { ResearchEventResponse } from './contracts'

export const WINDOWS_NOTIFICATION_DELIVERED_KEY = 'heimdall.research.windowsNotifications.v1'

export const loadDeliveredNotificationIds = (raw: string | null): string[] => {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string').slice(-500) : []
  } catch {
    return []
  }
}

export const isWindowsNotificationEvent = (event: ResearchEventResponse, deliveredIds: Set<string>): boolean => {
  if (event.kind !== 'alert_triggered' || event.acknowledgedAt || deliveredIds.has(event.id)) return false
  const channels: unknown = event.payload?.notificationChannels
  return Array.isArray(channels) && channels.includes('windows')
}
