import type { PineRun, PineRunRequest, PineRecords, ChartBars } from './generatedContracts'
import { browserRecord, browserRecords, updateBrowserRecord } from '@/modules/personal/browserStore'
import { ApiRequestError } from '@/api/request'

type RunControl = { worker?: Worker; abort: AbortController; timer: ReturnType<typeof setTimeout>; stop?: () => void }
const active = new Map<string, RunControl>()
let cancellationChannel: BroadcastChannel | undefined
function cancellation() {
  if (cancellationChannel || typeof BroadcastChannel === 'undefined') return cancellationChannel
  cancellationChannel = new BroadcastChannel('opentrading:backtest-cancel')
  cancellationChannel.onmessage = ({ data }) => stop(data)
  return cancellationChannel
}
function stop(id: string) {
  const control = active.get(id)
  if (control) { clearTimeout(control.timer); control.abort.abort(); control.worker?.terminate(); control.stop?.(); active.delete(id) }
}
const prefix = 'pine-run:'
const copy = <T>(value: T): T => structuredClone(value)
type SavedRun = { run: PineRun; result?: Record<string, any> }
async function saved(id: string) {
  const value = await browserRecord<SavedRun>(prefix + id)
  if (!value) throw new ApiRequestError('Backtest does not exist in this browser', { status: 404 })
  // A closed tab cannot keep computing. Other tabs retain their running jobs.
  if (['queued', 'loading', 'running'].includes(value.run.status) && !active.has(id) && Date.now() - value.run.created_at > 5000) {
    const owner = await navigator.locks?.query()
    if (!owner?.held?.some(lock => lock.name === prefix + id)) return updateBrowserRecord<SavedRun>(prefix + id, row => ({ ...row!, run: { ...row!.run, status: 'interrupted' } }))
  }
  return value
}
async function patch(id: string, values: Partial<PineRun>, result?: Record<string, any>) {
  return updateBrowserRecord<SavedRun>(prefix + id, previous => {
    if (!previous) throw new Error('Backtest is missing')
    if (!['queued', 'loading', 'running'].includes(previous.run.status)) return previous
    return { run: { ...previous.run, ...values }, ...(result ? { result } : previous.result ? { result: previous.result } : {}) }
  })
}
async function compute(id: string, request: PineRunRequest, control: RunControl) {
  try {
    const bars: ChartBars['bars'] = []
    let symbol: ChartBars['symbol'] | undefined, cursor = request.start
    while (cursor <= request.end) {
      if (!active.has(id)) return
      const query = new URLSearchParams({ symbol: request.symbol, timeframe: request.timeframe, start: String(cursor), end: String(request.end), limit: '1000' })
      const response = await fetch('/api/v1/chart-workspace/bars?' + query, { signal: control.abort.signal })
      if (!response.ok) throw new Error(`Market history unavailable (${response.status})`)
      const data: ChartBars = await response.json()
      symbol = data.symbol
      if (symbol.close_only || symbol.market === 'index') throw new Error('Strategy testing requires full OHLC data')
      const batch = data.bars.filter(bar => bar.closed && bar.closeTime <= request.end)
      if (!batch.length) break
      if (batch[0]!.time < cursor || batch[batch.length - 1]!.closeTime <= cursor) throw new Error('Market history pagination did not advance')
      for (let index = 0; index < batch.length; index++) {
        const bar = batch[index]!, previous = index ? batch[index - 1] : bars[bars.length - 1]
        if (previous && previous.closeTime !== bar.time) throw new Error('Market history contains a gap')
        if (![bar.open, bar.high, bar.low, bar.close, bar.volume ?? 0].every(Number.isFinite) || bar.low > Math.min(bar.open, bar.close) || Math.max(bar.open, bar.close) > bar.high || (bar.volume ?? 0) < 0) throw new Error('Invalid OHLCV data')
      }
      bars.push(...batch)
      cursor = batch[batch.length - 1]!.closeTime
      await patch(id, { progress: Math.min(99, (cursor - request.start) / (request.end - request.start) * 100) })
    }
    if (!active.has(id)) return
    if (!symbol || bars.length < 2) throw new Error('At least two closed candles are required')
    const nextBoundary = (time: number) => {
      if (request.timeframe === '1M') { const date = new Date(time); date.setUTCMonth(date.getUTCMonth() + 1, 1); date.setUTCHours(0, 0, 0, 0); return +date }
      const match = /^(\d+)([mhdw])$/.exec(request.timeframe)
      if (!match) throw new Error('Unsupported timeframe')
      return time + Number(match[1]) * ({ m: 60000, h: 3600000, d: 86400000, w: 604800000 }[match[2]!]!)
    }
    if (bars[0]!.time > nextBoundary(request.start) || nextBoundary(bars[bars.length - 1]!.closeTime) <= request.end) throw new Error('The requested history is incomplete')
    await patch(id, { status: 'running', progress: 0 })
    const worker = control.worker = new Worker(new URL('./backtest.worker.ts', import.meta.url), { type: 'module' })
    await new Promise<void>((resolve, reject) => {
      control.stop = resolve
      worker.onerror = () => reject(new Error('Backtest worker failed'))
      worker.onmessage = async ({ data }) => {
        try {
          if (!active.has(id)) return resolve()
          if (data.type === 'progress') await patch(id, { progress: data.value.progress })
          else if (data.type === 'completed') {
            await patch(id, { status: 'completed', progress: 100, summary: data.result.summary, provenance: { ...data.result.provenance, recording: 'report' } }, data.result)
            resolve()
          } else if (data.type === 'error') reject(new Error(data.message))
        } catch (error) { reject(error) }
      }
      worker.postMessage({ source: request.script_source, request, symbol, bars, api: location.origin + '/api/v1/chart-workspace' })
    })
  } catch (error) {
    if (active.has(id)) await patch(id, { status: 'failed', error: error instanceof Error ? error.message : String(error) })
  } finally { clearTimeout(control.timer); control.worker?.terminate(); active.delete(id) }
}
async function run(request: PineRunRequest): Promise<PineRun> {
  if (active.size >= 2) throw new Error('Wait for the current backtest to finish')
  if (!request.script_source || !Number.isFinite(request.start) || !Number.isFinite(request.end) || request.start >= request.end) throw new Error('Invalid backtest request')
  const id = crypto.randomUUID(), value: PineRun = { id, status: 'loading', progress: 0, created_at: Date.now(), request: copy(request), recording: 'report', summary: {}, provenance: {} }
  await updateBrowserRecord<SavedRun>(prefix + id, () => ({ run: value }))
  const control: RunControl = { abort: new AbortController(), timer: setTimeout(() => { void browserPineRuns.cancel(id) }, 300_000) }
  active.set(id, control)
  cancellation()
  const task = () => compute(id, request, control)
  void (navigator.locks ? navigator.locks.request(prefix + id, task) : task())
  return copy(value)
}
export const browserPineRuns = {
  run,
  runs: async (): Promise<PineRun[]> => {
    const entries = await browserRecords()
    return Promise.all(Object.keys(entries).filter(key => key.startsWith(prefix)).map(async key => (await saved(key.slice(prefix.length))).run)).then(rows => rows.sort((a, b) => b.created_at - a.created_at))
  },
  getRun: async (id: string): Promise<PineRun> => copy((await saved(id)).run),
  cancel: async (id: string): Promise<PineRun> => {
    // Locks coordinate cancellation with a worker owned by a different tab.
    await patch(id, { status: 'cancelled' })
    stop(id)
    cancellation()?.postMessage(id)
    return copy((await saved(id)).run)
  },
  rerun: async (id: string) => run((await saved(id)).run.request),
  records: async (id: string, kind: string, offset = 0, limit = 200, sampled = false): Promise<PineRecords> => {
    const value = await saved(id), rows = value.result?.[kind] ?? []
    const items = sampled && rows.length > limit ? Array.from({ length: limit }, (_, index) => rows[Math.round(index * (rows.length - 1) / (limit - 1))]) : rows.slice(offset, offset + limit)
    return { items: copy(items), total: rows.length, offset }
  },
}
