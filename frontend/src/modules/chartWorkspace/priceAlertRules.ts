import type { ResearchAlertResponse, ResearchAlertCreateCommand } from '@/modules/research/contracts'

export const finishedPriceAlert = (alert: ResearchAlertResponse) => !alert.enabled && !!alert.lastTriggeredAt && alert.configuration?.once !== false

export function alertCommand(alert: ResearchAlertResponse): ResearchAlertCreateCommand {
    return { symbol: alert.symbol, name: alert.name, metric: alert.metric, operator: alert.operator, threshold: alert.threshold,
      secondaryThreshold: alert.secondaryThreshold, cooldownMinutes: alert.cooldownMinutes, enabled: alert.enabled,
      notificationChannels: alert.notificationChannels, configuration: alert.configuration, watchItemId: alert.watchItemId }
  }
