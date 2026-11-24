import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import * as vue from 'vue'
import { createI18n } from 'vue-i18n'
import { createMessageTranslator } from '../src/modules/chartWorkspace/messageTranslation.mjs'

const zh = JSON.parse(fs.readFileSync(new URL('../src/i18n/zh-CN.json', import.meta.url)))
const en = JSON.parse(fs.readFileSync(new URL('../src/i18n/en.json', import.meta.url)))
const flatten = (object, prefix = '') => Object.fromEntries(Object.entries(object).flatMap(([key, value]) =>
  typeof value === 'string' ? [[prefix + key, value]] : Object.entries(flatten(value, prefix + key + '.'))))

function load(path, modules) {
  const source = fs.readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(id => id === 'vue' ? vue : modules[id], exports)
  return exports
}

test('all application messages compile in both languages with the same parameters', () => {
  const catalogs = { 'zh-CN': flatten(zh), en: flatten(en) }
  assert.deepEqual(Object.keys(catalogs.en).sort(), Object.keys(catalogs['zh-CN']).sort())
  const errors = []
  const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': zh, en }, onError: error => errors.push(error) })
  for (const [locale, messages] of Object.entries(catalogs)) {
    i18n.global.locale.value = locale
    for (const [key, text] of Object.entries(messages)) {
      const params = text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort()
      assert.deepEqual(params(text), params(catalogs['zh-CN'][key]), key)
      assert.ok(i18n.global.t(key, Object.fromEntries(params(text).map(name => [name, 'sample']))), key)
    }
  }
  assert.deepEqual(errors, [])
})

test('market names and existing backend messages follow locale changes without altering identifiers', () => {
  const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': zh, en } })
  const modules = { '@/i18n': { default: i18n }, '@/i18n/zh-CN.json': { default: zh }, '@/i18n/en.json': { default: en },
    './zh-CN.json': { default: zh }, './en.json': { default: en }, './index': { default: i18n },
    './messageTranslation.mjs': { createMessageTranslator }, '@/modules/chartWorkspace/messageTranslation.mjs': { createMessageTranslator } }
  const labels = load('modules/chartWorkspace/locale.ts', modules)
  const { backendText } = load('i18n/backendText.ts', modules)
  assert.equal(labels.exchangeLabel('BINANCE'), '币安')
  assert.equal(labels.workspaceMarketLabel('binance:spot:BTCUSDT'), '币安现货')
  assert.equal(labels.workspaceMarketLabel('binance:usdm:ETHUSDT'), '币安永续')
  assert.equal(labels.messageText('历史 OHLC 成交模拟不是逐 tick 还原'), zh.chartWorkspace.capHistory)
  assert.equal(backendText('cross 信号门槛 ATR 系数'), zh.backendText.adaptive_cloud_parameters_trigger_mult_label)
  assert.equal(backendText('Fed 总资产减 TGA 与 ON RRP 后的观察项，不纳入综合评分。'), zh.backendText.macroDescription_NET_LIQUIDITY)
  assert.equal(backendText('我的 RSI / API 笔记'), '我的 RSI / API 笔记')
  i18n.global.locale.value = 'en'
  assert.equal(labels.exchangeLabel('binance'), 'Binance')
  assert.equal(labels.workspaceMarketLabel('binance:spot:BTCUSDT'), 'Binance spot')
  assert.equal(labels.messageText('暂不支持 Bar Magnifier 成交模拟'), en.chartWorkspace.magnifierUnsupported)
  assert.equal(backendText('cross 信号门槛 ATR 系数'), en.backendText.adaptive_cloud_parameters_trigger_mult_label)
})

test('native dates use the app locale and restore canvas methods on disposal', async () => {
  const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: {} })
  const { chartDateText, localizeCanvasDates } = load('modules/chartWorkspace/canvasLocale.ts', { '@/i18n': { default: i18n } })
  assert.equal(chartDateText("Sun 22 Nov '26 22:00"), '26年11月22日 周日 22:00')
  assert.equal(chartDateText('Nov 24'), '11月24日')
  assert.equal(chartDateText('Nov'), '11月')
  assert.equal(chartDateText('RSI 14'), 'RSI 14')
  const drawn = []
  const contexts = Array.from({ length: 3 }, () => ({ fillText: text => drawn.push(text), strokeText: text => drawn.push(text), measureText: text => ({ width: text.length }) }))
  const original = contexts.map(context => ({ ...context }))
  let repaints = 0
  const dispose = localizeCanvasDates({ querySelectorAll: () => contexts.map(context => ({ getContext: () => context })) }, () => repaints++)
  contexts[0].fillText('Nov 24', 1, 2)
  assert.equal(drawn.pop(), '11月24日')
  assert.equal(contexts[2].measureText('Nov 24').width, '11月24日'.length)
  assert.equal(contexts[1].fillText, original[1].fillText)
  i18n.global.locale.value = 'en'
  await vue.nextTick()
  assert.equal(repaints, 1)
  contexts[0].fillText('Nov 24', 1, 2)
  assert.equal(drawn.pop(), 'Nov 24')
  dispose()
  for (let index = 0; index < contexts.length; index++) assert.deepEqual(contexts[index], original[index])
  i18n.global.locale.value = 'zh-CN'
  await vue.nextTick()
  assert.equal(repaints, 1)
})
