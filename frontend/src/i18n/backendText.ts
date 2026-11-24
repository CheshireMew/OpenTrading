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
  'backendText.adaptive_cloud_description': 'original 按用户提供的 Pine 规则计算；cross 为截图拟合的穿越候选。保留每根指标和条件，不自动把 TP/SL 标签当成交易订单。',
  'backendText.adaptive_cloud_parameters_trigger_mult_label': 'cross 信号门槛 ATR 系数',
  'backendText.adaptive_cloud_parameters_volume_mult_label': 'original 成交量倍数',
  'backendText.adaptive_cloud_parameters_cooldown_label': 'original 冷却根数（须严格大于）',
  'backendText.macroDescription_NET_LIQUIDITY': 'Fed 总资产减 TGA 与 ON RRP 后的观察项，不纳入综合评分。',
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
