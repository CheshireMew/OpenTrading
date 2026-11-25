import { computed, reactive, ref, type Ref } from 'vue'
import type { DataProvider, BarRange, OHLCV, Vela } from '@luxalgo/vela'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import { chartApi, type ChartBar, type ChartSymbol } from './api'
import { fromVela, velaSymbol, timeframes } from './provider'
import { ReplayAccount, ReplayPacer, aggregateMinute, periodStart, periodEnd, MINUTE, type Side, type OrderKind } from './replayModel'
import { quantityForAmount } from './replayQuantity'
import { cw } from './locale'
import { catalogSymbolIcon } from './symbolIcons'

class ReplayHistoryUnavailable extends Error {}

export type ReplaySourceBar = { sessionId: string; symbolId: string; bar: ChartBar }

export function createWorkspaceReplay(deps: { workspace: Ref<VelaWorkspace | undefined>; symbols: Ref<ChartSymbol[]>; settled?:()=>Promise<void> }) {
  const open = ref(false), active = ref(false), loading = ref(false), playing = ref(false), picking = ref(false)
  const processing = ref(false)
  const error = ref(''), now = ref(0), speed = ref(1), amount = ref(100), ended = ref(false)
  const account = reactive(new ReplayAccount()), clock = new ReplayPacer()
  const listeners = new Set<(bar: OHLCV) => void>(), pulses = new Set<(now: number) => void>()
  const sourceListeners = new Set<(event: ReplaySourceBar) => void>(), sessionId = ref('')
  const sourceStep = ref('1m'), symbol = ref<ChartSymbol>(), timeframe = ref('5m'), cellId = ref('')
  let target: Vela | undefined, history: ChartBar[] = [], buffer: ChartBar[] = [], offset = 0
  let nextSource = 0, ceiling = 0, generation = 0, abort = new AbortController(), disposed = false
  let fetchAhead: Promise<void> | undefined, busy = false, anchor = 0, providerName = '', failedStart: number | 'random' | undefined
  let failedStartAutoplay = false
  let viewEpoch = 0, viewAbort: AbortController | undefined, switchingView = false, failedTimeframe: string | undefined
  let advancing: Promise<void> = Promise.resolve()
  let playbackTimer: ReturnType<typeof setTimeout> | undefined
  const actualTime = () => active.value ? now.value : undefined
  const roundedPrice = (price: number) => {
    const tick = Number(symbol.value?.metadata?.mintick) || 0.00000001
    return Number((Math.round(price / tick) * tick).toPrecision(12))
  }
  const hasOrder = computed(() => !!(account.draft || account.pending || account.position))
  function place(side: Side, kind: OrderKind, price = account.price) {
    if (!active.value || loading.value) return false
    const entryPrice = kind === 'market' ? account.price : roundedPrice(price)
    const quantity = quantityForAmount(amount.value, entryPrice, Number(symbol.value?.metadata?.mincontract))
    return account.place(side, kind, entryPrice, quantity, now.value)
  }
  function clearPlayback() { clearTimeout(playbackTimer);playbackTimer=undefined }
  function schedule() {
    clearPlayback()
    if (!playing.value || busy || switchingView || loading.value || !active.value || ended.value) return
    playbackTimer=setTimeout(()=>{playbackTimer=undefined;void advanceOne()},clock.delay(performance.now()))
  }
  function pause() { clearPlayback();clock.pause(performance.now());playing.value=false }
  function report(cause: unknown) { pause();error.value = cause instanceof Error ? cause.message : String(cause) }
  async function fetchChunk(cursor: number, epoch: number, signal: AbortSignal, info: ChartSymbol, tf: string, cutoff = ceiling) {
    const end = Math.min(cutoff, tf === '1m' ? cursor + 1000 * MINUTE : cursor + 1000 * 86_400_000)
    if (cursor >= end) return []
    const result = await chartApi.replayBars({ symbol: info.id, timeframe: tf, start: cursor, end, limit: 1000 }, signal)
    if (epoch !== generation || disposed) return []
    const bars = result.bars
    for (let i = 0; i < bars.length; i++) {
      const b = bars[i]!, prior = bars[i - 1]
      if (b.time < cursor || b.closeTime > end || !b.closed ||
          ![b.open, b.high, b.low, b.close, b.volume ?? 0].every(Number.isFinite) ||
          b.open <= 0 || b.low <= 0 || b.low > Math.min(b.open, b.close) || b.high < Math.max(b.open, b.close) || (b.volume ?? 0) < 0 ||
          (prior && (b.time <= prior.time || (tf === '1m' && b.time !== prior.closeTime)))) throw new ReplayHistoryUnavailable(cw('replayGap'))
    }
    if (tf === '1m' && bars.length && bars[0]!.time !== cursor) throw new ReplayHistoryUnavailable(cw('replayGap'))
    return bars
  }
  async function prefetch() {
    if (fetchAhead) return fetchAhead
    const epoch = generation, cursor = nextSource, info = symbol.value!, tf = sourceStep.value, signal = abort.signal
    const operation = (async () => {
      const rows = await fetchChunk(cursor, epoch, signal, info, tf)
      if (epoch !== generation || disposed) return
      buffer = [...buffer.slice(offset), ...rows]; offset = 0
      if (rows.length) nextSource = rows[rows.length - 1]!.closeTime
      else if (cursor < ceiling) throw new Error(cw('replayGap'))
    })()
    fetchAhead = operation
    try { await operation } finally { if (fetchAhead === operation) fetchAhead = undefined }
  }
  const provider: DataProvider = {
    resolveSymbolIcon: descriptor => catalogSymbolIcon(deps.symbols.value, descriptor.ticker),
    listSymbols: async () => deps.symbols.value.map(s => ({ ticker: s.id, description: s.name })),
    getSymbolInfo: async ticker => {
      const info = deps.symbols.value.find(s => s.id === fromVela(ticker)) ?? symbol.value!
      return { ...info.metadata, ticker: info.symbol, tickerid: velaSymbol(info.id), currency: info.currency,
        timezone: info.timezone, session: info.session }
    },
    getBars: async (_ticker: string, _tf: string, range: BarRange) => {
      const epoch = generation, view = viewEpoch
      const tf = timeframes[_tf] ?? _tf
      if (fromVela(_ticker) !== symbol.value!.id || tf !== timeframe.value) {
        const query: Record<string, string | number> = { symbol: fromVela(_ticker), timeframe: tf,
          end: Math.min(range.to ?? now.value, now.value), limit: Math.min(range.limit ?? 1000, 1000) }
        if (range.from !== undefined) query.start = range.from
        const result = await chartApi.replayBars(query, abort.signal)
        return epoch === generation && view === viewEpoch ? result.bars.filter(b => b.closeTime <= now.value) : []
      }
      if (range.to !== undefined && history.length && range.to <= history[0]!.time) {
        const result = await chartApi.replayBars({ symbol: symbol.value!.id, timeframe: timeframe.value,
          end: Math.min(range.to + 1, now.value), limit: Math.min(range.limit ?? 1000, 1000) }, abort.signal)
        if (epoch !== generation || view !== viewEpoch) return []
        history = [...new Map([...result.bars, ...history].map(b => [b.time, b])).values()].sort((a, b) => a.time - b.time)
      }
      const rows = history.filter(b => (range.from === undefined || b.time >= range.from) && (range.to === undefined || b.time <= range.to))
      return range.limit ? rows.slice(-range.limit) : rows
    },
    subscribe: (_ticker, _tf, cb) => { listeners.add(cb); return () => { listeners.delete(cb) } },
  }
  async function randomDate(info: ChartSymbol, tf: string, signal: AbortSignal, excluded: Set<number>) {
    const upper = periodStart(Date.now(), info.timeframes.includes('1m') ? '1m' : '1d')
    // Monthly history covers the instrument's lifetime without downloading minute history.
    const monthly = info.timeframes.includes('1M')
    const overview = await chartApi.replayBars({ symbol: info.id, timeframe: monthly ? '1M' : '1d', end: upper,
      limit: 1000, ...(monthly ? { start: 0 } : {}) }, signal)
    const known = overview.bars.filter(bar => bar.closed && bar.closeTime < upper)
    const spans = monthly ? known.map(bar => ({ from: bar.time, to: bar.closeTime })) : []
    if (monthly && known.length && known[known.length-1]!.closeTime < upper)
      spans.push({ from: known[known.length-1]!.closeTime, to: upper })
    for(let attempt=0;attempt<6;attempt++){
      if(signal.aborted)throw new DOMException('Aborted','AbortError')
      const span=spans[Math.floor(Math.random()*spans.length)]
      const result=span?await chartApi.replayBars({symbol:info.id,timeframe:'1d',start:span.from,end:span.to,limit:1000},signal):
        monthly?await chartApi.replayBars({symbol:info.id,timeframe:'1d',end:upper,limit:1000},signal):overview
      const first=result.bars[0]
      if(!first)continue
      // Start after a known trading day, leaving both prior context and unrevealed history.
      const dates=result.bars.filter(bar=>bar.closed&&bar.closeTime<upper&&periodStart(bar.closeTime,tf)>=periodEnd(first.time,tf)&&!excluded.has(periodStart(bar.closeTime,tf)))
      if(dates.length)return dates[Math.floor(Math.random()*dates.length)]!.closeTime
    }
    throw new ReplayHistoryUnavailable(cw('replayRandomUnavailable'))
  }
  async function start(date: number | 'random', autoplay = date === 'random') {
    const cell = deps.workspace.value?.active
    if (!cell || loading.value || (date !== 'random' && !Number.isFinite(date))) return
    pause(); error.value = ''; loading.value = true
    viewEpoch++;viewAbort?.abort();switchingView=false;failedTimeframe=undefined
    failedStart = date
    failedStartAutoplay = autoplay
    const epoch = ++generation
    abort.abort(); abort = new AbortController(); fetchAhead = undefined
    const info = deps.symbols.value.find(s => s.id === fromVela(cell.symbol))!
    const tf = timeframes[cell.timeframe] ?? cell.timeframe, base = info.timeframes.includes('1m') ? '1m' : '1d'
    ceiling = periodStart(Date.now(), base)
    try {
      const signal = abort.signal, excluded = new Set<number>()
      const prepare = async (chosen: number) => {
        const startAt = periodStart(chosen, tf)
        if (startAt >= ceiling) throw new Error(cw('replayPastDate'))
        failedStart = startAt
        // The bounded history endpoint fills cache gaps from the venue before returning.
        const [past, future] = await Promise.all([
          chartApi.replayBars({ symbol: info.id, timeframe: tf, end: startAt, limit: Math.min(cell.chart.market.bars ?? 1000, 1000) }, signal),
          fetchChunk(startAt, epoch, signal, info, base),
        ])
        const history = past.bars.filter(bar => bar.closed && bar.closeTime <= startAt)
        if (!future.length || !history.length) throw new ReplayHistoryUnavailable(cw('replayNoData'))
        return { startAt, past: history, future }
      }
      let prepared: Awaited<ReturnType<typeof prepare>> | undefined
      if (date !== 'random') prepared = await prepare(date)
      else {
        for (let attempt = 0; attempt < 6 && !prepared; attempt++) {
          if (signal.aborted || epoch !== generation || disposed) return
          let chosen: number
          try { chosen = await randomDate(info, tf, signal, excluded) }
          catch (cause) { if (cause instanceof ReplayHistoryUnavailable) break; throw cause }
          excluded.add(periodStart(chosen, tf))
          try { prepared = await prepare(chosen) }
          catch (cause) { if (!(cause instanceof ReplayHistoryUnavailable)) throw cause }
        }
        if (!prepared && !signal.aborted && epoch === generation && !disposed) {
          // Coarse history can predate minute coverage; verify a recent source chunk as fallback.
          const recent = await chartApi.replayBars({ symbol: info.id, timeframe: base, end: ceiling, limit: 1000 }, signal)
          const dates = [...new Set(recent.bars.filter(bar => bar.closed && bar.closeTime <= ceiling)
            .map(bar => periodStart(bar.time, tf)))].filter(date => !excluded.has(date))
          for (let attempt = 0; attempt < 6 && dates.length && !prepared; attempt++) {
            if (signal.aborted || epoch !== generation || disposed) return
            const chosen = dates.splice(Math.floor(Math.random() * dates.length), 1)[0]!
            try { prepared = await prepare(chosen) }
            catch (cause) { if (!(cause instanceof ReplayHistoryUnavailable)) throw cause }
          }
        }
        if (!prepared) { failedStart = 'random'; throw new ReplayHistoryUnavailable(cw('replayRandomUnavailable')) }
      }
      if (epoch !== generation || disposed) return
      const { startAt, past, future } = prepared
      if (target && target !== cell.chart) await leaveChart()
      target = cell.chart; symbol.value = info; timeframe.value = tf; sourceStep.value = base; cellId.value = cell.id
      history = past; buffer = future; offset = 0; nextSource = future[future.length - 1]!.closeTime
      account.reset(history[history.length - 1]!.close)
      now.value = startAt; clock.reset(performance.now()); active.value = open.value = true; ended.value = false; picking.value = false
      const oldProvider = providerName
      // Each start owns a cache identity, so rewinding cannot reuse revealed future bars.
      providerName = 'replay' + Date.now() + epoch
      sessionId.value = providerName
      target.data.registerProvider(providerName, provider)
      await target.data.ready()
      target.renderer.setWallClock({ onTick: cb => { pulses.add(cb); cb(now.value); return () => { pulses.delete(cb) } } })
      await target.setMarket({ symbol: providerName + ':' + info.id, timeframe: cell.timeframe, data: undefined })
      if (oldProvider) target.data.unregisterProvider?.(oldProvider)
      if (epoch !== generation) return
      failedStart = undefined
    } catch (cause) { if (epoch === generation && !disposed) report(cause) }
    finally {
      if (epoch === generation) {
        loading.value = false
        if(autoplay&&active.value&&!error.value)play()
      }
    }
  }
  const startRandom=()=>start('random')
  async function viewHistory(tf: string, at: number, epoch: number, signal: AbortSignal) {
    const boundary = periodStart(at, tf), info = symbol.value!, base = sourceStep.value
    const past = await chartApi.replayBars({ symbol: info.id, timeframe: tf, end: boundary,
      limit: Math.min(target?.market.bars ?? 1000, 1000) }, signal)
    const rows = past.bars.filter(bar => bar.closed && bar.closeTime <= boundary)
    let forming: ChartBar | undefined, cursor = boundary
    const cutoff = periodStart(at, base)
    while (cursor < cutoff && epoch === generation && !signal.aborted) {
      const batch = await fetchChunk(cursor, epoch, signal, info, base, cutoff)
      if (!batch.length) {
        if (base === '1m') throw new Error(cw('replayGap'))
        break
      }
      for (const bar of batch) forming = aggregateMinute(forming, bar, tf)
      cursor = batch[batch.length - 1]!.closeTime
    }
    if (forming) rows.push(forming)
    if (!rows.length) throw new Error(cw('replayNoData'))
    return rows
  }
  /** Rebuild the chart view without seeking the replay or touching its trading account. */
  async function setTimeframe(value: string) {
    const chart = target, tf = timeframes[value] ?? value
    if (!active.value || !chart || (!switchingView && tf === timeframe.value)) return
    const epoch = generation, view = ++viewEpoch
    viewAbort?.abort();const controller = viewAbort = new AbortController()
    const current = () => epoch === generation && view === viewEpoch && !disposed && target === chart
    switchingView = true;loading.value = true;error.value = '';failedTimeframe = value
    // Preserve the user's play/pause choice and the remaining delay until the next candle.
    clearPlayback();clock.pause(performance.now())
    await advancing
    if (!current()) return
    loading.value = true
    const previous = { timeframe: timeframe.value, history }
    let committed = false
    try {
      const rows = await viewHistory(tf, now.value, epoch, controller.signal)
      if (!current()) return
      history = rows;timeframe.value = tf;committed = true
      await chart.setMarket({ timeframe: value })
      await deps.settled?.()
      if (current()) failedTimeframe = undefined
    } catch (cause) {
      if (current()) {
        if (committed) {
          history = previous.history;timeframe.value = previous.timeframe
          const oldValue = Object.keys(timeframes).find(key => timeframes[key] === previous.timeframe) ?? previous.timeframe
          await chart.setMarket({ timeframe: oldValue })
        }
        if (current()) report(cause)
      }
    } finally {
      if (current()) {
        switchingView = false;loading.value = false
        if (playing.value) {clock.play(performance.now());schedule()}
      }
    }
  }
  async function leaveChart() {
    const chart = target; target = undefined
    if (chart) {
      chart.renderer.setWallClock(null)
      await chart.setMarket({ symbol: velaSymbol(symbol.value!.id), data: undefined })
      if (providerName) chart.data.unregisterProvider?.(providerName)
    }
    listeners.clear(); pulses.clear(); providerName = ''
  }
  async function exit() {
    viewEpoch++;viewAbort?.abort();switchingView=false;failedTimeframe=undefined
    pause(); generation++; abort.abort(); fetchAhead = undefined; loading.value = false
    active.value = picking.value = open.value = false
    try { await leaveChart() } catch (cause) { if (!disposed) error.value = String(cause) }
  }
  function emitBar(bar: ChartBar) {
    const previous = history[history.length - 1]
    const next = aggregateMinute(previous, bar, timeframe.value)
    if (previous?.time === next.time) history[history.length - 1] = next
    else history.push(next)
    for (const cb of listeners) cb(next)
  }
  async function advanceOne() {
    if (busy || switchingView || !active.value || loading.value || ended.value) return
    clearPlayback();clock.pause(performance.now())
    busy = processing.value = true
    let finish!: () => void
    advancing = new Promise<void>(resolve => { finish = resolve })
    const epoch = generation
    try {
      let bar = buffer[offset]
      if (!bar && nextSource < ceiling) {
        loading.value = true
        try { await prefetch() } finally { if (epoch === generation) loading.value = switchingView }
        if (epoch !== generation || switchingView) return
        bar = buffer[offset]
      }
      if (!bar) { ended.value = true;pause();return }
      // Exactly one historical source candle: no elapsed-time catch-up or earlier wick reuse.
      now.value = bar.closeTime;account.consume(bar);offset++;emitBar(bar)
      for (const callback of sourceListeners) callback({ sessionId: sessionId.value, symbolId: symbol.value!.id, bar })
      await deps.settled?.()
      if (epoch !== generation) return
      if (buffer.length - offset < 100 && nextSource < ceiling && !fetchAhead)
        void prefetch().catch(cause => { if (epoch === generation) report(cause) })
    } catch (cause) { if (epoch === generation) report(cause) }
    finally {
      busy = processing.value = false
      if (epoch === generation) {
        clock.reset(performance.now())
        if (playing.value && !switchingView) { clock.play(performance.now());schedule() }
      }
      finish()
    }
  }
  function play() {
    if (!active.value || loading.value || ended.value) return
    error.value = '';playing.value = true
    if (!busy) { clock.play(performance.now());schedule() }
  }
  function setSpeed(value: number) { clock.setSpeed(value, performance.now());speed.value = value;schedule() }
  async function step() { pause();await advanceOne() }
  async function retry() { error.value = ''; if (failedTimeframe !== undefined) await setTimeframe(failedTimeframe); else if (failedStart !== undefined) await start(failedStart, failedStartAutoplay); else await step() }
  const timer = setInterval(() => {
    if (!active.value) return
    if (performance.now() - anchor >= 250) { anchor = performance.now(); for (const cb of pulses) cb(now.value) }
  }, 50)
  const visibility = () => { if (document.hidden) pause() }
  document.addEventListener('visibilitychange', visibility)
  function dispose() { disposed = true; pause(); generation++; viewEpoch++;viewAbort?.abort();abort.abort();clearInterval(timer); document.removeEventListener('visibilitychange', visibility); listeners.clear(); pulses.clear(); sourceListeners.clear() }
  return { open, active, loading, processing, playing, picking, error, now, speed, amount, ended, account, hasOrder, sourceStep, symbol, timeframe, cellId,
    actualTime, roundedPrice, place, start, startRandom, setTimeframe, exit, pause, play, setSpeed, step, retry, dispose,
    get chart() { return target }, get visibleBars() { return history },
    sessionId, subscribeSourceBars(callback: (event: ReplaySourceBar) => void) { sourceListeners.add(callback); return () => { sourceListeners.delete(callback) } },
  }
}
export type WorkspaceReplay = ReturnType<typeof createWorkspaceReplay>
