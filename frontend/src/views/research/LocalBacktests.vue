<template>
  <div class="backtests app-page">
    <header class="flex flex-wrap items-start justify-between gap-4">
      <div><h1 class="text-2xl font-semibold">策略回测</h1><p class="app-muted mt-2">基于所选价格数据、不计成本的多空策略模拟</p></div>
      <div class="flex gap-2"><RouterLink class="app-button-primary" to="/research/parameter-sweeps">批量比较参数</RouterLink><button class="app-button-secondary" @click="reload">刷新</button></div>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="workspace">
      <aside class="space-y-5">
        <form class="app-panel p-5 space-y-4" @submit.prevent="submit">
          <h2 class="font-semibold text-lg">新建回测</h2>
          <label>Python 策略<select v-model="form.strategy" required><option v-for="s in catalog?.strategies" :key="s.id" :value="s.id" :disabled="!!s.error">{{ s.name }}{{ s.error ? '（加载失败）' : '' }}</option></select></label>
          <p class="text-sm app-muted">{{ strategy?.description }} · {{ strategy?.warmup_rule ? "预热随参数计算，见数据预览" : `固定预热 ${strategy?.warmup_bars} 根` }}</p>
          <p v-for="s in catalog?.strategies.filter(v => v.error)" :key="s.id" class="error text-xs">{{ s.id }}：{{ s.error }}</p>
          <label v-for="(p, name) in strategy?.parameters" :key="name">{{ p.label || name }} {{ p.unit && !(p.label || "").includes(p.unit) ? p.unit : "" }}<span v-if="!parameterEnabled(p, parameters)" class="app-muted text-xs">（当前设置不使用）</span>
            <select v-if="p.options?.length" v-model="parameters[name]" :disabled="!parameterEnabled(p, parameters)"><option v-for="o in p.options" :key="String(o.value)" :value="o.value">{{ o.label }}</option></select>
            <input v-else-if="p.type === 'bool'" v-model="parameters[name]" :disabled="!parameterEnabled(p, parameters)" type="checkbox" />
            <input v-else-if="p.type === 'str'" v-model="parameters[name]" :disabled="!parameterEnabled(p, parameters)" type="text" />
            <input v-else v-model.number="parameters[name]" :disabled="!parameterEnabled(p, parameters)" type="number" :min="p.min ?? undefined" :max="p.max ?? undefined" :step="p.type === 'int' ? 1 : 'any'" required />
            <small v-if="p.help" class="app-muted">{{ p.help }}</small>
          </label>
          <label>币种<select v-model="form.symbol"><option v-for="s in catalog?.symbols" :key="s">{{ s }}</option></select></label>
          <label>周期<select v-model="form.timeframe"><option v-for="t in catalog?.timeframes[form.symbol]" :key="t">{{ t }}</option></select></label>
          <label>模拟成交周期<select v-model="form.execution_timeframe"><option value="">与信号周期相同</option><option v-for="t in executionFrames" :key="t">{{ t }}</option></select></label>
          <template v-if="form.execution_timeframe"><label><input v-model="form.intrabar_profit_protection" type="checkbox" /> 按细周期收盘更新利润保护</label><label>细周期不完整时<select v-model="form.execution_gap_policy"><option value="reject">停止并说明缺失区间</option><option value="coarse_fallback">回退主周期并记录</option></select></label></template>
          <label>开始时间（UTC，包含）<input v-model="form.start" type="datetime-local" required /></label>
          <label>结束时间（UTC，不包含）<input v-model="form.end" type="datetime-local" required /></label>
          <label>初始资金（报价币）<input v-model.number="form.initial_cash" type="number" min="0.01" step="any" required /></label>
          <label>每次仓位 %<input v-model.number="form.position_pct" type="number" min="0.01" max="100" step="any" required /></label>
          <p class="app-muted text-xs">成交时点由策略决定：收盘指令在下一根开盘执行，突破委托在后续触价时模拟成交。</p>
          <button type="button" class="app-button-secondary w-full" :disabled="busy || !strategy" @click="previewData">预览规则与数据</button>
          <BacktestPreflight v-if="dataPreview && previewStamp === draftStamp" :value="dataPreview" />
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
      <div class="min-w-0 space-y-5">
        <section v-if="selected" class="app-panel p-5 space-y-4">
          <div class="flex flex-wrap justify-between gap-3"><div><h2 class="text-xl font-semibold">{{ selected.config.symbol }} · {{ selected.config.timeframe }}</h2><p class="app-muted text-sm">{{ status(selected.status) }} · {{ selected.id }}</p></div>
            <div class="flex flex-wrap gap-2">
              <RouterLink v-if="selected.status === 'completed'" class="app-button-primary" :to="{ path: '/research/parameter-sweeps', query: { base_run: selected.id } }">用这组参数批量比较</RouterLink>
              <button v-if="!terminal(selected.status)" class="app-button-secondary" @click="act('cancel')">取消运行</button>
              <button v-else class="app-button-secondary" :disabled="!selected.metadata?.execution_bundle || !selected.metadata?.data_hash" @click="act('rerun')">按原版本重跑</button>
              <button v-if="terminal(selected.status) && selected.metadata?.data_hash" class="app-button-secondary" @click="act('migrate')">用当前引擎另建对照</button>
              <button v-if="selected.resume_available" class="app-button-primary" @click="act('resume')">继续保存已算结果</button>
              <button v-if="terminal(selected.status) && !selected.archived" class="app-button-secondary" @click="act('archive')">归档</button>
              <button class="app-button-secondary" @click="showLog">运行日志</button>
            </div>
          </div>
          <progress v-if="!terminal(selected.status)" :value="selected.progress" max="1" class="w-full" />
          <p v-if="selected.status === 'saving'" class="app-muted text-sm">计算结果已落盘，正在校验并发布 {{ selected.progress_detail?.done ?? 0 }} / {{ selected.progress_detail?.total ?? 0 }} 个记录块。中断后可继续保存。</p>
          <p v-if="selected.status === 'queued'" class="app-muted">等待现有后台进程领取任务；请保持后台运行。</p>
          <p v-if="selected.error" class="error">{{ selected.error }}</p>
          <ExecutionSummary :config="selected.config" :summary="selected.execution_summary ?? {}" :completed="selected.status === 'completed'" />
          <p v-if="historyGapCount" class="error">历史行情包含 {{ historyGapCount }} 段空档：未补造 K 线，跨空档持仓按下一条实际行情继续处理，无法判断空档内部是否触发止损。具体时间见下方数据来源记录。</p>
          <p v-if="selected.status === 'interrupted'" class="error">运行被中断。已有数据快照可用于重跑；尚无完整快照时请重新创建。</p>
          <pre v-if="log !== null" class="log">{{ log }}</pre>
          <details v-if="selected.metadata?.rules_summary"><summary>本次保存的规则说明</summary><p v-for="line in selected.metadata?.rules_summary as string[]" :key="line">{{ line }}</p></details>
          <details><summary>参数、数据来源与版本</summary><pre class="log">{{ JSON.stringify({ config: selected.config, metadata: selected.metadata }, null, 2) }}</pre></details>
        </section>
        <template v-if="selected?.status === 'completed'">
          <section class="metrics"><div v-for="[key, label] in metrics" :key="key" class="app-panel p-4"><span class="app-muted text-sm">{{ label }}</span><strong class="block text-xl mt-2">{{ number(selected.report?.[key]) }}</strong></div></section>
          <p class="app-muted text-sm">无亏损时利润因子为空；无交易时胜率为空。持仓时间在 K 线内退出时按所属 K 线近似。</p>
          <BacktestDiagnostics :run-id="selected.id" />
          <section class="app-panel p-5"><label v-if="selected.config.execution_timeframe" class="mb-3">权益采样<select v-model="equityKind" @change="loadEquity"><option value="equity">信号周期收盘</option><option value="execution_equity" :disabled="selected.report?.execution_close_max_drawdown_pct == null">实际成交周期收盘（含已记录回退）</option></select></label><h3 class="font-semibold mb-3">资金曲线（报价币）</h3><div class="curve"><TradingViewChart ref="equityChart" :data="equityData" chart-type="area" /></div><h3 class="font-semibold my-3">收盘权益回撤 %</h3><div class="curve"><TradingViewChart ref="drawdownChart" :data="drawdownData" chart-type="area" /></div></section>
          <section ref="priceSection" class="app-panel p-5" :class="{ 'chart-expanded': expanded }">
            <div class="flex flex-wrap justify-between gap-3"><div><h3 class="font-semibold">K 线复盘{{ focused ? ` · 第 ${focused.trade_id} 笔` : '' }}</h3><p class="app-muted text-xs mt-2">{{ selected.config.symbol }} · {{ selected.config.timeframe }} · {{ runSummary(selected) || strategyLabel(selected) }}</p></div><div class="flex gap-2"><button v-if="focused" class="app-button-secondary" @click="focused = null; candleOffset = 0; loadCandles()">查看全部区间</button><button class="app-button-secondary" @click="expanded = !expanded">{{ expanded ? '收起图表' : '展开图表' }}</button></div></div>
            <p v-if="focused" class="app-muted text-sm my-2">{{ focused.side === 'long' ? '多仓' : '空仓' }} · {{ reason(focused.exit_reason) }} · 收益 {{ number(focused.profit) }}{{ focused.ambiguous ? ` · ${ambiguityLabel(focused)}` : '' }}{{ Array.isArray(focused.execution_fallback_times) && focused.execution_fallback_times.length ? ` · ${focused.execution_fallback_times.length} 段回退主周期` : '' }}</p>
            <TradeTimeline v-if="focused" :run-id="selected.id" :trade-id="Number(focused.trade_id)" />
            <div class="chart-controls">
              <label>图上标记<select v-model="markerMode"><option value="signals">全部多空信号</option><option value="fills">实际成交</option></select></label>
              <label>价格刻度<select v-model="logarithmic"><option :value="false">线性</option><option :value="true">对数</option></select></label>
              <label>图表时区<select v-model="timezoneOffset"><option :value="0">UTC</option><option :value="8">UTC+8</option></select></label>
              <label>图表背景<select v-model="lightChart"><option :value="false">深色</option><option :value="true">浅色</option></select></label>
            </div>
            <p v-if="markerMode === 'signals'" class="app-muted text-xs mt-3">信号标在条件产生的 K 线上，收盘后才确认。突破委托需随后触价，信号不等于已经成交；实际操作请切换“实际成交”。</p>
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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { signalMarkers, fillMarkers, signalStatus, exitReason as reason } from '@/modules/research/tradePresentation'
import BacktestPreflight from '@/components/research/BacktestPreflight.vue'
import { parameterEnabled } from '@/modules/research/strategyParameters'
import BacktestDiagnostics from '@/components/research/BacktestDiagnostics.vue'
import TradeTimeline from '@/components/research/TradeTimeline.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TradingViewChart from '@/components/TradingViewChart.vue'
import BacktestPriceChart from '@/components/research/BacktestPriceChart.vue'
import ExecutionSummary from '@/components/research/ExecutionSummary.vue'
import type { TradingViewDataPoint, TradingViewStrategyMarker } from '@/components/tradingViewChartPresentation'
import { localBacktestApi as api } from '@/modules/research/localBacktestApi'
import type { LocalBacktestCatalog, LocalBacktestCommand, LocalBacktestRun, LocalBacktestPreview } from '@/modules/research/generatedContracts'

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
const equityKind = ref<'equity' | 'execution_equity'>('equity')
const markerMode = ref<'signals' | 'fills'>('signals'), logarithmic = ref(route.query.scale === 'log'), timezoneOffset = ref(route.query.tz === '8' ? 8 : 0), inspectionTime = ref(0)
const expanded = ref(route.query.view === 'chart'), lightChart = ref(route.query.theme === 'light')
const strategyLabel = (run: LocalBacktestRun) => String((run.metadata?.strategy as Row | undefined)?.name || run.config.strategy)
const runSummary = (run: LocalBacktestRun) => {
  const summary = run.metadata?.rules_summary
  return Array.isArray(summary) ? String(summary[0] ?? '') : String((run.metadata?.strategy as Row | undefined)?.description ?? '旧记录没有保存规则说明')
}
const closeExpanded = (e: KeyboardEvent) => { if (e.key === 'Escape') expanded.value = false }
const historyGapCount = computed(() => {
  const gaps = selected.value?.metadata?.history_gaps
  return Array.isArray(gaps) ? gaps.length : 0
})
const inspection = computed(() => indicators.value.find(v => Number(v.timestamp) === inspectionTime.value))
const chartDate = (v: unknown) => date(Number(v) + timezoneOffset.value * 3600000) + (timezoneOffset.value ? ' UTC+8' : ' UTC')
const markers = computed<TradingViewStrategyMarker[]>(() => markerMode.value === 'signals' ? signalMarkers(signalRows.value) : fillMarkers(fillRows.value, focused.value ? [...trades.value, focused.value] : trades.value, focused.value?.trade_id))
const end = new Date(); end.setUTCHours(0, 0, 0, 0)
const form = reactive({ strategy: 'ma_cross', symbol: 'BTC/USDT', timeframe: '1h', start: new Date(end.getTime() - 90 * 86400000).toISOString().slice(0, 16), end: end.toISOString().slice(0, 16), initial_cash: 10000, position_pct: 100, execution_timeframe: '', intrabar_profit_protection: false, execution_gap_policy: 'reject' as 'reject' | 'coarse_fallback' })
const timeframeMinutes: Record<string, number> = { '1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440 }
const executionFrames = computed(() => ['1m', '5m', '15m', '30m', '1h'].filter(t => timeframeMinutes[t]! < timeframeMinutes[form.timeframe]!))
watch(() => form.timeframe, () => { if (!executionFrames.value.includes(form.execution_timeframe)) form.execution_timeframe = '' })
const parameters = reactive<Record<string, any>>({})
const strategy = computed(() => catalog.value?.strategies.find(s => s.id === form.strategy))
watch(strategy, s => { Object.keys(parameters).forEach(k => delete parameters[k]); for (const [k, p] of Object.entries(s?.parameters ?? {})) parameters[k] = p.default })
watch(() => form.symbol, s => { const list = catalog.value?.timeframes[s] ?? []; if (!list.includes(form.timeframe)) form.timeframe = list[0] ?? '' })
const terminal = (s: string) => ['completed', 'failed', 'cancelled', 'interrupted'].includes(s)
const status = (s: string) => ({ queued: '排队中', preparing: '准备数据', running: '计算并记录', saving: '校验与保存', completed: '完成', failed: '失败', cancelled: '已取消', interrupted: '已中断' }[s] ?? s)
const ambiguityLabel = (trade: Row) => trade.entry_bar_ambiguous ? trade.entry_ambiguity_policy === 'adverse_extreme_before_entry' ? '先后不明，按不利极值发生在入场前处理' : '先后不明，按入场后触发止损处理' : '同根触及止盈止损，按止损优先处理'
const number = (v: unknown) => v == null ? '—' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 6 })
const date = (v: unknown) => new Date(typeof v === 'number' ? v : String(v)).toISOString().replace('T', ' ').replace('.000Z', '')
const metrics = [['return_pct', '总收益 %'], ['final_equity', '期末权益'], ['profit', '已实现盈亏'], ['max_drawdown_pct', '主周期收盘最大回撤 %'], ['execution_close_max_drawdown_pct', '成交周期收盘最大回撤 %'], ['total_trades', '交易次数'], ['win_rate', '胜率 %'], ['average_return_pct', '平均单笔收益 %'], ['payoff_ratio', '盈亏比'], ['profit_factor', '利润因子'], ['average_duration_minutes', '平均持仓分钟'], ['breakeven', '保本交易'], ['ambiguous_trades', '先后顺序不确定的交易']] as const
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
async function choose(run: LocalBacktestRun) { equityKind.value = 'equity'; selected.value = run; log.value = null; focused.value = null; tradeOffset.value = signalOffset.value = candleOffset.value = 0; trades.value = []; signals.value = []; candles.value = []; equity.value = []; await router.replace({ query: { run: run.id } }); if (run.status === 'completed') await loadResults() }
const dataPreview = ref<LocalBacktestPreview>(), previewStamp = ref('')
const draftStamp = computed(() => JSON.stringify({ form, parameters }))
const command = (): LocalBacktestCommand => ({ ...form, timeframe: form.timeframe as LocalBacktestCommand['timeframe'], execution_timeframe: (form.execution_timeframe || null) as LocalBacktestCommand['execution_timeframe'], intrabar_profit_protection: !!form.execution_timeframe && form.intrabar_profit_protection, start: new Date(form.start + 'Z').toISOString(), end: new Date(form.end + 'Z').toISOString(), parameters: { ...parameters } })
async function previewData() { busy.value = true; error.value = ''; await safe(async () => { const stamp = draftStamp.value; dataPreview.value = await api.preview(command()); previewStamp.value = stamp }); busy.value = false }
async function submit() { busy.value = true; error.value = ''; await safe(async () => { const run = await api.create(command()); await choose(run); await refresh() }); busy.value = false }
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
async function loadEquity() { await safe(async () => { const id = selected.value!.id, kind = equityKind.value; const p = await api.records(id, kind, { sampled: true, limit: Math.max(300, Math.min(window.innerWidth, 2000)) }); if (selected.value?.id === id && equityKind.value === kind) equity.value = p.items }) }
async function loadResults() { await Promise.all([loadTrades(), loadSignals(), loadCandles(), loadEquity()]) }
async function focusTrade(t: Row) { focused.value = t; candleOffset.value = 0; await loadCandles(); priceSection.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }
async function act(action: 'cancel' | 'rerun' | 'migrate' | 'resume' | 'archive') { await safe(async () => { const run = await api[action](selected.value!.id); await choose(run); await refresh() }) }
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
