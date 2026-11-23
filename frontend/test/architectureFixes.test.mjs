import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import ts from 'typescript'
import * as vue from 'vue'

const require = createRequire(import.meta.url)
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return {promise, resolve} }
const ref = value => ({value})
const compile = source => ts.transpileModule(source, {compilerOptions: {module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
function load(file, modules={}) {
  const exports = {}
  new Function('require','exports',compile(fs.readFileSync(new URL(file,import.meta.url),'utf8')))(id => id in modules ? modules[id] : require(id),exports)
  return exports
}
function actualFunction(name, state, file='../src/views/ChartWorkspace.vue') {
  const source = fs.readFileSync(new URL(file,import.meta.url),'utf8').match(/<script setup(?: lang="ts")?>([\s\S]*?)<\/script>/)[1]
  const ast = ts.createSourceFile('component.ts',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TS)
  const node = ast.statements.find(node => ts.isFunctionDeclaration(node) && node.name.text === name ||
    ts.isVariableStatement(node) && node.declarationList.declarations.some(value => value.name.getText(ast) === name))
  return new Function('state',`with(state){${compile(node.getText(ast))};return ${name}}`)(state)
}
const market={toBaseSymbol:value=>String(value).split('/')[0].toUpperCase(),isIndexSymbol:()=>false,readCashSymbolPrices:()=>({USD:1,USDT:1})}

function asyncPage(kind, api) {
  let unmount
  const page = load(`../src/modules/tools/use${kind}Page.ts`, {
    vue: { ...vue, onMounted() {}, onBeforeUnmount: fn => { unmount = fn } },
    '@/theme/palette.mjs': { DARK_PALETTE: {} }, '@/composables/useTheme': { useTheme: () => ({ theme: vue.ref('light') }) },
    'vue-i18n': { useI18n: () => ({ t: key => key, locale: vue.ref('zh-CN') }) }, 'vue-router': { useRoute: () => ({ query: {} }) },
    '@/composables/pageSnapshot': { PAGE_SNAPSHOT_KEYS: {}, createPersistentPageSnapshot: () => ({ initial: {} }) },
    '@/modules/market': { ensureSymbolCatalogLoaded: async () => {}, isIndexSymbol: () => false },
    '@/composables/useRequestError': { useRequestError: () => ({ error: vue.ref(''), setError() {}, clearError() {} }) },
    '@/composables/useUserPreferences': { useUserPreferences: () => ({ timezone: vue.ref('UTC'), setTimezone() {} }) },
    '@/composables/useMoney': { useMoney: () => ({ displayCurrency: vue.ref('USD') }) },
    './pageSnapshots': { createEmptyCompareSnapshot: () => ({ config: { symbolA: 'BTC', symbolB: 'ETH', days: 30, timeframe: '1d' } }),
      createEmptyDcaSnapshot: () => ({}), createEmptyDcaConfig: () => ({ symbol: 'BTC', amount: 100, start_date: '', investment_time: '12:00', timezone: 'UTC', strategy: 'standard', strategy_params: {} }) },
    './useDcaMarketContext': { createEmptyMarketData: () => ({}), useDcaMarketContext: () => ({ marketData: {}, fetchMarketIndicators: async () => {} }) },
    './useDcaCharts': { useDcaCharts: () => ({ renderCharts() {} }) },
    '@/utils/localDate': { localIsoDateDaysAgo: () => '2020-01-01', todayLocalIsoDate: () => '2026-11-14' },
    './api': { toolsApi: api },
  })[`use${kind}Page`]()
  if (kind === 'Dca') page.ready.value = true
  return { page, unmount: () => unmount() }
}

for (const kind of ['Compare', 'Dca']) for (const action of ['change', 'unmount']) test(`${kind} ignores responses after ${action}`, async () => {
  const pending = deferred()
  const { page, unmount } = asyncPage(kind, { comparePairs: () => pending.promise, runSimulation: () => pending.promise })
  const running = kind === 'Compare' ? page.fetchComparisonData() : page.runSimulation()
  await Promise.resolve(); await Promise.resolve()
  if (action === 'unmount') unmount()
  else if (kind === 'Compare') page.config.symbolA = 'SOL'
  else page.config.amount = 200
  pending.resolve({ data_a: [{ close: 1 }], data_b: [{ close: 2 }], ratio_ohlc: [{ close: 0.5 }], history: [{ price: 1 }] })
  await running
  assert.equal(kind === 'Compare' ? page.hasData.value : Boolean(page.result.value), false)
  assert.equal(page.loading.value, false)
  unmount()
})
