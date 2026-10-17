<template>
  <div class="backtests app-page">
    <header class="flex flex-wrap items-start justify-between gap-4">
      <div><h1 class="text-2xl font-semibold">策略回测</h1><p class="app-muted mt-2">基于所选价格数据、不计成本的多空策略模拟</p></div>
      <button class="app-button-secondary" @click="reload">刷新</button>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="workspace">
      <aside class="space-y-5">
        <form class="app-panel p-5 space-y-4" @submit.prevent="submit">
          <h2 class="font-semibold text-lg">新建回测</h2>
          <label>Python 策略<select v-model="form.strategy" required><option v-for="s in catalog?.strategies" :key="s.id" :value="s.id" :disabled="!!s.error">{{ s.name }}{{ s.error ? '（加载失败）' : '' }}</option></select></label>
          <p class="text-sm app-muted">{{ strategy?.description }} · 预热 {{ strategy?.warmup_bars }} 根</p>
          <p v-for="s in catalog?.strategies.filter(v => v.error)" :key="s.id" class="error text-xs">{{ s.id }}：{{ s.error }}</p>
          <label v-for="(p, name) in strategy?.parameters" :key="name">{{ p.label || name }}
            <input v-if="p.type === 'bool'" v-model="parameters[name]" type="checkbox" />
            <input v-else-if="p.type === 'str'" v-model="parameters[name]" type="text" />
            <input v-else v-model.number="parameters[name]" type="number" :min="p.min ?? undefined" :max="p.max ?? undefined" :step="p.type === 'int' ? 1 : 'any'" required />
          </label>
          <label>币种<select v-model="form.symbol"><option v-for="s in catalog?.symbols" :key="s">{{ s }}</option></select></label>
          <label>周期<select v-model="form.timeframe"><option v-for="t in catalog?.timeframes[form.symbol]" :key="t">{{ t }}</option></select></label>
          <label>开始时间（UTC，包含）<input v-model="form.start" type="datetime-local" required /></label>
          <label>结束时间（UTC，不包含）<input v-model="form.end" type="datetime-local" required /></label>
          <label>初始资金（报价币）<input v-model.number="form.initial_cash" type="number" min="0.01" step="any" required /></label>
          <label>每次仓位 %<input v-model.number="form.position_pct" type="number" min="0.01" max="100" step="any" required /></label>
          <p class="app-muted text-xs">单币种、无杠杆；不计交易成本。下一根开盘成交，同根止盈止损按止损优先。</p>
          <button class="app-button-primary w-full" :disabled="busy || !strategy">{{ busy ? '提交中…' : '开始回测' }}</button>
        </form>
        <section class="app-panel p-5">
          <div class="flex justify-between items-center"><h2 class="font-semibold">运行记录</h2><label class="inline-label"><input v-model="archived" type="checkbox" @change="listOffset = 0; refresh()" /> 已归档</label></div>
          <p v-if="!runs.length" class="app-muted py-5">暂无回测记录</p>
          <button v-for="run in runs" :key="run.id" class="run" :class="{ active: selected?.id === run.id }" @click="choose(run)">
            <strong>{{ run.config.symbol }} · {{ strategyLabel(run) }}</strong><span v-if="runSummary(run)">{{ runSummary(run) }}</span><span>{{ status(run.status) }} · {{ date(run.created_at) }}</span>
          </button>
          <div class="pager"><button :disabled="listOffset === 0" @click="listOffset -= 30; refresh()">上一页</button><span>{{ listOffset + runs.length }} / {{ totalRuns }}</span><button :disabled="listOffset + 30 >= totalRuns" @click="listOffset += 30; refresh()">下一页</button></div>
        </section>
      </aside>
      <main class="min-w-0 space-y-5">
        <section v-if="selected" class="app-panel p-5 space-y-4">
          <div class="flex flex-wrap justify-between gap-3"><div><h2 class="text-xl font-semibold">{{ selected.config.symbol }} · {{ selected.config.timeframe }}</h2><p class="app-muted text-sm">{{ status(selected.status) }} · {{ selected.id }}</p></div>
            <div class="flex flex-wrap gap-2">
              <button v-if="!terminal(selected.status)" class="app-button-secondary" @click="act('cancel')">取消运行</button>
              <button v-else class="app-button-secondary" :disabled="!selected.metadata?.data_hash" @click="act('rerun')">按快照重跑</button>
              <button v-if="terminal(selected.status) && !selected.archived" class="app-button-secondary" @click="act('archive')">归档</button>
              <button class="app-button-secondary" @click="showLog">运行日志</button>
            </div>
          </div>
          <progress v-if="!terminal(selected.status)" :value="selected.progress" max="1" class="w-full" />
          <p v-if="selected.status === 'queued'" class="app-muted">等待现有后台进程领取任务；请保持后台运行。</p>
          <p v-if="selected.error" class="error">{{ selected.error }}</p>
          <p v-if="selected.status === 'interrupted'" class="error">运行被中断。已有数据快照可用于重跑；尚无完整快照时请重新创建。</p>
          <pre v-if="log !== null" class="log">{{ log }}</pre>
          <details><summary>参数、数据来源与版本</summary><pre class="log">{{ JSON.stringify({ config: selected.config, metadata: selected.metadata }, null, 2) }}</pre></details>
        </section>
        <template v-if="selected?.status === 'completed'">
          <section class="metrics"><div v-for="[key, label] in metrics" :key="key" class="app-panel p-4"><span class="app-muted text-sm">{{ label }}</span><strong class="block text-xl mt-2">{{ number(selected.report?.[key]) }}</strong></div></section>
          <p class="app-muted text-sm">无亏损时利润因子为空；无交易时胜率为空。持仓时间在 K 线内退出时按所属 K 线近似。</p>
          <section class="app-panel p-5"><h3 class="font-semibold mb-3">资金曲线（报价币）</h3><div class="curve"><TradingViewChart ref="equityChart" :data="equityData" chart-type="area" /></div><h3 class="font-semibold my-3">收盘权益回撤 %</h3><div class="curve"><TradingViewChart ref="drawdownChart" :data="drawdownData" chart-type="area" /></div></section>
          <section ref="priceSection" class="app-panel p-5" :class="{ 'chart-expanded': expanded }">
            <div class="flex flex-wrap justify-between gap-3"><div><h3 class="font-semibold">K 线复盘{{ focused ? ` · 第 ${focused.trade_id} 笔` : '' }}</h3><p class="app-muted text-xs mt-2">{{ selected.config.symbol }} · {{ selected.config.timeframe }} · {{ runSummary(selected) || strategyLabel(selected) }}</p></div><div class="flex gap-2"><button v-if="focused" class="app-button-secondary" @click="focused = null; candleOffset = 0; loadCandles()">查看全部区间</button><button class="app-button-secondary" @click="expanded = !expanded">{{ expanded ? '收起图表' : '展开图表' }}</button></div></div>
            <p v-if="focused" class="app-muted text-sm my-2">{{ focused.side === 'long' ? '多仓' : '空仓' }} · {{ reason(focused.exit_reason) }} · 收益 {{ number(focused.profit) }} · 红线止损 / 绿线止盈{{ focused.ambiguous ? ' · 同根双触发，止损优先' : '' }}</p>
            <div class="chart-controls">
              <label>图上标记<select v-model="markerMode"><option value="signals">全部多空信号</option><option value="fills">实际成交</option></select></label>
              <label>价格刻度<select v-model="logarithmic"><option :value="false">线性</option><option :value="true">对数</option></select></label>
              <label>图表时区<select v-model="timezoneOffset"><option :value="0">UTC</option><option :value="8">UTC+8</option></select></label>
              <label>图表背景<select v-model="lightChart"><option :value="false">深色</option><option :value="true">浅色</option></select></label>
            </div>
            <p v-if="markerMode === 'signals'" class="app-muted text-xs mt-3">信号标在产生条件的 K 线上，收盘后才确认；模拟成交在下一根开盘。同向持仓期间的信号也全部保留。</p>
            <div class="price-chart"><BacktestPriceChart :key="selected.id" :data="candles" :markers="markers" :levels="levels" :indicators="indicators" :logarithmic="logarithmic" :timezone-offset="timezoneOffset" :light="lightChart" :label-signals="markerMode === 'signals'" @inspect="inspectionTime = $event" /></div>
            <div class="pager"><button :disabled="candleOffset === 0" @click="candleOffset = Math.max(0, candleOffset - 500); loadCandles()">前 500 根</button><span>{{ candleOffset + candles.length }} / {{ totalCandles }} 根</span><button :disabled="candleOffset + 500 >= totalCandles" @click="candleOffset += 500; loadCandles()">后 500 根</button></div>
            <div v-if="indicators.length" class="inspection">
              <label>逐根检查（也可点击 K 线）<select v-model="inspectionTime"><option v-for="v in indicators" :key="Number(v.timestamp)" :value="Number(v.timestamp)">{{ chartDate(v.timestamp) }}</option></select></label>
              <div v-if="inspection" class="inspection-grid">
                <dl><div v-for="(value, key) in inspection.values as Row" :key="key"><dt>{{ key }}</dt><dd>{{ number(value) }}</dd></div></dl>
                <dl><div v-for="(value, key) in inspection.checks as Row" :key="key"><dt>{{ key }}</dt><dd :class="value ? 'check-pass' : 'check-fail'">{{ value ? '满足' : '不满足' }}</dd></div></dl>
              </div>
            </div>
          </section>
          <section class="app-panel p-5">
            <div class="flex flex-wrap justify-between gap-3"><h3 class="font-semibold">逐笔交易</h3><div class="flex gap-2"><button v-for="f in exportFormats" :key="f" class="app-button-secondary" @click="download(f)">{{ f === 'json' ? '完整 JSON' : f === 'trades' ? '交易 CSV' : '权益 CSV' }}</button></div></div>
            <div class="table-scroll"><table><thead><tr><th>方向</th><th>入场 UTC</th><th>退出 UTC</th><th>入场价</th><th>退出价</th><th>盈亏</th><th>收益 %</th><th>退出原因</th></tr></thead><tbody><tr v-for="t in trades" :key="String(t.trade_id)" tabindex="0" @click="focusTrade(t)" @keydown.enter="focusTrade(t)"><td>{{ t.side === 'long' ? '多' : '空' }}</td><td>{{ date(t.entry_time) }}</td><td>{{ date(t.exit_time) }} ({{ t.exit_phase }})</td><td>{{ number(t.entry_price) }}</td><td>{{ number(t.exit_price) }}</td><td>{{ number(t.profit) }}</td><td>{{ number(t.return_pct) }}</td><td>{{ reason(t.exit_reason) }}{{ t.ambiguous ? ' · 顺序不确定' : '' }}</td></tr></tbody></table><p v-if="!trades.length" class="app-muted py-5">该区间没有已成交交易</p></div>
            <div class="pager"><button :disabled="tradeOffset === 0" @click="tradeOffset -= 50; loadTrades()">上一页</button><span>{{ tradeOffset + trades.length }} / {{ totalTrades }}</span><button :disabled="tradeOffset + 50 >= totalTrades" @click="tradeOffset += 50; loadTrades()">下一页</button></div>
          </section>
          <section class="app-panel p-5"><h3 class="font-semibold">完整信号记录</h3><div class="table-scroll"><table><thead><tr><th>产生时间 UTC</th><th>指令</th><th>结果</th><th>理由</th></tr></thead><tbody><tr v-for="(s, i) in signals" :key="i"><td>{{ date(s.decision_time) }}</td><td>{{ s.action }}</td><td>{{ signalStatus(s.status) }}</td><td>{{ s.reason }}</td></tr></tbody></table></div><div class="pager"><button :disabled="signalOffset === 0" @click="signalOffset -= 50; loadSignals()">上一页</button><span>{{ signalOffset + signals.length }} / {{ totalSignals }}</span><button :disabled="signalOffset + 50 >= totalSignals" @click="signalOffset += 50; loadSignals()">下一页</button></div></section>
        </template>
        <section v-else-if="!selected" class="app-panel p-12 app-muted text-center">创建或选择一次回测，查看资金曲线与交易过程。</section>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TradingViewChart from '@/components/TradingViewChart.vue'
