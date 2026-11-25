import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import { buildSync } from 'esbuild'
import ts from 'typescript'
import * as vue from 'vue'

const require = createRequire(import.meta.url)
function load(path, modules = {}) {
  const content = fs.readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')
  const code = ts.transpileModule(content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(id => modules[id] ?? (id === 'vue' ? vue : require(id)), exports)
  return exports
}
const requestBundle = buildSync({ entryPoints: [new URL('../src/api/request.ts', import.meta.url).pathname.replace(/^\/(\w:)/, '$1')], bundle: true, platform: 'node', format: 'cjs', write: false }).outputFiles[0].text
const requestModule = { exports: {} }
new Function('require', 'module', 'exports', requestBundle)(require, requestModule, requestModule.exports)
const requestErrors = load('composables/useRequestError.ts', { '@/api/request': requestModule.exports })
const utcDates = load('utils/utcDate.ts')
const { render } = vue.createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), insert() {}, remove() {}, patchProp() {}, setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null })
const settle = async () => { for (let i = 0; i < 12; i++) await vue.nextTick() }
const mount = factory => {
  let state
  const host = {}
  render(vue.h({ setup() { state = factory(); return () => null } }), host)
  return { get state() { return state }, unmount: () => render(null, host) }
}
const deferred = () => { let resolve, reject; const promise = new Promise((ok, fail) => { resolve = ok; reject = fail }); return { promise, resolve, reject } }

test('a stored transport error follows language changes and is cleared after recovery', () => {
  const locale = vue.ref('zh')
  const errors = requestErrors.useRequestError(key => locale.value + ':' + key)
  errors.setError(new SyntaxError("Expected property name or '}' in JSON at position 1 (line 1 column 2)"), 'retry')
  assert.equal(errors.error.value, 'zh:retry')
  locale.value = 'en'
  assert.equal(errors.error.value, 'en:retry')
  errors.clearError()
  assert.equal(errors.error.value, '')
})

test('Web3 details publish successful sources before a slow audit fails and recover on retry', async () => {
  const audit = deferred()
  const api = { getBinanceWeb3TokenDynamic: async () => ({ price: 12 }),
    getBinanceWeb3TokenAudit: () => audit.promise,
    getBinanceWeb3TokenKline: async () => ({ items: [{ open_time: 60_000, open: 1, high: 2, low: 1, close: 2, volume: 3 }] }) }
  const { useWeb3HeatRankPanel } = load('modules/market/useWeb3HeatRankPanel.ts', {
    'vue-i18n': { useI18n: () => ({ t: (key, values) => key + (values?.sources ? ':' + values.sources : '') }) },
    './api': { binanceWeb3Api: api }, './web3MarketShared': {},
    './web3MarketWarmSnapshot': { web3HeatRankWarmSnapshot: { read() {}, write() {} } },
  })
  const mounted = mount(() => useWeb3HeatRankPanel(vue.ref('56'))), state = mounted.state
  state.openWeb3Token({ chain_id: '56', contract_address: '0xA', platform: 'bsc' })
  await settle()
  assert.equal(state.web3Dynamic.value.price, 12)
  assert.equal(state.web3ChartData.value.length, 1)
  assert.equal(state.web3DetailLoading.value, true)
  audit.reject(new Error('audit only unavailable'))
  await settle()
  assert.equal(state.web3DetailLoading.value, false)
  assert.match(state.web3DetailError.value, /tokenDetailPartialFailed.*detailSources.audit/)
  assert.equal(state.web3ChartData.value.length, 1)
  api.getBinanceWeb3TokenAudit = async () => ({ status: 'verified' })
  await state.retryWeb3TokenDetail()
  assert.equal(state.web3Audit.value.status, 'verified')
  assert.equal(state.web3DetailError.value, '')
  mounted.unmount()
})

