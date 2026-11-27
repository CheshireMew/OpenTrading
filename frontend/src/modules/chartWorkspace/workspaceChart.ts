import { computed, ref, shallowRef, watch, type Ref } from 'vue'
import { VelaWorkspace } from '@luxalgo/vela/workspace'
import { type Vela, type OHLCV } from '@luxalgo/vela'
import { CHART_FONT, chartPalette, chartTheme, WorkspaceRenderer } from './chartPresentation'
import { OpenTradingPineEngine } from './pineEngine'
import { OpenTradingProvider, fromVela, velaSymbol, timeframes } from './provider'
import { chartApi, type ChartSymbol, type PineRun } from './api'
import { bindWorkspaceRenderer, installMarketDrawings } from './persistence'
import { localizeChart } from './localize'
import { cw, formatDate, formatNumber } from './locale'
import { installDrawingToolbarIcons } from './drawingToolbarIcons'
import { createWorkspaceReplay } from './workspaceReplay'
import { createWorkspacePaper } from './workspacePaper'
import { createWorkspaceCursor } from './workspaceCursor'
import { registerWorkspaceIndicatorDefinitions } from './workspaceIndicatorDefinitions'
import { registerMovingAverageDefinitions } from './movingAverages'
import { installIndicatorHelp } from './indicatorHelp'
import { registerWorkspaceDrawingDefaults } from './drawingDefaults'
import { installCellTimeframe } from './cellTimeframes'
import { installChartHistory } from './chartHistory'

const DIRECT_CHART_MOTION = { zoom: false, pan: false, autoscale: false } as const

function separateVolumePane(chart: Vela) {
  const pricePane = chart.panes.list().find(pane => pane.kind === 'price')
  const volume = chart.indicators().find(indicator => indicator.nativeType === 'volume')
  if (pricePane && volume && pricePane.indicators.some(indicator => indicator.id === volume.id)) {
    volume.moveTo({ newPane: { after: pricePane.id } })
  }
}

