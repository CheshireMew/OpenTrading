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
import { installIndicatorHelp } from './indicatorHelp'
import { registerWorkspaceDrawingDefaults } from './drawingDefaults'

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
  const sync = ref<Record<string, boolean>>({ viewport: true, crosshair: true, symbol: false, timeframe: false })
  const activeSymbol = computed(() => symbols.value.find(symbol => symbol.id === activeSymbolId.value))
  const backendPeriod = computed(() => timeframes[activeTimeframe.value] ?? activeTimeframe.value)
  const historyText = computed(() => {
    const history = historyByCell.value[activeCell.value]
    if (!history && feedStatus.value === 'error') return cw('incomplete')
    return history ? cw('historyBars', { count: formatNumber(history.loaded, 0) }) +
      (history.state === 'loading' ? ' · ' + cw('loading') : history.state === 'aborted' ? ' · ' + cw('incomplete') : '') : cw('loadingHistory')
  })
  const feedText = computed(() => replay.active.value ? cw('replay') : ({ connecting: cw('connecting'), live: cw('live'), polling: cw('polling'), offline: cw('offline'), error: cw('dataError') }[feedStatus.value] ?? feedStatus.value))
  const engines = new Set<OpenTradingPineEngine>(), configuredCharts = new WeakSet<Vela>()
  let provider: OpenTradingProvider | undefined, snapshotChart: Vela | undefined
  const paper = createWorkspacePaper({ workspace, symbols, symbolId: activeSymbolId, timeframe: backendPeriod,
    subscribe: (id, tf, onBar) => provider!.subscribe(id, tf, onBar) })
  let disposeDrawings: (() => void) | undefined, disposeLocale: (() => void) | undefined, disposeToolbarIcons: (() => void) | undefined
  let disposeIndicatorHelp: (() => void) | undefined
  let disposed = false, marketEpoch = 0
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
    }
  }
  function setHistoryDepth(depth: number) {
    for (const cell of workspace.value?.cells() ?? []) void cell.chart.setMarket({ bars: depth })
    historyDepth.value = depth
    deps.dirty()
  }
  function applyChartTheme() {
    const chart = workspace.value
    if (!chart) return
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
    }
  }
  async function setLayout(value: string) { if (replay.active.value) await replay.exit(); workspace.value?.setLayout(value); applyChartTheme(); projectActive() }
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
    marketEpoch++
    const info = symbols.value.find(symbol => symbol.id === id), context = workspace.value?.context()
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
    return state
  }
  function restore(data: Record<string, any>) {
    // A background save/merge must never replace the running replay market.
    // Explicit layout selection exits replay in the page before restoring it.
    if (replay.active.value) return
    if (data.state) workspace.value?.applyState(data.state)
    // In-place layout restores keep the chart instance and overwrite its config.
    for (const cell of workspace.value?.cells() ?? []) {
      cell.chart.renderer.applyConfig({ animations: DIRECT_CHART_MOTION })
      separateVolumePane(cell.chart)
    }
    applyChartTheme()
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
    })
    provider.catalog = symbols.value
    const chart = new VelaWorkspace(deps.host.value, {
      layout: '1', symbol: velaSymbol('binance:spot:BTCUSDT'), timeframe: '60', bars: 1000,
      live: true, theme: chartTheme(deps.theme.value), renderer: WorkspaceRenderer,
      volume: false, timezone: 'Asia/Shanghai', watermark: false,
      animations: { ...DIRECT_CHART_MOTION, scroll: false },
      layoutMode: 'desktop', persist: false, sync: { viewport: true, crosshair: true },
      topbar: { left: ['style', 'undo-redo'], right: ['panels'] },
      drawings: { tools: ['trendline', 'ray', 'hline', 'vline', 'parallelchannel', 'box', 'fibretracement', 'text', 'arrow', 'freehand', 'datepricerange'] },
      providers: { opentrading: () => provider! },
      engines: { pine: () => { const engine = new OpenTradingPineEngine(() => symbols.value, replay.actualTime); engines.add(engine); return engine } },
    })
    // Vela registers its built-ins when the first chart is constructed.
    registerWorkspaceIndicatorDefinitions()
    registerWorkspaceDrawingDefaults()
    workspace.value = chart
    configureCells()
    applyChartTheme()
    chart.on('cell:created', configureCells)
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
  }
  const stopTheme = watch(deps.theme, applyChartTheme)
  function dispose() {
    cursor.dispose()
    replay.dispose()
    paper.dispose()
    disposed = true
    marketEpoch++
    stopTheme()
    disposeIndicatorHelp?.(); disposeLocale?.(); disposeDrawings?.(); disposeToolbarIcons?.()
    workspace.value?.destroy()
    workspace.value = undefined
    provider?.destroy()
    for (const engine of engines) engine.terminate()
    engines.clear()
  }
  return { workspace, symbols, activeCell, activeSymbolId, activeTimeframe, activeSymbol, backendPeriod,
    layout, historyDepth, historyText, feedText, feedError, sync, snapshotRun,
    replay, paper, cursor, initializationFailed, selectSymbol, setPeriod, setLayout, setSync, setHistoryDepth, returnLive, locateTrade, snapshot, restore, initialize, dispose }
}