import BacktestPriceChart from '@/components/research/BacktestPriceChart.vue'
import type { TradingViewDataPoint, TradingViewStrategyMarker } from '@/components/tradingViewChartPresentation'
import { localBacktestApi as api } from '@/modules/research/localBacktestApi'
import type { LocalBacktestCatalog, LocalBacktestCommand, LocalBacktestRun } from '@/modules/research/generatedContracts'

type Row = Record<string, unknown>
const route = useRoute(), router = useRouter()
const catalog = ref<LocalBacktestCatalog>(), runs = ref<LocalBacktestRun[]>([]), selected = ref<LocalBacktestRun | null>(null)
const error = ref(''), busy = ref(false), archived = ref(false), log = ref<string | null>(null)
const listOffset = ref(0), totalRuns = ref(0), tradeOffset = ref(0), totalTrades = ref(0), signalOffset = ref(0), totalSignals = ref(0), candleOffset = ref(0), totalCandles = ref(0)
const trades = ref<Row[]>([]), signals = ref<Row[]>([]), equity = ref<Row[]>([]), levels = ref<Row[]>([]), focused = ref<Row | null>(null)
const equityChart = ref<InstanceType<typeof TradingViewChart> | null>(null), drawdownChart = ref<InstanceType<typeof TradingViewChart> | null>(null)
watch(equity, async () => { await nextTick(); equityChart.value?.chart?.timeScale().fitContent(); drawdownChart.value?.chart?.timeScale().fitContent() }, { flush: 'post' })
const priceSection = ref<HTMLElement | null>(null)
const candles = ref<TradingViewDataPoint[]>([]), fillRows = ref<Row[]>([]), signalRows = ref<Row[]>([]), indicators = ref<Row[]>([])
const markerMode = ref<'signals' | 'fills'>('signals'), logarithmic = ref(route.query.scale === 'log'), timezoneOffset = ref(route.query.tz === '8' ? 8 : 0), inspectionTime = ref(0)
const expanded = ref(route.query.view === 'chart'), lightChart = ref(route.query.theme === 'light')
const strategyLabel = (run: LocalBacktestRun) => String((run.metadata?.strategy as Row | undefined)?.name || run.config.strategy)
const runMode = (run: LocalBacktestRun) => (run.config.parameters as Row | undefined)?.variant ?? (run.config.parameters as Row | undefined)?.mode
const comparisonLabels: Record<string, string> = {
  original_05: '原脚本 · ATR 0.5', original_15: '原脚本 · ATR 1.5', ema31_atr: 'EMA31＋ATR14 候选',
  ema31_range: 'EMA31＋高低差（无 ATR）', ema30_hlc3: 'hlc3／EMA30 候选', ema30_hl2: 'hl2／EMA30 候选',
  ema29_close: 'close／EMA29 候选', high_low_ema: '高低价 EMA31 通道', wma41_atr: 'WMA41＋ATR16',
  sma28_atr: 'SMA28＋ATR16', dual_ema: 'EMA26／36 双均线带', ema31_cross: '单 EMA31 穿越基准',
  buy_hold: '买入持有基准', cash: '持有现金基准',
}
const ruleLabel = (mode: unknown) => mode === 'original' ? '原始 Pine 规则' : mode === 'cross' ? '穿越候选（按截图拟合，原公式未确认）' : comparisonLabels[String(mode)] ?? String(mode)
const runSummary = (run: LocalBacktestRun) => {
  const mode = runMode(run)
  if (mode != null) return ruleLabel(mode)
  if (!['trend_cloud_profit_protection', 'trend_cloud_robustness_v1'].includes(String(run.config.strategy))) return ''
  const p = run.config.parameters as Row
  const method = ({
    slow_trend: `顺 EMA${p.method_value} 开仓`,
    efficiency: `震荡过滤 ${Number(p.method_value) * 100}%`,
    spacing: `入场间隔 ${Number(p.method_value) / 4} 小时`,
    alternate: '不连续开同向单',
  } as Record<string, string>)[String(p.entry_method)]
  return [`中心 EMA${p.center_length ?? 31}`, `宽度 EMA${p.width_length}`, `门槛 ${p.trigger_mult}`,
    Number(p.activation_pct) ? `盈利 ${p.activation_pct}% 后回吐 ${p.giveback_pct}% 平仓` : '无利润保护', method].filter(Boolean).join(' · ')
}
const closeExpanded = (e: KeyboardEvent) => { if (e.key === 'Escape') expanded.value = false }
const inspection = computed(() => indicators.value.find(v => Number(v.timestamp) === inspectionTime.value))
const chartDate = (v: unknown) => date(Number(v) + timezoneOffset.value * 3600000) + (timezoneOffset.value ? ' UTC+8' : ' UTC')
const markers = computed<TradingViewStrategyMarker[]>(() => markerMode.value === 'signals'
  ? signalRows.value.filter(v => v.action === 'long' || v.action === 'short').map(v => ({ time: Number(v.timestamp), kind: `${v.action}_entry`, position: v.action === 'short' ? 'aboveBar' : 'belowBar', label: v.action === 'long' ? '做多' : '做空', color: v.action === 'long' ? '#14b88a' : '#e85c5c' }))
  : fillRows.value.filter(v => !focused.value || v.trade_id === focused.value.trade_id).map(v => ({ time: Number(v.timestamp), kind: v.action === 'close' ? 'exit' : `${v.action}_entry`, position: v.action === 'long' ? 'belowBar' : 'aboveBar', label: `${v.action === 'close' ? '平仓' : v.action === 'long' ? '开多' : '开空'} ${number(v.price)}`, color: v.action === 'long' ? '#14b88a' : '#e85c5c' })))
