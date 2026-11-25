import type { PineRun, PineRunRequest, PineRecords, ChartBars } from './generatedContracts'
import { browserPineStore } from '@/modules/personal/browserStore'
import type { SavedPineRun } from '@/modules/personal/browserPineStore'
import { ApiRequestError } from '@/api/request'

type RunControl = {
  worker?: Worker; abort: AbortController; timer?: ReturnType<typeof setTimeout>; stop?: () => void
  release?: () => void; lease?: Promise<unknown>; released?: Promise<void>
  task?: Promise<void>; accepted: Promise<void>; accept: () => void
  closing?: boolean; cancellation?: Promise<unknown>
}
const active = new Map<string, RunControl>()
let cancellationChannel: BroadcastChannel | undefined
function cancellation() {
  if (cancellationChannel || typeof BroadcastChannel === 'undefined') return cancellationChannel
  cancellationChannel = new BroadcastChannel('opentrading:backtest-cancel')
  cancellationChannel.onmessage = ({ data }) => { void stop(data).catch(() => {}) }
  return cancellationChannel
}
async function release(id: string, control: RunControl) {
  return control.released ??= (async () => {
    clearTimeout(control.timer)
    control.worker?.terminate()
    control.release?.()
    try { await control.lease } catch { /* Admission already reported its error. */ }
    if (active.get(id) === control) active.delete(id)
  })()
}
async function stop(id: string) {
  const control = active.get(id)
  if (!control) return
  if (!control.cancellation) {
    control.closing = true
    clearTimeout(control.timer)
    control.abort.abort(); control.worker?.terminate(); control.stop?.()
    // The worker is stopped before publishing cancellation. Keep its owner lock
    // until the terminal write finishes, even when storage rejects that write.
    control.cancellation = patch(id, { status: 'cancelled' })
    void control.cancellation.catch(() => {})
  }
  await control.accepted
  await control.task
  await control.cancellation
}
const prefix = 'pine-run:'
const copy = <T>(value: T): T => structuredClone(value)