test('Web3 old token responses and disposed detail requests cannot replace the selected token', async () => {
  const old = deferred(), late = deferred()
  const { useWeb3HeatRankPanel } = load('modules/market/useWeb3HeatRankPanel.ts', {
    'vue-i18n': { useI18n: () => ({ t: key => key }) },
    './api': { binanceWeb3Api: {
      getBinanceWeb3TokenDynamic: args => args.contract_address === 'A' ? old.promise : args.contract_address === 'C' ? late.promise : Promise.resolve({ token: 'B' }),
      getBinanceWeb3TokenAudit: async () => ({}), getBinanceWeb3TokenKline: async () => ({ items: [] }),
    } }, './web3MarketShared': {}, './web3MarketWarmSnapshot': { web3HeatRankWarmSnapshot: { read() {}, write() {} } },
  })
  const mounted = mount(() => useWeb3HeatRankPanel(vue.ref('56'))), state = mounted.state
  const token = address => ({ chain_id: '56', contract_address: address, platform: 'bsc' })
  state.openWeb3Token(token('A')); state.openWeb3Token(token('B'))
  await settle(); old.resolve({ token: 'A' }); await settle()
  assert.equal(state.web3Dynamic.value.token, 'B')
  state.openWeb3Token(token('C')); await settle(); mounted.unmount()
  late.resolve({ token: 'C' }); await settle()
  assert.equal(state.web3Dynamic.value, null)
})

test('liquidity failures give localized recovery and retain the last successful data', async () => {
  const locale = vue.ref('zh')
  const { useSignalResource } = load('modules/market/signalLab.ts', {
    '@/api/request': requestModule.exports, '@/composables/useRequestError': requestErrors,
    '@/i18n': { default: { global: { t: key => locale.value + ':' + key } } },
  })
  const mounted = mount(useSignalResource), state = mounted.state
  await state.load(async () => ({ value: 1 }))
  await state.load(async () => { throw new requestModule.exports.ApiRequestError('Request failed with status code 503', { status: 503 }) })
  assert.deepEqual(state.data.value, { value: 1 })
  assert.equal(state.error.value, 'zh:signalLab.readFailed')
  locale.value = 'en'
  assert.equal(state.error.value, 'en:signalLab.readFailed')
  await state.load(async () => ({ value: 2 }))
  assert.equal(state.error.value, '')
  mounted.unmount()
})

test('local input guidance keeps its translation key until it is displayed', () => {
  const locale = vue.ref('zh')
  const errors = requestErrors.useRequestError(key => locale.value + ':' + key)
  errors.setError(new requestErrors.LocalizedRequestError('invalidParameters'), 'retry')
  assert.equal(errors.error.value, 'zh:invalidParameters')
  locale.value = 'en'
  assert.equal(errors.error.value, 'en:invalidParameters')
})