const end = new Date(); end.setUTCHours(0, 0, 0, 0)
const form = reactive({ strategy: 'ma_cross', symbol: 'BTC/USDT', timeframe: '1h', start: new Date(end.getTime() - 90 * 86400000).toISOString().slice(0, 16), end: end.toISOString().slice(0, 16), initial_cash: 10000, position_pct: 100 })
const parameters = reactive<Record<string, any>>({})
const strategy = computed(() => catalog.value?.strategies.find(s => s.id === form.strategy))
watch(strategy, s => { Object.keys(parameters).forEach(k => delete parameters[k]); for (const [k, p] of Object.entries(s?.parameters ?? {})) parameters[k] = p.default })
watch(() => form.symbol, s => { const list = catalog.value?.timeframes[s] ?? []; if (!list.includes(form.timeframe)) form.timeframe = list[0] ?? '' })
const terminal = (s: string) => ['completed', 'failed', 'cancelled', 'interrupted'].includes(s)
const status = (s: string) => ({ queued: '排队中', preparing: '准备数据', running: '回测中', completed: '完成', failed: '失败', cancelled: '已取消', interrupted: '已中断' }[s] ?? s)
const signalStatus = (s: unknown) => ({ executed: '已执行', ignored_flat: '空仓，忽略平仓', ignored_same_side: '已有同向持仓', ignored_nonpositive_equity: '权益不足', unexecuted_end: '区间结束，未执行' }[String(s)] ?? String(s))
const reason = (s: unknown) => ({ stop_loss: '止损', take_profit: '止盈', profit_protection: '利润回吐保护', reversal: '反向信号', signal: '策略退出', end_of_backtest: '回测结束' }[String(s)] ?? String(s))
const number = (v: unknown) => v == null ? '—' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
const date = (v: unknown) => new Date(typeof v === 'number' ? v : String(v)).toISOString().replace('T', ' ').replace('.000Z', '')
const metrics = [['return_pct', '总收益 %'], ['final_equity', '期末权益'], ['profit', '已实现盈亏'], ['max_drawdown_pct', '收盘权益最大回撤 %'], ['total_trades', '交易次数'], ['win_rate', '胜率 %'], ['average_return_pct', '平均单笔收益 %'], ['payoff_ratio', '盈亏比'], ['profit_factor', '利润因子'], ['average_duration_minutes', '平均持仓分钟'], ['breakeven', '保本交易'], ['ambiguous_trades', '同根双触发交易']] as const
const exportFormats = ['json', 'trades', 'equity'] as const
const line = (key: string) => equity.value.map(v => ({ time: Number(v.timestamp) / 1000, open: Number(v[key]), high: Number(v[key]), low: Number(v[key]), close: Number(v[key]) }))
const equityData = computed(() => line('equity')), drawdownData = computed(() => line('drawdown_pct'))
let timer: ReturnType<typeof setTimeout> | undefined, disposed = false, refreshBusy = false
async function safe(work: () => Promise<unknown>) { try { await work() } catch (e) { error.value = e instanceof Error ? e.message : String(e) } }
async function reload() { error.value = ''; await safe(async () => { catalog.value = await api.catalog() }); await refresh() }
async function refresh() {
  if (refreshBusy) return
  refreshBusy = true
  try { await safe(async () => {
    const page = await api.list(listOffset.value, archived.value); runs.value = page.items; totalRuns.value = page.total
    const id = selected.value?.id || String(route.query.run || '')
    if (id) { const previous = selected.value; const run = await api.get(id); if (!selected.value || selected.value.id === id) { selected.value = run; if (run.status === 'completed' && (previous?.status !== 'completed' || previous.id !== id)) await loadResults() } }
  }) } finally { refreshBusy = false }
}
async function choose(run: LocalBacktestRun) { selected.value = run; log.value = null; focused.value = null; tradeOffset.value = signalOffset.value = candleOffset.value = 0; trades.value = []; signals.value = []; candles.value = []; equity.value = []; await router.replace({ query: { run: run.id } }); if (run.status === 'completed') await loadResults() }
async function submit() { busy.value = true; error.value = ''; await safe(async () => { const run = await api.create({ ...form, timeframe: form.timeframe as LocalBacktestCommand['timeframe'], start: new Date(form.start + 'Z').toISOString(), end: new Date(form.end + 'Z').toISOString(), parameters: { ...parameters } }); await choose(run); await refresh() }); busy.value = false }
async function loadTrades() { await safe(async () => { const id = selected.value!.id; const p = await api.records(id, 'trades', { offset: tradeOffset.value, limit: 50 }); if (selected.value?.id === id) { trades.value = p.items; totalTrades.value = p.total } }) }
async function loadSignals() { await safe(async () => { const id = selected.value!.id; const p = await api.records(id, 'signals', { offset: signalOffset.value, limit: 50 }); if (selected.value?.id === id) { signals.value = p.items; totalSignals.value = p.total } }) }
async function loadCandles() { await safe(async () => {
  const id = selected.value!.id, focus = focused.value, offset = candleOffset.value
  const durations: Record<string, number> = { '1m': 60000, '5m': 300000, '15m': 900000, '30m': 1800000, '1h': 3600000, '4h': 14400000, '1d': 86400000 }
  const step = durations[String(selected.value!.config.timeframe)] ?? 3600000
  const p = await api.records(id, 'candles', { offset, limit: 500, start: focus ? Number(focus.entry_time) - 5 * step : new Date(String(selected.value!.config.start)).getTime(), end: focus ? Number(focus.exit_time) + 5 * step : null })
  if (selected.value?.id !== id || focused.value !== focus || candleOffset.value !== offset) return
  candles.value = p.items.map(v => ({ time: Number(v.timestamp) / 1000, open: Number(v.open), high: Number(v.high), low: Number(v.low), close: Number(v.close) })); totalCandles.value = p.total
  if (!p.items.length) { levels.value = []; fillRows.value = []; signalRows.value = []; indicators.value = []; return }
  const start = Number(p.items[0]!.timestamp), end = Number(p.items[p.items.length - 1]!.timestamp)
  const [l, f, s, obs] = await Promise.all([api.records(id, 'levels', { start, end, limit: 5000 }), api.records(id, 'fills', { start, end, limit: 5000 }), api.records(id, 'signals', { start, end, limit: 5000 }), api.records(id, 'indicators', { start, end, limit: 5000 })])
  if (selected.value?.id !== id || focused.value !== focus || candleOffset.value !== offset) return
  levels.value = focus ? l.items.filter(v => v.trade_id === focus.trade_id) : []
  fillRows.value = f.items; signalRows.value = s.items; indicators.value = obs.items
  if (!obs.items.some(v => Number(v.timestamp) === inspectionTime.value)) inspectionTime.value = Number(obs.items[obs.items.length - 1]?.timestamp ?? 0)
}) }
async function loadResults() { const id = selected.value!.id; await Promise.all([loadTrades(), loadSignals(), loadCandles(), safe(async () => { const p = await api.records(id, 'equity', { sampled: true, limit: Math.max(300, Math.min(window.innerWidth, 2000)) }); if (selected.value?.id === id) equity.value = p.items })]) }
async function focusTrade(t: Row) { focused.value = t; candleOffset.value = 0; await loadCandles(); priceSection.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }
async function act(action: 'cancel' | 'rerun' | 'archive') { await safe(async () => { const run = await api[action](selected.value!.id); await choose(run); await refresh() }) }
async function showLog() { await safe(async () => { log.value = (await api.log(selected.value!.id)).content }) }
async function download(format: typeof exportFormats[number]) { await safe(async () => { const r = await api.export(selected.value!.id, format); const url = URL.createObjectURL(new Blob([r.content], { type: r.media_type + ';charset=utf-8' })); const a = document.createElement('a'); a.href = url; a.download = r.filename; a.click(); URL.revokeObjectURL(url) }) }
async function poll() { await refresh(); if (!disposed) timer = setTimeout(poll, 2000) }
onMounted(async () => { window.addEventListener('keydown', closeExpanded); await safe(async () => { catalog.value = await api.catalog() }); if (!disposed) await poll() })
onBeforeUnmount(() => { disposed = true; window.removeEventListener('keydown', closeExpanded); if (timer) clearTimeout(timer) })
</script>