async function admission(id: string, control: RunControl) {
  if (!navigator.locks) return
  for (let slot = 0; slot < 2; slot++) {
    const acquired = await new Promise<boolean>((resolve, reject) => {
      control.lease = navigator.locks.request(`opentrading:pine-slot:${slot}`, { ifAvailable: true }, async lock => {
        if (!lock) { resolve(false); return }
        // This existing run-owner identity also lets other tabs discover and
        // cancel the exact worker without mistaking it for an interrupted run.
        await navigator.locks.request(prefix + id, async () => {
          const held = new Promise<void>(done => { control.release = done })
          resolve(true)
          await held
        })
      })
      void control.lease.catch(reject)
    })
    if (acquired) return
  }
  throw new Error('Wait for the current backtest to finish')
}
async function saved(id: string) {
  const value = await browserPineStore.get(id)
  if (!value) throw new ApiRequestError('Backtest does not exist in this browser', { status: 404 })
  return recover(value)
}
async function recover(value: SavedPineRun) {
  const id = value.run.id
  // A closed tab cannot keep computing. Other tabs retain their running jobs.
  if (['queued', 'loading', 'running'].includes(value.run.status) && !active.has(id) && Date.now() - value.run.created_at > 5000) {
    const owner = await navigator.locks?.query()
    if (!owner?.held?.some(lock => lock.name === prefix + id)) return browserPineStore.update(id, row =>
      ['queued', 'loading', 'running'].includes(row!.run.status) ? { ...row!, run: { ...row!.run, status: 'interrupted' } } : row!)
  }
  return value
}
async function patch(id: string, values: Partial<PineRun>, result?: Record<string, any>) {
  return browserPineStore.update(id, previous => {
    if (!previous) throw new Error('Backtest is missing')
    if (!['queued', 'loading', 'running'].includes(previous.run.status)) return previous
    return { ...previous, run: { ...previous.run, ...values } }
  }, result)
}
async function compute(id: string, request: PineRunRequest, control: RunControl) {
  try {
    const bars: ChartBars['bars'] = []
    let symbol: ChartBars['symbol'] | undefined, cursor = request.start
    while (cursor <= request.end) {
      if (!active.has(id) || control.closing) return
      const query = new URLSearchParams({ symbol: request.symbol, timeframe: request.timeframe, start: String(cursor), end: String(request.end), limit: '1000' })
      const response = await fetch('/api/v1/chart-workspace/bars?' + query, { signal: control.abort.signal })
      if (!response.ok) throw new Error(`Market history unavailable (${response.status})`)
      const data: ChartBars = await response.json()
      symbol = data.symbol
      if (symbol.close_only || !['spot', 'usdm'].includes(symbol.market)) throw new Error('Strategy testing requires full OHLC data')
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
      await patch(id, { progress: { phase: 'loading', mode: 'indeterminate', completed: bars.length, total: null, unit: 'candles' } })
    }
    if (!active.has(id) || control.closing) return
    if (!symbol || bars.length < 2) throw new Error('At least two closed candles are required')
    const nextBoundary = (time: number) => {
      if (request.timeframe === '1M') { const date = new Date(time); date.setUTCMonth(date.getUTCMonth() + 1, 1); date.setUTCHours(0, 0, 0, 0); return +date }
      const match = /^(\d+)([mhdw])$/.exec(request.timeframe)
      if (!match) throw new Error('Unsupported timeframe')
      return time + Number(match[1]) * ({ m: 60000, h: 3600000, d: 86400000, w: 604800000 }[match[2]!]!)
    }
    if (bars[0]!.time > nextBoundary(request.start) || nextBoundary(bars[bars.length - 1]!.closeTime) <= request.end) throw new Error('The requested history is incomplete')
    await patch(id, { status: 'running', progress: { phase: 'computing', mode: 'indeterminate', completed: null, total: null, unit: null } })
    const worker = control.worker = new Worker(new URL('./backtest.worker.ts', import.meta.url), { type: 'module' })
    await new Promise<void>((resolve, reject) => {
      control.stop = resolve
      worker.onerror = () => reject(new Error('Backtest worker failed'))
      worker.onmessage = async ({ data }) => {
        try {
          if (!active.has(id) || control.closing) return resolve()
          if (data.type === 'progress' && data.value.runId === id) await patch(id, { progress: data.value.progress })
          else if (data.type === 'completed') {
            await patch(id, { status: 'completed', progress: null, summary: data.result.summary, provenance: { ...data.result.provenance, recording: 'report' } }, data.result)
            resolve()
          } else if (data.type === 'error') reject(new Error(data.message))
        } catch (error) { reject(error) }
      }
      worker.postMessage({ runId: id, source: request.script_source, request, symbol, bars, api: location.origin + '/api/v1/chart-workspace' })
    })
  } catch (error) {
    if (active.has(id) && !control.closing) await patch(id, { status: 'failed', error: error instanceof Error ? error.message : String(error) })
  } finally {
    await control.cancellation?.catch(() => {})
    await release(id, control)
  }
}
async function run(request: PineRunRequest): Promise<PineRun> {
  if (active.size >= 2) throw new Error('Wait for the current backtest to finish')
  if (!request.script_source || !Number.isFinite(request.start) || !Number.isFinite(request.end) || request.start >= request.end) throw new Error('Invalid backtest request')
  const id = crypto.randomUUID(), value: PineRun = { id, status: 'loading', progress: { phase: 'loading', mode: 'indeterminate', completed: null, total: null, unit: null }, created_at: Date.now(), request: copy(request), recording: 'report', summary: {}, provenance: {} }
  let accept = () => {}
  const accepted = new Promise<void>(resolve => { accept = resolve })
  const control: RunControl = { abort: new AbortController(), accepted, accept }
  // Reserve synchronously before the first await, including pending IDB writes.
  active.set(id, control)
  try {
    // Another tab can see the committed row before this submission resumes.
    // Register its cancellation receiver before crossing any async boundary.
    cancellation()
    await admission(id, control)
    await browserPineStore.update(id, () => ({ run: value }))
    if (control.closing) {
      await control.cancellation
      await release(id, control)
      return copy((await saved(id)).run)
    }
    control.timer = setTimeout(() => { void browserPineRuns.cancel(id).catch(() => {}) }, 300_000)
    control.task = compute(id, request, control)
    void control.task.catch(() => {}) // getRun exposes the persisted terminal state.
    return copy(value)
  } catch (error) {
    await release(id, control)
    throw error
  } finally { control.accept() }
}
export const browserPineRuns = {
  run,
  runs: async (): Promise<PineRun[]> => {
    const entries = await browserPineStore.list()
    return Promise.all(entries.map(async row => (await recover(row)).run)).then(rows => rows.sort((a, b) => b.created_at - a.created_at))
  },
  getRun: async (id: string): Promise<PineRun> => copy((await saved(id)).run),
  cancel: async (id: string): Promise<PineRun> => {
    if (active.has(id)) await stop(id)
    else {
      cancellation()?.postMessage(id)
      // The owner publishes its terminal state before releasing this lock.
      // A missing/crashed owner has already released it automatically.
      if (navigator.locks) await navigator.locks.request(prefix + id, { signal: AbortSignal.timeout(10_000) }, () => {})
    }
    await patch(id, { status: 'cancelled' })
    return copy((await saved(id)).run)
  },
  rerun: async (id: string) => run((await saved(id)).run.request),
  records: async (id: string, kind: string, offset = 0, limit = 200, sampled = false): Promise<PineRecords> => {
    await saved(id)
    return browserPineStore.records(id, kind, offset, limit, sampled)
  },
}
