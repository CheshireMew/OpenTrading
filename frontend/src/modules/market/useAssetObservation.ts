import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { apiGet } from '@/api/request'
import { useRequestError } from '@/composables/useRequestError'
import { chartApi, type ChartSymbol } from '@/modules/chartWorkspace/api'
import { getLocalStorage } from '@/utils/storage'
import { useSymbolCatalog } from './symbolCatalog'
import { analyzeObservation, DAY_MS, normalizeObservationBars, type PeakBasis } from './assetObservation'
import type { OhlcvPointResponse } from './contracts'

const STORAGE_KEY = 'opentrading:asset-observation-symbol'
const DEFAULT_SYMBOL = 'binance:spot:BTCUSDT'
const HISTORY_PAGE_SIZE = 1000

type AssetHistory = {
  bars: OhlcvPointResponse[]
  source: string
  closeOnly: boolean
  incomplete: boolean
}

function savedSymbol(): string {
  try {
    const storage = getLocalStorage()
    const selected = storage?.getItem(STORAGE_KEY)
    if (selected) return selected
    const legacy = JSON.parse(storage?.getItem('opentrading:asset-observation') || 'null')?.symbol
    if (typeof legacy === 'string') return legacy
  } catch { /* Storage access or a legacy value can fail. */ }
  return DEFAULT_SYMBOL
}

async function loadChartHistory(instrument: ChartSymbol, signal: AbortSignal): Promise<AssetHistory> {
  const bars: OhlcvPointResponse[] = []
  let end: number | undefined
  let source = instrument.exchange, closeOnly = !!instrument.close_only
  for (;;) {
    const history = await chartApi.bars({ symbol: instrument.id, timeframe: '1d', limit: HISTORY_PAGE_SIZE, ...(end === undefined ? {} : { end }) }, signal)
    source = history.source
    closeOnly = !!history.symbol.close_only
    for (const row of history.bars) {
      bars.push({ timestamp: row.time, open: row.open, high: row.high, low: row.low, close: row.close, volume: row.volume ?? 0 })
    }
    if (history.bars.length < HISTORY_PAGE_SIZE) break
    const nextEnd = Math.min(...history.bars.map(row => row.time)) - 1
    if (end !== undefined && nextEnd >= end) throw new Error('Daily history did not advance')
    end = nextEnd
  }
  return { bars, source, closeOnly, incomplete: false }
}

export function useAssetObservation() {
  const { t } = useI18n()
  const catalog = useSymbolCatalog()
  const symbols = shallowRef<ChartSymbol[]>([])
  const activeSymbolId = ref('')
  const selected = savedSymbol()
  const basis = ref<PeakBasis>('high')
  const snapshot = shallowRef<(AssetHistory & { instrument: ChartSymbol }) | null>(null)
  const loading = ref(false)
  const { error, setError, clearError } = useRequestError(t)
  let sequence = 0
  let controller: AbortController | null = null
  let disposed = false
  const data = computed(() => snapshot.value?.instrument.id === activeSymbolId.value ? snapshot.value : null)
  const stats = computed(() => data.value ? analyzeObservation(data.value.bars, data.value.closeOnly ? 'close' : basis.value) : null)
  const instrument = computed(() => data.value?.instrument ?? symbols.value.find(item => item.id === activeSymbolId.value))
  const isIndex = computed(() => instrument.value?.market === 'index')
  const stale = computed(() => !!stats.value && Date.now() - stats.value.latest.timestamp > (isIndex.value ? 5 : 2) * DAY_MS)
  async function refreshSymbols() {
    const loaded = await chartApi.symbols()
    if (!disposed) symbols.value = loaded.filter(item => item.timeframes.includes('1d'))
  }

  async function readHistory(instrument: ChartSymbol, signal: AbortSignal): Promise<AssetHistory> {
    if (instrument.market === 'index') {
      const history = await apiGet('get_index_history', { query: { symbol: instrument.symbol, timeframe: '1d', start_date: '1970-01-01' }, timeout: 90000, signal })
      return { bars: history.data ?? [], source: history.source, closeOnly: !!history.is_close_only, incomplete: false }
    }
    // The shared market store only covers its configured spot pairs.
    // Other chart symbols keep their own exchange and market via chart bars.
    if (instrument.market === 'spot') {
      await catalog.loadSymbols().catch(() => undefined)
      const configured = catalog.symbols.value.find(item => item.symbol === instrument.name && item.asset_class === 'crypto' && item.exchange?.toLowerCase() === instrument.exchange)
      if (configured) {
        const startDate = instrument.id === DEFAULT_SYMBOL ? '2017-08-17' : '2010-01-01'
        const [history, tail] = await Promise.all([
          apiGet('get_market_full_history', { query: { symbol: configured.symbol, timeframe: '1d', start_date: startDate }, timeout: 90000, signal }),
          instrument.exchange === 'binance'
            ? apiGet('get_binance_market_klines', { query: { symbol: instrument.symbol, market: 'spot', interval: '1d', limit: 2 }, timeout: 30000, signal }).catch(() => null)
            : Promise.resolve(null),
        ])
        const bars = [...(history.items || []), ...(tail?.items || [])].filter(row => row.timestamp >= Date.parse(startDate))
        const first = bars.reduce((date, row) => Math.min(date, row.timestamp), Infinity)
        const incomplete = (history.coverage?.missing_ranges || []).some(gap => gap.end_ts > first)
        return { bars, incomplete, source: instrument.exchange, closeOnly: false }
      }
    }
    return loadChartHistory(instrument, signal)
  }

  async function load() {
    const requestId = ++sequence
    controller?.abort()
    controller = new AbortController()
    const signal = controller.signal
    loading.value = true
    clearError()
    try {
      if (!symbols.value.length) {
        const loaded = await chartApi.symbols()
        if (requestId !== sequence) return
        symbols.value = loaded.filter(item => item.timeframes.includes('1d'))
        if (!activeSymbolId.value) {
          const initial = symbols.value.find(item => item.id === selected)
            ?? symbols.value.find(item => item.market !== 'usdm' && (item.symbol === selected || item.name === selected))
            ?? symbols.value.find(item => item.id === DEFAULT_SYMBOL)
            ?? symbols.value[0]
          if (initial) {
            activeSymbolId.value = initial.id
            return
          }
        }
      }
      const current = symbols.value.find(item => item.id === activeSymbolId.value)
      if (!current) throw new Error(t('observation.unsupported'))
      const history = await readHistory(current, signal)
      if (requestId !== sequence) return
      const bars = normalizeObservationBars(history.bars)
      if (!bars.length) throw new Error(t('observation.empty'))
      const incomplete = history.incomplete || bars.length !== new Set(history.bars.map(row => row.timestamp)).size
      snapshot.value = { ...history, bars, incomplete, instrument: current }
    } catch (cause) {
      if (requestId === sequence) setError(cause, 'observation.loadFailed')
    } finally {
      if (requestId === sequence) loading.value = false
    }
  }

  function selectSymbol(id: string) {
    if (!disposed) activeSymbolId.value = id
  }
  watch(activeSymbolId, id => {
    try { getLocalStorage()?.setItem(STORAGE_KEY, id) } catch { /* Storage may be unavailable. */ }
    void load()
  })
  onBeforeUnmount(() => { disposed = true; sequence++; controller?.abort() })
  return { symbols, activeSymbolId, basis, data, stats, instrument, isIndex, stale, loading, error, selectSymbol, load, refreshSymbols }
}