<style scoped>
.backtests{padding:24px;max-width:1800px;margin:auto}.workspace{display:grid;grid-template-columns:300px minmax(0,1fr);gap:24px;margin-top:24px}label{display:block;font-size:13px}input:not([type=checkbox]),select{display:block;width:100%;padding:9px 11px;border:1px solid var(--app-border,#d1d5db);border-radius:8px;margin-top:6px;background:transparent;color:inherit}.inline-label{display:flex;align-items:center;gap:5px}.run{display:block;text-align:left;padding:12px;width:100%;border-radius:8px;margin-top:6px;border:1px solid transparent}.run span{display:block;font-size:11px;margin-top:6px;opacity:.7}.run.active{border-color:#14b88a;background:#14b88a12}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.curve{height:190px}.price-chart{height:370px;margin-top:16px}.table-scroll{overflow:auto;margin-top:14px;max-height:480px}table{width:100%;font-size:12px;text-align:left;white-space:nowrap}td,th{padding:10px 12px;border-bottom:1px solid #8882}tbody tr:hover{background:#14b88a12;cursor:pointer}.pager{display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:12px;margin-top:15px}.pager button{padding:6px 10px;border:1px solid #8884;border-radius:6px}button:disabled{opacity:.45;cursor:not-allowed}.error{background:#e85c5c15;color:#dc5656;border-radius:8px;padding:12px;margin-top:10px;overflow-wrap:anywhere}.log{max-height:350px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;padding:12px;background:#8881;border-radius:8px}summary{cursor:pointer;font-size:13px}@media(max-width:1100px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:800px){.workspace{grid-template-columns:1fr}.backtests{padding:16px}}
</style>
<style scoped>.chart-controls{display:flex;flex-wrap:wrap;gap:16px;margin-top:14px}.chart-controls label{min-width:135px}.price-chart{height:480px}.inspection{margin-top:20px;border-top:1px solid #8883;padding-top:16px}.inspection>label{max-width:320px}.inspection-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:16px}.inspection-grid dl>div{display:flex;justify-content:space-between;gap:12px;padding:6px 0;font-size:12px}.check-pass{color:#059669}.check-fail{color:#e85c5c}@media(max-width:700px){.inspection-grid{grid-template-columns:1fr}}</style>
<style scoped>.chart-expanded{position:fixed;inset:12px;z-index:1000;overflow:auto;box-shadow:0 0 0 20px #0009}.chart-expanded .price-chart{height:calc(100dvh - 240px);min-height:350px}</style>
