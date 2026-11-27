import type { ChartBars } from './generatedContracts'

type Query = Record<string, string | number>
type Entry = {
  query: Query; latest: boolean; at: number; expires: number; result?: ChartBars
  pending?: Promise<ChartBars>; abort: AbortController; users: number
}

// Share transport work across cells and replay consumers. Closed history is
// reusable; a live tail expires quickly and never crosses a minute boundary.
export function createBarRequests(fetchBars: (query: Query, signal: AbortSignal) => Promise<ChartBars>,
  options: { maxEntries?: number; maxBars?: number; historical?: boolean } = {}) {
  const entries = new Map<string, Entry>()
  const maxEntries = options.maxEntries ?? 64, maxBars = options.maxBars ?? 32000
  const isLatest = (query: Query) => !options.historical &&
    (query.end === undefined || Number(query.end) >= Date.now() - 2000)
  const keyOf = (query: Query, latest: boolean) => JSON.stringify(Object.entries({ ...query,
    ...(latest ? { end: 'latest:' + Math.floor(Number(query.end ?? Date.now()) / 60000) } : {}),
  }).sort(([left], [right]) => left.localeCompare(right)))
  const touch = (key: string, entry: Entry) => { entries.delete(key); entries.set(key, entry) }
  function prune() {
    let bars = [...entries.values()].reduce((sum, entry) => sum + (entry.result?.bars.length ?? 0), 0)
    for (const [key, entry] of entries) {
      if (entries.size <= maxEntries && bars <= maxBars) break
      if (entry.pending) continue
      bars -= entry.result?.bars.length ?? 0
      entries.delete(key)
    }
  }
  function load(query: Query, signal?: AbortSignal): Promise<ChartBars> {
    if (signal?.aborted) return Promise.reject(signal.reason ?? new DOMException('Aborted', 'AbortError'))
    const latest = isLatest(query), key = keyOf(query, latest)
    let entry = entries.get(key)
    if (entry?.result && entry.expires > Date.now()) {
      touch(key, entry)
      return Promise.resolve(entry.result)
    }
    if (!entry?.pending) {
      entry = { query: { ...query }, latest, at: Date.now(), expires: 0, abort: new AbortController(), users: 0 }
      const current = entry
      entries.set(key, current)
      current.pending = fetchBars(query, current.abort.signal).then(result => {
        if (!current.abort.signal.aborted) {
          current.result = result
          current.at = Date.now()
          const changing = latest || Number(query.end ?? current.at) >= current.at || !result.bars.length ||
            result.bars.some(bar => !bar.closed || bar.closeTime > current.at)
          current.expires = current.at + (changing ? 2000 : 30 * 60_000)
        }
        return result
      }).finally(() => {
        current.pending = undefined
        if (entries.get(key) === current) {
          if (!current.result) entries.delete(key)
          prune()
        }
      })
    }
    const current = entry
    touch(key, current)
    current.users++
    return new Promise<ChartBars>((resolve, reject) => {
      let done = false
      const finish = () => {
        if (done) return false
        done = true; signal?.removeEventListener('abort', cancel); current.users--
        return true
      }
      const cancel = () => {
        if (!finish()) return
        reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'))
        if (current.users === 0 && current.pending) {
          if (entries.get(key) === current) entries.delete(key)
          current.abort.abort()
        }
      }
      signal?.addEventListener('abort', cancel, { once: true })
      current.pending!.then(result => { if (finish()) resolve(result) }, error => { if (finish()) reject(error) })
    })
  }
  function peek(query: Query): ChartBars | undefined {
    // A previous live preview can paint immediately while its refresh runs.
    // Historical previews must match the exact cutoff to preserve replay time.
    const exact = entries.get(keyOf(query, isLatest(query)))
    if (exact?.result) return exact.result
    if (!isLatest(query)) return
    return [...entries.values()].reverse().find(entry => entry.latest && entry.result &&
      entry.query.symbol === query.symbol && entry.query.timeframe === query.timeframe &&
      entry.query.start === query.start && Number(entry.query.limit) >= Number(query.limit))?.result
  }
  return { load, peek }
}
