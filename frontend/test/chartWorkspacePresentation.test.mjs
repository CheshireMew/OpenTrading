import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { computed } from 'vue'
import { createI18n } from 'vue-i18n'
import { payoffRatio } from '../src/modules/chartWorkspace/metrics.mjs'
import { createMessageTranslator } from '../src/modules/chartWorkspace/messageTranslation.mjs'

const zh = JSON.parse(fs.readFileSync(new URL('../src/i18n/zh-CN.json', import.meta.url))).chartWorkspace
const en = JSON.parse(fs.readFileSync(new URL('../src/i18n/en.json', import.meta.url))).chartWorkspace

test('historical closed-trade totals distinguish average win/loss from profit factor', () => {
  // Two wins (80 + 20), one loss (-25) and three breakeven trades.
  const summary = Object.freeze({ grossprofit: 100, grossloss: -25, wintrades: 2,
    losstrades: 1, eventrades: 3, profit_factor: 4, openprofit: 9999, commission: 12 })
  assert.equal(payoffRatio(summary), 2)
  assert.equal(summary.profit_factor, 4)
  // Commission is already reflected according to the engine's accounting basis;
  // do not subtract it again or include open P&L / breakeven counts.
  assert.equal(payoffRatio({ ...summary, grossloss: 25 }), 2)
})

test('one-sided trades and missing historical evidence have no observed win/loss ratio', () => {
  for (const summary of [undefined, {},
    { grossprofit: 100, grossloss: 0, wintrades: 2, losstrades: 0 },
    { grossprofit: 0, grossloss: -25, wintrades: 0, losstrades: 1 },
    { grossprofit: 100, grossloss: -25, wintrades: null, losstrades: 1 },
    { grossprofit: Infinity, grossloss: -25, wintrades: 2, losstrades: 1 },
  ]) assert.equal(payoffRatio(summary), null)
})

test('locale switches update labels and saved diagnostics while retaining source details', () => {
  const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': zh, en } })
  const translate = createMessageTranslator([zh, en], (key, params) => i18n.global.t(key, params))
  const display = computed(() => [i18n.global.t('payoffRatio'), translate('原版脚本只读，请另存副本')])
  assert.deepEqual(display.value, ['盈亏比', zh.readonlyCopy])
  i18n.global.locale.value = 'en'
  assert.deepEqual(display.value, ['Average win / loss', en.readonlyCopy])
  assert.equal(translate('Error: 暂不支持 OCA 订单联动（第 8 行，第 3 列）'),
    'OCA order groups are unsupported (line 8, column 3)')
  assert.equal(translate('ETH 不支持 1m 周期'), 'ETH does not support the 1m timeframe')
  assert.equal(translate('脚本编译失败（第 2 行，第 4 列）：Unexpected token "原版"'),
    'Script compilation failed (line 2, column 4): Unexpected token "原版"')
  const log = translate('我的测试 v2 已在 c1 运行')
  assert.equal(log, '我的测试 v2 is running on c1')
  assert.equal(translate('Unknown compiler error: "我的指标"'), 'Unknown compiler error: "我的指标"')
  i18n.global.locale.value = 'zh-CN'
  assert.equal(translate(log), '我的测试 v2 已在 c1 运行')
  assert.deepEqual(display.value, ['盈亏比', zh.readonlyCopy])
})

test('workspace messages compile with matching placeholders in both locales', () => {
  assert.deepEqual(Object.keys(en).sort(), Object.keys(zh).sort())
  const errors = []
  const i18n = createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': zh, en },
    onError: error => errors.push(error) })
  for (const locale of ['zh-CN', 'en']) {
    i18n.global.locale.value = locale
    for (const [key, message] of Object.entries(locale === 'en' ? en : zh)) {
      const names = [...message.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort()
      const expected = [...zh[key].matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort()
      assert.deepEqual(names, expected, key)
      assert.ok(i18n.global.t(key, Object.fromEntries(names.map(name => [name, 'sample']))))
    }
  }
  assert.deepEqual(errors, [])
})
