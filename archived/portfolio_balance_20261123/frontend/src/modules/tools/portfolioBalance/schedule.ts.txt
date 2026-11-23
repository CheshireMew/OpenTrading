import { addDaysToLocalIsoDate, localIsoDateDaysAgo, parseLocalIsoDate, todayLocalIsoDate, toLocalIsoDate } from '@/utils/localDate'
import type { PortfolioReviewFrequency } from './types'

export const DEFAULT_REVIEW_FREQUENCY: PortfolioReviewFrequency = 'weekly'

export const daysAgoIso = localIsoDateDaysAgo
export const todayIso = todayLocalIsoDate
export const parseIsoDate = (value: string) => parseLocalIsoDate(value)

export const shiftReviewDate = (dateText: string, frequency: PortfolioReviewFrequency) => {
  const source = parseIsoDate(dateText)
  if (!source) return todayIso()

  if (frequency === 'daily') return addDaysToLocalIsoDate(dateText, 1)
  if (frequency === 'weekly') return addDaysToLocalIsoDate(dateText, 7)
  const next = new Date(source)
  next.setMonth(next.getMonth() + (frequency === 'monthly' ? 1 : 3))
  return toLocalIsoDate(next)
}

export const diffDaysFromToday = (dateText: string) => {
  const target = parseIsoDate(dateText)
  if (!target) return 0
  const today = new Date()
  const current = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return Math.ceil((target.getTime() - current.getTime()) / 86400000)
}

