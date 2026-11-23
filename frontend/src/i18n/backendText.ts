import i18n from './index'
import zh from './zh-CN.json'
import en from './en.json'
import { createMessageTranslator } from '@/modules/chartWorkspace/messageTranslation.mjs'

const flatten = (value: Record<string, unknown>, prefix = ''): Record<string, string> => Object.fromEntries(
  Object.entries(value).flatMap(([key, text]) => typeof text === 'string'
    ? [[prefix + key, text]]
    : Object.entries(flatten(text as Record<string, unknown>, `${prefix}${key}.`))),
)
const catalogs = [flatten(zh), flatten(en), {
  'signalLab.missing': '{count} expected dates are missing',
}]
const exactKeys = new Map(catalogs.flatMap(catalog => Object.entries(catalog)
  .filter(([, value]) => !/\{\w+\}/.test(value)).map(([key, value]) => [value, key])))

// Only call this for application-owned metadata and status messages. User
// titles, notes, code and stable API identifiers keep their original text.
export const backendText = createMessageTranslator(catalogs, (key, params) => i18n.global.t(key,
  Object.fromEntries(Object.entries(params).map(([name, value]) => [name,
    exactKeys.has(value) ? i18n.global.t(exactKeys.get(value)!) : value])),
))

export const backendRuleSummary = (value: unknown) => {
  const text = value == null ? '' : String(value)
  const translated = backendText(text)
  if (translated !== text) return translated
  const english = i18n.global.locale.value === 'en'
  return text.split('；').map(part => {
    const pair = part.match(/^([^：]+)：(.*)$/)
    if (!pair) return backendText(part)
    const numberUnit = pair[2].match(/^(-?\d+(?:\.\d+)?) (.+)$/)
    const value = numberUnit ? `${numberUnit[1]} ${backendText(numberUnit[2])}` : backendText(pair[2])
    return `${backendText(pair[1])}${english ? ': ' : '：'}${value}`
  }).join(english ? '; ' : '；')
}
