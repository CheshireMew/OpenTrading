import i18n from '@/i18n'
import zh from '@/i18n/zh-CN.json'
import en from '@/i18n/en.json'
import { createMessageTranslator } from './messageTranslation.mjs'

export const cw = (key: string, params: Record<string, string | number> = {}) =>
  i18n.global.t('chartWorkspace.' + key, params)

export const messageText = createMessageTranslator(
  [zh.chartWorkspace, en.chartWorkspace], cw,
)

export function formatNumber(value: unknown, digits = 4): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString(i18n.global.locale.value, { maximumFractionDigits: digits }) : '—'
}

export function formatDate(value: number, timeOnly = false): string {
  const date = new Date(value)
  return timeOnly ? date.toLocaleTimeString(i18n.global.locale.value) : date.toLocaleString(i18n.global.locale.value)
}
