import { computed, reactive, ref, type Ref } from 'vue'
import type { LiveQuote } from './provider'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import { chartApi, type ChartSymbol } from './api'
import { ReplayAccount, type Side, type OrderKind } from './replayModel'
import { quantityForAmount } from './replayQuantity'
import { cw } from './locale'

/** Real-time paper positions are independent of the historical replay account. */
export function createWorkspacePaper(deps: {
  workspace: Ref<VelaWorkspace | undefined>; symbols: Ref<ChartSymbol[]>
  symbolId: Ref<string>; timeframe: Readonly<Ref<string>>
  subscribe: (id: string, timeframe: string, onQuote: (quote: LiveQuote) => void) => () => void
}) {
  const accounts = reactive(new Map<string, ReplayAccount>()), idle = reactive(new ReplayAccount())
  const symbol = computed(() => deps.symbols.value.find(info => info.id === deps.symbolId.value))
  const active = computed(() => accounts.has(deps.symbolId.value))
  const amount = ref(100), loading = ref(false), error = ref('')
  const subscriptions = new Map<string, () => void>()
  const observed = new Map<string, number>()
  const account = () => accounts.get(deps.symbolId.value) ?? idle
  const hasOrder = computed(() => !!account().order)
  let disposed = false
  function roundedPrice(price: number) {
    const tick = Number(symbol.value?.metadata?.mintick) || 0.00000001
    return Number((Math.round(price / tick) * tick).toPrecision(12))
  }
  async function place(side: Side, kind: OrderKind, price: number) {
    const info = symbol.value, cell = deps.workspace.value?.active, budget = amount.value
    if (disposed || loading.value || !info || !cell || hasOrder.value) return false
    if (!Number.isFinite(budget) || budget <= 0) { error.value = cw('replayInvalidOrder');return false }
    loading.value = true; error.value = ''
    try {
      const quote = (await chartApi.quotes([info.id]))[0]
      if (!quote?.price || quote.error || quote.id !== info.id) throw new Error(quote?.error || cw('alertQuoteUnavailable'))
      if (disposed || deps.symbolId.value !== info.id || deps.workspace.value?.active !== cell) return false
      const entryPrice = kind === 'market' ? quote.price : roundedPrice(price)
      const quantity = quantityForAmount(budget, entryPrice, Number(info.metadata?.mincontract))
      if (!(quantity > 0)) { error.value = cw('replayInvalidOrder'); return false }
      if (!accounts.has(info.id)) accounts.set(info.id, new ReplayAccount())
      const target = accounts.get(info.id)!
      const createdAt = Date.now()
      observed.set(info.id, createdAt)
      target.quote(quote.price, createdAt)
      if (!target.place(side, kind, entryPrice, quantity, createdAt)) return false
      if (!subscriptions.has(info.id)) subscriptions.set(info.id, deps.subscribe(info.id, info.timeframes.includes('1m') ? '1m' : '1d', update => {
        if (!disposed && Number.isFinite(update.observedAt) && update.observedAt >= (observed.get(info.id) ?? Infinity)) {
          observed.set(info.id, update.observedAt)
          target.quote(update.price, update.observedAt)
        }
      }))
      return true
    } catch (cause) { if (!disposed) error.value = cause instanceof Error ? cause.message : String(cause); return false }
    finally { loading.value = false }
  }
  function dispose() { disposed = true; for (const off of subscriptions.values()) off(); subscriptions.clear() }
  return { active, symbol, timeframe: deps.timeframe, amount, loading, error, hasOrder, roundedPrice, place, dispose,
    get account() { return account() }, get chart() { return deps.workspace.value?.active.chart } }
}
export type WorkspacePaper = ReturnType<typeof createWorkspacePaper>
