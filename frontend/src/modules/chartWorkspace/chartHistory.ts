import type { Vela, VisibleRange } from '@luxalgo/vela'

const HISTORY_BATCH = 1000

// Vela extends a requested depth without moving the viewport, but does not
// request more history when the user pans past that depth.
export function installChartHistory(chart: Vela, deps: {
  enabled: () => boolean
  onLoading: (loaded: number) => void
  onDepth: (depth: number) => void
  onError: (error: unknown) => void
}) {
  let disposed = false, queued = false, generation = 0
  let oldest: number | undefined, loaded = 0
  let reason: 'depth' | 'genesis' | 'aborted' | undefined
  let completed: Promise<void> | undefined
  let viewport: VisibleRange | null = null
  let retry: ReturnType<typeof setTimeout> | undefined, failures = 0
  let marketKey = `${chart.market.symbol}:${chart.market.timeframe}`

  function retryLater() {
    clearTimeout(retry)
    if (failures >= 3 || disposed) return
    retry = setTimeout(() => { retry = undefined; refresh() }, 1500 * 2 ** failures++)
  }

  function refresh(range?: VisibleRange) {
    if (range) {
      if (viewport?.from === range.from && viewport.to === range.to) return
      viewport = range
    }
    if (disposed || queued) return
    queued = true
    queueMicrotask(() => {
      queued = false
      const market = chart.market
      if (disposed || !deps.enabled() || market.offline || !market.symbol?.startsWith('opentrading:') ||
          !reason || reason === 'genesis' || completed !== chart.historyComplete()) return
      const range = viewport ?? chart.getVisibleRange()
      if (oldest !== undefined && (!range || !Number.isFinite(range.from) || !Number.isFinite(range.to) || range.to <= range.from ||
          range.from > oldest + (range.to - range.from) / 2)) return
      if (oldest === undefined && reason !== 'aborted') return
      clearTimeout(retry); retry = undefined
      const depth = Math.max(loaded, market.bars ?? HISTORY_BATCH) + (reason === 'aborted' ? 0 : HISTORY_BATCH)
      const current = ++generation
      completed = undefined
      deps.onLoading(loaded)
      void chart.setMarket({ bars: depth }).then(() => {
        if (!disposed && current === generation) deps.onDepth(depth)
      }).catch(error => {
        if (disposed || current !== generation) return
        completed = chart.historyComplete()
        reason = 'aborted'
        deps.onError(error)
        retryLater()
      })
    })
  }

  const off = [
    chart.on('viewport:changed', refresh),
    chart.on('load:start', () => {
      const key = `${chart.market.symbol}:${chart.market.timeframe}`
      if (key !== marketKey) { marketKey = key; failures = 0 }
      clearTimeout(retry); retry = undefined
      generation++
      oldest = undefined
      completed = undefined
      reason = undefined
      viewport = null
    }),
    chart.on('history:complete', event => {
      oldest = event.barsLoaded > 0 ? event.oldestTime : undefined
      loaded = event.barsLoaded
      reason = event.reason
      completed = chart.historyComplete()
      if (reason === 'aborted') retryLater()
      else { failures = 0; clearTimeout(retry); retry = undefined }
      if (reason === 'depth') refresh()
    }),
  ]
  return {
    refresh,
    dispose() { disposed = true; generation++; clearTimeout(retry); off.forEach(unsubscribe => unsubscribe()) },
  }
}