const storage = {
  PAGE_SNAPSHOT_KEYS: { compare: 'compare', dca: 'dca' },
  createPersistentPageSnapshot: (_key, _normalize, initial) => ({ initial, hasStoredData: false, bind: () => () => {} }),
  isRecord: v => v && typeof v === 'object' && !Array.isArray(v),
  readNumber: (v, fallback) => typeof v === 'number' ? v : fallback,
  readString: (v, fallback) => typeof v === 'string' ? v : fallback,
}
const snapshots = load('modules/tools/pageSnapshots.ts', { '@/composables/pageSnapshot': storage })
const contract = {
  compare_defaults: { symbol_a: 'BTC', symbol_b: 'ETH', days: 30, timeframe: '1d' },
  dca_defaults: { symbol: 'BTC/USDT', amount: 100, start_date: '', investment_time: '00:00', timezone: 'Asia/Shanghai', strategy: 'standard' },
  dca_strategies: ['standard'], dca_multiplier_default: 1, dca_max_days: 3650,
}
for (const page of ['Compare', 'Dca']) {
  test(page + ' retries failed initialization and restores usable configuration', async () => {
    let failing = true, loads = 0
    const api = { getContract: async () => { loads++; if (failing) throw new Error('Network Error'); return contract },
      comparePairs: async () => ({ data_a: [{}], data_b: [{}], ratio_ohlc: [{}], statistics: {} }) }
    const modules = {
      '@/theme/palette.mjs': { DARK_PALETTE: {} },
      'vue-i18n': { useI18n: () => ({ t: key => key, locale: vue.ref('zh-CN') }) },
      'vue-router': { useRoute: () => ({ query: {} }) },
      '@/composables/pageSnapshot': storage,
      '@/modules/market': { ensureSymbolCatalogLoaded: async () => {}, isIndexSymbol: () => false },
      '@/composables/useTheme': { useTheme: () => ({ theme: vue.ref('light') }) },
      '@/composables/useRequestError': requestErrors,
      './api': { toolsApi: api }, './pageSnapshots': snapshots,
      '@/composables/useUserPreferences': { useUserPreferences: () => ({ timezone: vue.ref('Asia/Shanghai'), setTimezone() {} }) },
      '@/composables/useMoney': { useMoney: () => ({ displayCurrency: vue.ref('USD'), fromDisplayAmount: Number, formatDisplayNumber: Number, formatMoney: String }) },
      './useDcaMarketContext': { createEmptyMarketData: () => ({}), useDcaMarketContext: () => ({ marketData: vue.reactive({}), fetchMarketIndicators: async () => {} }) },
      './useDcaCharts': { useDcaCharts: () => ({ renderCharts() {} }) },
      '@/utils/localDate': { localIsoDateDaysAgo: () => '2016-01-01', todayLocalIsoDate: () => '2026-11-06' },
    }
    const name = 'use' + page + 'Page'
    const mounted = mount(load('modules/tools/' + name + '.ts', modules)[name])
    await settle()
    assert.equal(mounted.state.ready.value, false)
    assert.ok((mounted.state.initializationError ?? mounted.state.errorMessage).value)
    assert.equal(mounted.state.initializing.value, false)
    failing = false
    await mounted.state.initialize()
    assert.equal(loads, 2)
    assert.equal(mounted.state.ready.value, true)
    assert.equal((mounted.state.initializationError ?? mounted.state.errorMessage).value, '')
    assert.equal((mounted.state.canRunSimulation ?? mounted.state.canCompare).value, true)
    mounted.unmount()
  })
}

test('legacy UTC timestamps display the same instant as explicit UTC in Shanghai', () => {
  const { useDateTime } = load('composables/useDateTime.ts', {
    '@/utils/utcDate': utcDates,
    './useUserPreferences': { useUserPreferences: () => ({ timezone: vue.ref('Asia/Shanghai') }) },
    '@/i18n': { default: { global: { locale: vue.ref('zh-CN') } } },
  })
  const dates = useDateTime()
  assert.equal(dates.formatDateTime('2026-11-06T12:52:00'), dates.formatDateTime('2026-11-06T12:52:00Z'))
  assert.match(dates.formatDateTime('2026-11-06T12:52:00'), /20:52/)
})

test('dates follow the app language independently of the browser language', () => {
  const locale = vue.ref('zh-CN')
  const { useDateTime } = load('composables/useDateTime.ts', {
    '@/utils/utcDate': utcDates,
    './useUserPreferences': { useUserPreferences: () => ({ timezone: vue.ref('Asia/Shanghai') }) },
    '@/i18n': { default: { global: { locale } } },
  })
  const dates = useDateTime()
  const chinese = dates.formatDate('2026-11-06T12:52:00Z')
  locale.value = 'en'
  assert.notEqual(dates.formatDate('2026-11-06T12:52:00Z'), chinese)
  assert.match(dates.formatDate('2026-11-06T12:52:00Z'), /Nov/)
  assert.equal(dates.formatDate('2026-11-06'), '2026-11-06')
})

