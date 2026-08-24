import { apiErrorMessage } from '@/api/request'

export type PortfolioTranslate = (key: string, params?: Record<string, unknown>) => string

export class PortfolioDataError extends Error {
  constructor(readonly key: string, readonly params?: Record<string, unknown>) {
    super(key)
    this.name = 'PortfolioDataError'
  }
}

export const toPortfolioUserError = (error: unknown, fallbackKey: string, t: PortfolioTranslate) => {
  if (error instanceof PortfolioDataError) return t(error.key, error.params)
  const fallback = t(fallbackKey)
  const message = apiErrorMessage(error, fallback).trim()
  if (!message) return fallback
  if (message.includes('Background on this error at:') || message.includes('sqlalche.me/e/')) {
    return t('portfolioBalance.feedback.historyProcessingFailed')
  }
  if (message.length > 240) {
    return `${message.slice(0, 240)}...`
  }
  return message
}