export function createWorkspaceChart(deps: {
  host: Ref<HTMLElement | undefined>
  controlsHost?: Ref<HTMLElement | undefined>
  theme: Readonly<Ref<'light' | 'dark'>>
  dirty: () => void
  refreshQuotes: () => void
  log: (message: string) => void
  onError: (error: unknown) => void
}) {
  const workspace = shallowRef<VelaWorkspace>(), symbols = ref<ChartSymbol[]>([])
  const cursor = createWorkspaceCursor({ workspace, host: deps.host })
  const activeCell = ref('c1'), activeSymbolId = ref('binance:spot:BTCUSDT'), activeTimeframe = ref('60')
  const layout = ref('1'), historyDepth = ref(1000), snapshotRun = ref('')
  const replay = createWorkspaceReplay({ workspace, symbols, settled:async()=>{await Promise.all([...engines].map(engine=>engine.settled()))} })
  const historyByCell = ref<Record<string, { loaded: number; state: string }>>({})
  const feedStatus = ref('connecting'), feedError = ref('')
  const sync = ref<Record<string, boolean>>({ viewport: false, crosshair: true, symbol: false, timeframe: false })
  const activeSymbol = computed(() => symbols.value.find(symbol => symbol.id === activeSymbolId.value))
  watch(() => activeSymbol.value?.close_only, (closeOnly, previous) => {
    if (closeOnly !== undefined && previous !== undefined && closeOnly !== previous) {
      workspace.value?.context().setPriceStyle(closeOnly ? 'line' : 'candles')
    }
  })
  const backendPeriod = computed(() => timeframes[activeTimeframe.value] ?? activeTimeframe.value)
  const historyText = computed(() => {
    const history = historyByCell.value[activeCell.value]
    if (!history && feedStatus.value === 'error') return cw('incomplete')
    return history ? cw('historyBars', { count: formatNumber(history.loaded, 0) }) +
      (history.state === 'loading' ? ' · ' + cw('loading') : history.state === 'aborted' ? ' · ' + cw('incomplete') : '') : cw('loadingHistory')
  })
  const feedText = computed(() => replay.active.value ? cw('replay') : ({ connecting: cw('connecting'), live: cw('live'), polling: cw('polling'), delayed: cw('delayedQuotes'), offline: cw('offline'), error: cw('dataError') }[feedStatus.value] ?? feedStatus.value))
  const engines = new Set<OpenTradingPineEngine>(), configuredCharts = new WeakSet<Vela>()
  const cellTimeframes = new Map<string, () => void>()
  const cellHistories = new Map<string, ReturnType<typeof installChartHistory>>()
  let provider: OpenTradingProvider | undefined, snapshotChart: Vela | undefined
  const paper = createWorkspacePaper({ workspace, symbols, symbolId: activeSymbolId, timeframe: backendPeriod,
    subscribe: (id, tf, onQuote) => provider!.subscribeQuotes(id, tf, onQuote) })
  let disposeDrawings: (() => void) | undefined, disposeLocale: (() => void) | undefined, disposeToolbarIcons: (() => void) | undefined
  let disposeIndicatorHelp: (() => void) | undefined
  let disposed = false, paused = false, marketEpoch = 0
  let preloadTimer: ReturnType<typeof setTimeout> | undefined, preloadAbort: AbortController | undefined, preloadKey = ''
  function cancelPreload() { clearTimeout(preloadTimer); preloadAbort?.abort(); preloadKey = '' }
  function preload(id: string, timeframe: string) {
    if (disposed || paused || !provider) return
    const key = `${id}:${timeframe}:${replay.active.value ? replay.now.value : 'live'}`
    if (key === preloadKey) return
    cancelPreload(); preloadKey = key
    const controller = preloadAbort = new AbortController()
    preloadTimer = setTimeout(() => {
      const request = replay.active.value && id === activeSymbolId.value
        ? replay.preloadTimeframe(timeframe, controller.signal) : provider!.preload(id, timeframe, controller.signal)
      void request.catch(() => {}).finally(() => { if (preloadAbort === controller) preloadKey = '' })
    }, 100)
  }
  function preloadSymbol(id: string) {
    const info = symbols.value.find(symbol => symbol.id === id)
    if (info && id !== activeSymbolId.value) preload(id, info.timeframes.includes(backendPeriod.value) ? activeTimeframe.value : 'D')
  }
  function preloadPeriod(timeframe: string) {
    if (timeframe !== activeTimeframe.value) preload(activeSymbolId.value, timeframe)
  }
  let catalogRequest: Promise<void> | undefined
  const discoveredSymbols = new Map<string, ChartSymbol>()
  let catalogTimer: ReturnType<typeof setInterval> | undefined
  function startCatalogRefresh() {
    if (disposed || paused || !workspace.value || catalogTimer !== undefined) return
    const refresh = () => { void refreshCatalog().catch(() => {}) }
    catalogTimer = setInterval(refresh, 60_000)
    refresh()
  }
  function pause() {
    paused = true; clearInterval(catalogTimer); catalogTimer = undefined
    cancelPreload(); provider?.setPaused(true)
  }
  function resume() {
    paused = false; provider?.setPaused(false)
    for (const history of cellHistories.values()) history.refresh()
    startCatalogRefresh()
  }
  function refreshCatalog() {
    if (disposed) return Promise.resolve()
    return catalogRequest ??= chartApi.symbols(undefined, { waitForRefresh: true }).then(catalog => {
      if (disposed) return
      symbols.value = [...new Map([...discoveredSymbols.values(), ...catalog].map(info => [info.id, info])).values()]
      if (provider) provider.catalog = symbols.value
    }).finally(() => { catalogRequest = undefined })
  }
  function registerSymbols(discovered: ChartSymbol[]) {
    if (disposed) return
    for (const info of discovered) discoveredSymbols.set(info.id, info)
    symbols.value = [...new Map([...symbols.value, ...discovered].map(info => [info.id, info])).values()]
    if (provider) provider.catalog = symbols.value
  }
  function initializationFailed() { feedStatus.value = 'error' }
  function returnLive() {
    if (snapshotChart) void snapshotChart.setMarket({ data: undefined })
    snapshotChart = undefined
    snapshotRun.value = ''
  }
  function projectActive() {
    const cell = workspace.value?.active
    if (!cell) return
    activeCell.value = cell.id
    activeSymbolId.value = fromVela(cell.symbol)
    activeTimeframe.value = cell.timeframe
    historyDepth.value = cell.chart.market.bars ?? 1000
    layout.value = workspace.value!.getState().layout
    const status = provider?.statuses.get(activeSymbolId.value)
    feedStatus.value = status?.status ?? 'connecting'
    feedError.value = status?.error ?? ''
  }
  function configureCells() {
    for (const cell of workspace.value?.cells() ?? []) {
      if (configuredCharts.has(cell.chart)) continue
      cellTimeframes.set(cell.id, installCellTimeframe(cell, {
        symbols,
        select: async timeframe => { workspace.value?.setActiveCell(cell.id); await setPeriod(timeframe) },
        onError: deps.onError,
      }))
      bindWorkspaceRenderer(cell.chart, cell.host)
      WorkspaceRenderer.forHost(cell.host)?.bindIndicatorInteraction({
        activate: () => workspace.value?.setActiveCell(cell.id),
        enabled: () => !cell.chart.drawings.getTool() && !cell.chart.drawings.getMode() &&
          ['cross', 'dot', 'arrow'].includes(cursor.mode.value),
      })
      // Vela's menu reset frames ALL loaded history. Reset this cell to the
      // same candle size as startup instead, while restoring automatic scaling.
      cell.resetView = () => {
        cell.chart.renderer.set('autoScale', true)
        WorkspaceRenderer.forHost(cell.host)?.frameRecentCandles()
      }
      // Pooled cells can carry animation settings from an older saved layout.
      cell.chart.renderer.applyConfig({ animations: DIRECT_CHART_MOTION })
      configuredCharts.add(cell.chart)
      separateVolumePane(cell.chart)
      // Volume may mount after the initial market load or be restored from a layout.
      cell.chart.on('indicator:added', () => separateVolumePane(cell.chart))
      // Indicator changes are immediate; the workspace's state event is delayed.
      // Capture them now so autosave cannot restore an already closed study.
      for (const event of ['indicator:added', 'indicator:removed', 'indicator:visibility', 'indicator:moved', 'indicator:inputs'] as const) {
        cell.chart.on(event, deps.dirty)
      }
      cell.chart.on('load:start', () => { historyByCell.value[cell.id] = { loaded: 0, state: 'loading' } })
      cell.chart.on('history:progress', event => { historyByCell.value[cell.id] = { loaded: event.loaded, state: 'loading' } })
      cell.chart.on('history:complete', event => { historyByCell.value[cell.id] = { loaded: event.barsLoaded, state: event.reason } })
      const history = installChartHistory(cell.chart, {
        enabled: () => !disposed && !paused,
        onLoading: loaded => { historyByCell.value[cell.id] = { loaded, state: 'loading' } },
        onDepth: depth => { if (activeCell.value === cell.id) historyDepth.value = depth; deps.dirty() },
        onError: deps.onError,
      })
      const offViewport = WorkspaceRenderer.forHost(cell.host)?.onHistoryViewport(history.refresh)
      cellHistories.set(cell.id, { refresh: history.refresh, dispose: () => { offViewport?.(); history.dispose() } })
    }
  }
  function applyChartTheme(preserveAppearance = false) {
    const chart = workspace.value
    if (!chart) return
    const appearances = preserveAppearance ? new Map(chart.cells().map(cell => [cell.id, cell.chart.renderer.getConfig()])) : undefined
    const colors = chartPalette(deps.theme.value)
    chart.setTheme(chartTheme(deps.theme.value))
    for (const cell of chart.cells()) {
      cell.chart.renderer.applyConfig({
        layout: { background: colors.panel, textColor: colors.text, fontFamily: CHART_FONT, fontSize: 12 },
        grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
        priceScale: { borderColor: colors.border },
        panes: { separatorColor: colors.borderStrong },
        candles: { upColor: colors.positive, downColor: colors.negative, wickUpColor: colors.positive, wickDownColor: colors.negative, borderUpColor: colors.positive, borderDownColor: colors.negative },
        bars: { upColor: colors.positive, downColor: colors.negative },
      })
      const appearance = appearances?.get(cell.id)
      if (appearance) cell.chart.renderer.applyConfig(appearance)
    }
  }
  async function setLayout(value: string) { if (replay.active.value) await replay.exit(); workspace.value?.setLayout(value); applyChartTheme(true); projectActive() }
  function setSync(key: string, on: boolean) { sync.value[key] = on; workspace.value?.sync.set(key as 'symbol', on) }
  async function setPeriod(timeframe: string) {
    marketEpoch++
    if (replay.active.value) { await replay.setTimeframe(timeframe);projectActive();return }
    if (snapshotRun.value) returnLive()
    workspace.value?.context().setTimeframe(timeframe)
    projectActive()
  }
  async function selectSymbol(id: string) {
    const replaying = replay.active.value, date = replay.now.value
    if (replaying) await replay.exit()
    const epoch = ++marketEpoch
    let info = symbols.value.find(symbol => symbol.id === id)
    if (!info) {
      try {
        const catalog = await chartApi.symbols(id)
        if (disposed || epoch !== marketEpoch) return
        const found = catalog.find(symbol => symbol.id === id)
        if (!found) throw new Error(cw('symbolUnavailable', { symbol: id }))
        registerSymbols([found]); info = found
      } catch (error) { if (!disposed && epoch === marketEpoch) deps.onError(error); return }
    }
    const context = workspace.value?.context()
    if (!info || !context) return
    if (!info.timeframes.includes(backendPeriod.value)) context.setTimeframe('D')
    if (snapshotRun.value) returnLive()
    context.setSymbol(velaSymbol(id))
    context.setPriceStyle(info.close_only ? 'line' : 'candles')
    projectActive()
    deps.refreshQuotes()
    if (replaying) await replay.start(date)
  }
  async function locateTrade({ time, run }: { time: number; run: PineRun }) {
    if (replay.active.value) await replay.exit()
    const cell = workspace.value?.active
    if (!cell || disposed) return
    await selectSymbol(run.request.symbol)
    await setPeriod(Object.keys(timeframes).find(key => timeframes[key] === run.request.timeframe) ?? '60')
    const epoch = marketEpoch
    try {
      const first = await chartApi.records(run.id, 'bars', 0, 10000), bars = [...first.items]
      for (let offset = bars.length; offset < first.total; offset += 10000) {
        if (disposed || epoch !== marketEpoch || workspace.value?.active !== cell) return
        bars.push(...(await chartApi.records(run.id, 'bars', offset, 10000)).items)
      }
      if (disposed || epoch !== marketEpoch || workspace.value?.active !== cell) return
      await cell.chart.setMarket({ symbol: velaSymbol(run.request.symbol), timeframe: cell.timeframe, data: bars as unknown as OHLCV[] })
      if (disposed || epoch !== marketEpoch) return
      snapshotChart = cell.chart
      snapshotRun.value = run.id
      cell.chart.setVisibleRange({ from: time - 12 * 3600000, to: time + 12 * 3600000 })
      deps.log(cw('locatedTrade', { run: run.id.slice(0, 8), time: formatDate(time) }))
    } catch (error) { if (!disposed && epoch === marketEpoch) deps.onError(error) }
  }
  function snapshot() {
    const state = workspace.value?.getState()
    if (state) for (const saved of state.charts) {
      if (saved.symbol && /^replay\d*:/.test(saved.symbol)) saved.symbol = velaSymbol(fromVela(saved.symbol))
      const live = workspace.value?.cells().find(cell => cell.id === saved.id)
      if (live) saved.bars = live.chart.market.bars ?? saved.bars
    }
    return state ? { ...state, viewportSyncVersion: 1 } : undefined
  }
  function restore(data: Record<string, any>) {
    // A background save/merge must never replace the running replay market.
    // Explicit layout selection exits replay in the page before restoring it.
    if (replay.active.value) return
    if (data.state) {
      const { viewportSyncVersion, ...state } = data.state
      // Older layouts saved the former linked-zoom default automatically.
      // Migrate it once; subsequent explicit sync choices are kept in snapshots.
      if (viewportSyncVersion !== 1) state.sync = { ...state.sync, viewport: false }
      // These views now live in the app sidebar. An older layout must not open
      // the library's separate dock alongside it.
      if (state.panels) state.panels = { ...state.panels,
        open: ['objects', 'dataWindow'].includes(state.panels.open) ? undefined : state.panels.open,
        pinned: state.panels.pinned?.filter((id: string) => id !== 'objects' && id !== 'dataWindow'),
      }
      workspace.value?.applyState(state)
    }
    // In-place layout restores keep the chart instance and overwrite its config.
    for (const cell of workspace.value?.cells() ?? []) {
      cell.chart.renderer.applyConfig({ animations: DIRECT_CHART_MOTION })
      separateVolumePane(cell.chart)
    }
    applyChartTheme(true)
    const state = workspace.value?.getState()
    if (state) for (const key of Object.keys(sync.value)) sync.value[key] = !!state.sync?.[key as 'symbol']
    projectActive()
  }
  function initialize(catalog: ChartSymbol[]) {
    if (disposed || workspace.value || !deps.host.value) return
    disposeIndicatorHelp = installIndicatorHelp(deps.host.value, () => workspace.value)
    symbols.value = catalog
    provider = new OpenTradingProvider((symbol, status, message) => {
      if (!disposed && symbol === activeSymbolId.value) { feedStatus.value = status; feedError.value = message ?? '' }
    }, info => registerSymbols([info]))
    provider.catalog = symbols.value
    provider.setPaused(paused)
    const initial = catalog.find(info => info.id === activeSymbolId.value)
      ?? catalog.find(info => info.market === 'spot')
      ?? catalog.find(info => info.market === 'alpha' || info.market === 'web3') ?? catalog[0]
    if (!initial) throw new Error(cw('loadFailed'))
    const initialTimeframe = initial.timeframes.includes('1h') ? '60' : Object.keys(timeframes).find(key => initial.timeframes.includes(timeframes[key]!)) ?? 'D'
    const chart = new VelaWorkspace(deps.host.value, {
      layout: '1', symbol: velaSymbol(initial.id), timeframe: initialTimeframe, bars: 1000,
      live: true, theme: chartTheme(deps.theme.value), renderer: WorkspaceRenderer,
      volume: false, timezone: 'Asia/Shanghai', watermark: false,
      animations: { ...DIRECT_CHART_MOTION, scroll: false },
      layoutMode: 'desktop', persist: false, sync: { viewport: false, crosshair: true, symbol: false, timeframe: false },
      topbar: { left: ['style', 'undo-redo'], right: [] },
      drawings: { tools: ['trendline', 'ray', 'hline', 'vline', 'parallelchannel', 'box', 'fibretracement', 'text', 'arrow', 'freehand', 'datepricerange'] },
      providers: { opentrading: () => provider! },
      engines: { pine: () => { const engine = new OpenTradingPineEngine(() => symbols.value, replay.actualTime); engines.add(engine); return engine } },
    })
    // Vela registers its built-ins when the first chart is constructed.
    registerWorkspaceIndicatorDefinitions()
    registerMovingAverageDefinitions()
    registerWorkspaceDrawingDefaults()
    workspace.value = chart
    if (initial.close_only) chart.context().setPriceStyle('line')
    configureCells()
    applyChartTheme()
    chart.on('cell:created', configureCells)
    chart.on('cell:destroyed', ({ id }) => {
      cellTimeframes.get(id)?.(); cellTimeframes.delete(id)
      cellHistories.get(id)?.dispose(); cellHistories.delete(id)
    })
    disposeDrawings = installMarketDrawings(chart, deps.dirty)
    // Keep Vela's live controls and history bindings, inside the main header.
    const controlsHost = deps.controlsHost?.value
    const nativeBar = deps.host.value.querySelector<HTMLElement>('.vela-widget-topbar')
    if (controlsHost && nativeBar) controlsHost.appendChild(nativeBar)
    const chromeHosts = controlsHost ? [deps.host.value, controlsHost] : [deps.host.value]
    const locales = chromeHosts.map(host => localizeChart(host, () => symbols.value))
    const icons = chromeHosts.map(installDrawingToolbarIcons)
    disposeLocale = () => locales.forEach(dispose => dispose())
    disposeToolbarIcons = () => icons.forEach(dispose => dispose())
    cursor.initialize()
    chart.sync.set('drawings', false)
    chart.on('state:changed', () => { projectActive(); deps.dirty() })
    chart.on('cell:active', () => { marketEpoch++; if (replay.active.value && chart.active.id !== replay.cellId.value) void replay.exit(); projectActive() })
    chart.on('layout:changed', projectActive)
    chart.on('script:run', event => { if (event.first) for (const warning of event.warnings) deps.log(String(warning.message)) })
    projectActive()
    startCatalogRefresh()
  }
  const stopTheme = watch(deps.theme, () => applyChartTheme())
  function dispose() {
    cursor.dispose()
    replay.dispose()
    paper.dispose()
    disposed = true
    marketEpoch++
    stopTheme()
    clearInterval(catalogTimer); catalogTimer = undefined
    cancelPreload()
    disposeIndicatorHelp?.(); disposeLocale?.(); disposeDrawings?.(); disposeToolbarIcons?.()
    for (const dispose of cellTimeframes.values()) dispose()
    cellTimeframes.clear()
    for (const history of cellHistories.values()) history.dispose()
    cellHistories.clear()
    workspace.value?.destroy()
    workspace.value = undefined
    provider?.destroy()
    for (const engine of engines) engine.terminate()
    engines.clear()
  }
  return { workspace, symbols, activeCell, activeSymbolId, activeTimeframe, activeSymbol, backendPeriod,
    layout, historyDepth, historyText, feedText, feedError, sync, snapshotRun,
    replay, paper, cursor, initializationFailed, selectSymbol, setPeriod, preloadPeriod, preloadSymbol, setLayout, setSync, returnLive, locateTrade, snapshot, restore, initialize, pause, resume, refreshCatalog, registerSymbols, dispose }
}