test('market failures with empty board objects are unavailable, while healthy empty results remain valid', async () => {
  let payload = { monitor: { items: [], updated_at: null }, spot_boards: { gainers: { items: [] } }, contract_boards: { gainers: { items: [] } }, load_errors: ['现货榜单', 'U本位24H'], refresh_status: { boards_ready: true, monitor_ready: true, snapshot_ready: false } }
  const { useBinanceMarketPageResource } = load('modules/market/useBinanceMarketPageResource.ts', {
    './api': { binanceMarketApi: { getBinanceMarketPage: async () => payload } },
    './binanceMarketWarmSnapshot': { binanceMarketWarmSnapshot: { read: () => null, write() {} } },
    './binanceMarketShared': { EMPTY_RESPONSE: { items: [] } },
  })
  const scope = vue.effectScope()
  const state = scope.run(() => useBinanceMarketPageResource(vue.ref(10), vue.ref(false), vue.ref('zh-CN'), key => key))
  await state.fetchData()
  assert.equal(state.spotAvailable.value, false)
  assert.equal(state.contractAvailable.value, false)
  assert.equal(state.monitorAvailable.value, false)
  assert.ok(state.error.value)
  payload = { ...payload, spot_boards: { gainers: { items: [{ symbol: 'BTCUSDT' }] } } }
  await state.fetchData()
  assert.equal(state.spotAvailable.value, true)
  assert.equal(state.contractAvailable.value, false)
  payload = { ...payload, monitor: { items: [], updated_at: '2026-11-13T00:00:00Z' }, load_errors: [], refresh_status: { boards_ready: true, monitor_ready: true, snapshot_ready: true } }
  await state.fetchData()
  assert.equal(state.contractAvailable.value, true)
  assert.equal(state.monitorAvailable.value, true)
  assert.equal(state.error.value, '')
  scope.stop()
})

test('address rankings use an explicit chain and format the API win-rate ratio', async () => {
  const formats = load('modules/format.ts', {
    '@/composables/useDateTime': {}, '@/composables/useMoney': {},
    '@/utils/number': { asNumber: value => value == null || !Number.isFinite(Number(value)) ? null : Number(value) },
  })
  const requests = []
  const { useWeb3MarketRankPage } = load('modules/market/useWeb3MarketRankPage.ts', {
    '@/theme/palette.mjs': { DARK_PALETTE: {} }, 'vue-i18n': { useI18n: () => ({ t: key => key }) },
    '@/composables/useTheme': { useTheme: () => ({ theme: vue.ref('light') }) }, '@/modules/format': formats,
    './api': { binanceWeb3Api: { getBinanceWeb3AddressPnlRank: async args => { requests.push(args); return { items: [{ address: args.chain_id, win_rate: 1 / 3 }] } } } },
    './binanceMarketShared': {},
    './useWeb3HeatRankPanel': { useWeb3HeatRankPanel: () => ({ web3UpdatedAt: vue.ref(null), fetchWeb3HeatRank: async () => {} }) },
    './web3MarketShared': { WEB3_ALL_CHAIN_ID: 'all', WEB3_SUPPORTED_CHAIN_OPTIONS: [{ value: '56', label: 'BSC' }, { value: '1', label: 'Ethereum' }], WEB3_KLINE_INTERVALS: [] },
  })
  const mounted = mount(useWeb3MarketRankPage)
  await settle()
  assert.equal(mounted.state.addressChainId.value, '56')
  assert.equal(requests[0].chain_id, '56')
  assert.equal(mounted.state.formatWinRate(1 / 3), '33.33%')
  assert.equal(mounted.state.formatWinRate(0), '0.00%')
  assert.equal(mounted.state.formatWinRate(null), '--')
  mounted.state.addressChainId.value = '1'
  await settle()
  assert.equal(requests.at(-1).chain_id, '1')
  assert.equal(mounted.state.addressPnl.value[0].address, '1')
  assert.ok(mounted.state.addressChainOptions.every(option => option.value !== 'all'))
  mounted.unmount()
})
