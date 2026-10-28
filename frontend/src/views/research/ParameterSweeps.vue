<template>
  <div class="app-page app-page-inner-wide sweeps">
    <header class="page-head">
      <h1 class="text-2xl font-semibold">批量参数比较</h1>
      <RouterLink class="app-button-secondary" to="/research/backtests">单次回测与 K 线复盘</RouterLink>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <div class="layout">
      <aside class="app-panel history">
        <div class="page-head"><h2 class="font-semibold">本地记录</h2><button class="text-sm" @click="guard(refreshHistory)">刷新</button></div>
        <p v-if="!history.length" class="app-muted mt-4">还没有批量比较</p>
        <button v-for="h in history" :key="String(h.id)" class="history-item" :class="{ active: selected?.id === h.id }" @click="guard(() => choose(String(h.id)))">
          <strong>{{ h.title }}</strong><span>{{ status(String(h.status)) }} · {{ h.total }} 组</span><small>{{ date(String(h.created_at)) }}</small>
        </button>
        <div class="pager"><button :disabled="historyOffset === 0" @click="historyOffset -= 10; guard(refreshHistory)">上一页</button><span>{{ historyOffset + history.length }}/{{ historyTotal }}</span><button :disabled="historyOffset + 10 >= historyTotal" @click="historyOffset += 10; guard(refreshHistory)">下一页</button></div>
        <p class="app-muted text-xs mt-4">关闭页面后继续运行。后台停止后，可从这里恢复；旧参数、结果和逐笔交易会保留。</p>
      </aside>
      <div class="space-y-5 min-w-0">
        <section v-if="selected" class="app-panel section" ref="resultSection">
          <div class="page-head"><div><h2 class="text-xl font-semibold">{{ selected.title }}</h2><p class="app-muted mt-1">{{ status(selected.status) }} · 已完成 {{ selected.counts.completed || 0 }} / {{ selected.total }} 组</p></div>
            <div class="actions"><button class="app-button-secondary" :disabled="busy" @click="copyVersion">复制参数，另建一版</button><button class="app-button-secondary" :disabled="busy" @click="guard(download)">导出 CSV</button><button v-if="selected.status === 'running'" class="app-button-secondary" :disabled="busy" @click="act('cancel')">取消未完成项</button><button v-if="selected.status === 'attention'" class="app-button-primary" :disabled="busy" @click="act('resume')">恢复未完成项</button></div>
          </div>
          <progress :value="selected.progress" max="1" class="w-full my-3" />
          <p class="app-muted text-sm">{{ countSummary }}。{{ selected.axes.position_pct ? "收益按各组合列出的仓位计算" : `每笔使用当时资金的 ${selected.request.base.position_pct ?? 100}%` }}，盈亏计入下一笔本金，不计手续费和滑点。</p>
          <p class="app-muted text-sm mt-2">{{ selected.request.base.symbol }} · {{ selected.request.base.start.slice(0, 10) }} 至 {{ selected.request.base.end.slice(0, 10) }} · {{ selected.axes.execution_timeframe || selected.axes.intrabar_profit_protection ? '成交和保护更新方式见各组合' : selected.request.base.execution_timeframe ? `${selected.request.base.execution_timeframe} 行情模拟成交` : '按信号周期模拟成交' }}{{ !selected.axes.execution_timeframe && !selected.axes.intrabar_profit_protection && selected.request.base.intrabar_profit_protection ? '，每根细周期收盘后更新利润保护' : '' }}</p>
          <div class="filters">
            <label>排序<select v-model="sort" @change="offset = 0; guard(refreshSelected)"><option value="return_pct">收益率从高到低</option><option value="win_rate">胜率从高到低</option><option value="max_drawdown_pct">最大回撤从小到大</option><option value="total_trades">交易次数从多到少</option></select></label>
            <label>至少交易几笔<input v-model.number="minimumTrades" type="number" min="0" step="1" @change="offset = 0; guard(refreshSelected)" /></label>
            <button class="app-button-secondary" :disabled="busy || !selected.counts.completed" @click="showEffects">查看参数影响</button>
          </div>
          <div class="table-scroll"><table><thead><tr><th>排名</th><th>参数组合</th><th>收益率</th><th>胜率</th><th>赚钱 / 亏钱</th><th>总笔数</th><th>最大回撤</th><th>状态 / 复盘</th></tr></thead>
            <tbody><tr v-for="(item, i) in selected.items" :key="item.case"><td>{{ offset + i + 1 }}</td><td class="combination">{{ combination(item) }}<p v-if="item.execution_summary?.fallback_intervals" class="text-xs mt-1">{{ item.execution_summary.fallback_intervals }} 段回退主周期</p><details v-if="item.status === 'completed'" class="mt-2"><summary>成交与版本</summary><ExecutionSummary :config="item.config ?? {}" :summary="item.execution_summary ?? {}" completed /></details></td><td :class="tone(item.report?.return_pct)">{{ percent(item.report?.return_pct) }}</td><td>{{ percent(item.report?.win_rate) }}</td><td>{{ integer(item.report?.wins) }} / {{ integer(item.report?.losses) }}</td><td>{{ integer(item.report?.total_trades) }}</td><td>{{ percent(item.report?.max_drawdown_pct) }}</td><td><RouterLink v-if="item.status === 'completed' && item.chart_path" :to="item.chart_path" class="link">查看 K 线</RouterLink><span v-else>{{ status(item.status) }}</span><p v-if="item.error" class="error cell-error">{{ item.error }}</p></td></tr></tbody>
          </table></div>
          <p v-if="!selected.items.length" class="app-muted py-4">没有满足当前筛选条件的结果。</p>
          <div class="pager"><button :disabled="offset === 0" @click="offset -= 30; guard(refreshSelected)">上一页</button><span>{{ offset + selected.items.length }} / {{ selected.filtered_total }}</span><button :disabled="offset + 30 >= selected.filtered_total" @click="offset += 30; guard(refreshSelected)">下一页</button></div>
          <section v-if="effects" class="effect-panel"><h3 class="font-semibold">只改变一个参数时，结果如何变化</h3><p class="app-muted text-sm my-2">参数影响只比较其他参数和行情证据相同的组合。周期实验另外标明聚合和采样差异；收益差是百分点。</p>
            <div v-for="effect in effects.effects" :key="String(effect.factor)" class="mt-3"><strong>{{ parameterLabel(String(effect.factor)) }}</strong><p v-if="!effectPairs(effect).length" class="app-muted text-sm">没有满足同条件比较的结果。</p><p v-for="(pair, i) in effectPairs(effect)" :key="i" class="text-sm mt-1">{{ effect.factor === 'timeframe' ? '不同聚合周期对照：' : effect.factor === 'execution_timeframe' ? '成交精度对照：' : '' }}从 {{ pair.before }} 改到 {{ pair.after }}：{{ pair.paired_comparisons }} 组对照中，{{ pair.improved }} 组收益提高；收益差中位数 {{ percent(pair.median_return_difference_percentage_points).replace("%", " 个百分点") }}。</p></div>
          </section>
          <details class="mt-4"><summary>完整参数、数据与本地保存位置</summary><p class="local-path my-3">{{ selected.path }}</p><pre>{{ JSON.stringify(selected.request, null, 2) }}</pre></details>
          <p class="app-muted text-xs mt-3">排名反映所选历史的表现，不能直接当作未来最佳参数。平本交易计入总笔数，未计入赚钱或亏钱次数。</p>
        </section>

        <form class="app-panel section" @submit.prevent="submit" ref="formSection">
          <div class="page-head"><div><h2 class="text-xl font-semibold">新建比较</h2><p class="app-muted text-sm mt-1">原来的固定版保留。这里只计算你选定的组合，每批最多 512 组。</p></div><span v-if="parent" class="badge">基于旧记录另建版本</span></div>
          <div class="form-grid mt-5">
            <label class="wide">记录名称<input v-model="title" required maxlength="160" placeholder="例如：ETH 15分钟，比较 EMA 和突破门槛" /></label>
            <label class="wide">策略<select v-model="base.strategy" required @change="resetParameters"><option v-for="s in catalog?.strategies" :key="s.id" :value="s.id" :disabled="!!s.error">{{ s.name }}{{ s.error ? '（不可用）' : '' }}</option></select></label>
            <label>标的<select v-model="base.symbol" required><option v-for="s in catalog?.symbols" :key="s">{{ s }}</option></select></label>
            <label>交易周期<select v-model="base.timeframe"><option v-for="t in availableTimeframes" :key="t">{{ t }}</option></select></label>
            <label>开始时间（UTC，包含）<input v-model="start" type="datetime-local" required /></label><label>结束时间（UTC，不包含）<input v-model="end" type="datetime-local" required /></label>
          </div>
          <p v-if="sourceRun" class="notice mt-3">已继承回测 {{ sourceRun }} 的完整设置。行情范围相同时复用它的行情快照；参数完全相同且代码一致的组合直接复用已有结果。</p>
          <details class="mt-4"><summary>资金、成交精度和数据空档</summary><div class="form-grid mt-3">
            <label>初始资金<input v-model.number="base.initial_cash" type="number" min="0.01" step="any" required /></label><label>每笔使用当时资金 %<input v-model.number="base.position_pct" type="number" min="0.01" max="100" step="any" required /></label>
            <label>用于模拟成交的更小周期<select v-model="execution"><option value="">与交易周期相同</option><option v-for="t in executionFrames" :key="t">{{ t }}</option></select></label>
            <label v-if="execution">细周期缺失或不匹配时<select v-model="base.execution_gap_policy"><option value="reject">停止并报告</option><option value="coarse_fallback">回退主周期并记录</option></select></label>
            <label>缺失行情的处理<select v-model="base.data_gap_policy"><option value="reject">有缺失就停止并报告</option><option value="observed_bars">沿用实际行情，并记录空档</option></select></label>
            <label class="check wide"><input v-model="base.intrabar_profit_protection" type="checkbox" :disabled="!execution" />每根细周期收盘后更新利润保护（需选择更小周期）</label>
          </div><p class="app-muted text-xs mt-2">未勾选的资金和成交设置保持固定，不计交易成本。更小周期必须能整除信号周期。</p></details>
          <div class="parameter-heading"><h3 class="font-semibold">选择要比较的参数</h3><p class="app-muted text-sm">勾选后填多个取值；不勾选的参数保持单个固定值。</p></div>
          <div class="axis-row">
            <label class="check"><input v-model="compareTimeframe" type="checkbox" />同时比较交易周期</label>
            <input v-if="compareTimeframe" v-model="timeframeValues" aria-label="比较的交易周期" placeholder="15m, 30m, 1h" /><span v-else class="app-muted text-sm">固定 {{ base.timeframe }}</span>
          </div>
          <div class="axis-row"><label class="check"><input v-model="comparePosition" type="checkbox" />比较每笔仓位 %</label><input v-if="comparePosition" v-model="positionValues" aria-label="比较的仓位百分比" placeholder="100, 50, 25" /><span v-else class="app-muted text-sm">固定 {{ base.position_pct }}%</span></div>
          <div class="axis-row"><label class="check"><input v-model="compareExecution" type="checkbox" />比较模拟成交周期</label><input v-if="compareExecution" v-model="executionValues" aria-label="比较的成交周期" placeholder="none, 5m, 1m" /><span v-else class="app-muted text-sm">{{ execution || '与信号周期相同' }}</span><small v-if="compareExecution" class="app-muted">none 表示不使用细周期</small></div>
          <div class="axis-row"><label class="check"><input v-model="compareProtection" type="checkbox" />比较利润保护更新方式</label><input v-if="compareProtection" v-model="protectionValues" aria-label="比较的细周期保护设置" placeholder="false, true" /><span v-else class="app-muted text-sm">{{ base.intrabar_profit_protection ? '细周期收盘更新' : '信号周期收盘更新' }}</span><small v-if="compareProtection" class="app-muted">false：信号周期；true：细周期</small></div>
          <p v-if="compareProtection && (compareExecution ? split(executionValues).includes('none') : !execution)" class="notice">细周期保护需要成交周期。包含 none 的组合无法启用细周期保护，检查组合时会报告这个冲突。</p>
          <div v-for="row in rows" :key="row.name" class="axis-row">
            <label class="check"><input v-model="row.enabled" type="checkbox" :disabled="!rowActive(row)" />{{ row.label }} {{ rowSpec(row)?.unit && !row.label.includes(rowSpec(row)!.unit!) ? rowSpec(row)?.unit : "" }}<small v-if="!rowActive(row)">当前设置不使用</small></label>
            <template v-if="row.enabled && rowActive(row)">
              <div v-if="rowOptions(row).length" class="options"><label v-for="o in rowOptions(row)" :key="String(o.value)" class="check"><input type="checkbox" :checked="split(row.values).includes(String(o.value))" @change="toggleOption(row, o.value, ($event.target as HTMLInputElement).checked)" />{{ o.label }}</label></div>
              <select v-else-if="row.type === 'int' || row.type === 'float'" v-model="row.mode" :aria-label="`${row.label} 输入方式`"><option value="list">指定取值</option><option value="range">起止范围</option></select>
              <span v-else class="app-muted text-sm">指定取值</span>
              <div v-if="!rowOptions(row).length && row.mode === 'range'" class="range-fields"><label>起点<input v-model.number="row.start" type="number" step="any" required /></label><label>终点<input v-model.number="row.end" type="number" step="any" required /></label><label>步长<input v-model.number="row.step" type="number" step="any" min="0.000001" required /></label></div>
              <input v-else-if="!rowOptions(row).length" v-model="row.values" :aria-label="`${row.label} 取值`" :placeholder="row.type === 'bool' ? 'true, false' : '例如：34, 55, 89'" required />
            </template>
            <template v-else><select v-if="rowOptions(row).length" v-model="row.value" :disabled="!rowActive(row)" :aria-label="`${row.label} 固定值`"><option v-for="o in rowOptions(row)" :key="String(o.value)" :value="o.value">{{ o.label }}</option></select><select v-else-if="row.type === 'bool'" :disabled="!rowActive(row)" v-model="row.value" :aria-label="`${row.label} 固定值`"><option :value="true">开启</option><option :value="false">关闭</option></select><input v-else v-model="row.value" :disabled="!rowActive(row)" :type="row.type === 'str' ? 'text' : 'number'" :step="row.type === 'int' ? 1 : 'any'" :min="row.min ?? undefined" :max="row.max ?? undefined" :aria-label="`${row.label} 固定值`" required /></template><small v-if="rowSpec(row)?.help" class="app-muted">{{ rowSpec(row)?.help }}</small>
          </div>
          <div class="submit-bar"><div><strong>{{ combinationCount }} 组组合</strong><p class="app-muted text-xs mt-1">{{ varyingCount }} 个参数参与比较，其他参数固定。可先预览，不会下载行情。</p></div><div class="actions"><button type="button" class="app-button-secondary" :disabled="busy || !rows.length" @click="previewRequest">检查组合</button><button class="app-button-primary" :disabled="busy || !rows.length || combinationCount > 512">{{ busy ? '处理中…' : '开始批量回测' }}</button></div></div>
          <p v-if="preview && previewStamp === draftStamp" class="notice mt-3">检查通过：{{ preview.count }} 组，需计算 {{ preview.new_runs }} 组，复用已有结果 {{ preview.reused_runs }} 组。</p>
          <section v-if="preview && previewStamp === draftStamp" class="mt-3 space-y-3">
            <p>全部组合共同有完整预热和本地数据的区间（UTC）：</p><p v-if="!preview.comparable_intervals?.length">暂无完整共同区间；需要先获取缺失行情。</p><p v-for="v in preview.comparable_intervals" :key="v.start_ms">{{ utc(v.start_ms) }} 至 {{ utc(v.end_ms) }}</p>
            <details v-for="v in preview.data_previews" :key="v.case"><summary>{{ v.case }} · {{ v.config.timeframe }} · 预热 {{ v.warmup_bars }} 根 · 查看规则和覆盖</summary><BacktestPreflight :value="v" /></details>
            <p v-for="w in preview.warnings" :key="w" class="app-muted text-xs">{{ w }}</p>
          </section>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BacktestPreflight from '@/components/research/BacktestPreflight.vue'
import { parameterEnabled, parameterValue } from '@/modules/research/strategyParameters'
import ExecutionSummary from '@/components/research/ExecutionSummary.vue'
import { localBacktestApi } from '@/modules/research/localBacktestApi'
import { parameterSweepApi as api } from '@/modules/research/parameterSweepApi'
import { apiErrorMessage } from '@/api/request'
import type { LocalBacktestCatalog, LocalBacktestCommand, ParameterSweepCommand, ParameterSweepPreview, ParameterSweepView, ParameterSweepEffects, ParameterSweepItem, GetParameterSweepQueryParams } from '@/modules/research/generatedContracts'

type Scalar = string | number | boolean
type Row = { name: string; label: string; type: string; value: Scalar; enabled: boolean; mode: 'list' | 'range'; values: string; start: number; end: number; step: number; min?: number | null; max?: number | null }
const route = useRoute(), router = useRouter()
const catalog = ref<LocalBacktestCatalog>(), selected = ref<ParameterSweepView>(), preview = ref<ParameterSweepPreview>(), effects = ref<ParameterSweepEffects>()
const rows = ref<Row[]>([]), history = ref<Record<string, unknown>[]>([]), historyTotal = ref(0), historyOffset = ref(0)
const busy = ref(false), error = ref(''), notice = ref(''), title = ref('ETH 参数比较'), sourceRun = ref<string>(), parent = ref<string>()
const start = ref('2024-09-10T00:00'), end = ref('2026-09-10T00:00'), execution = ref('')
const base = reactive<LocalBacktestCommand>({ strategy: 'trend_cloud_intrabar_methods_v3', parameters: {}, symbol: 'ETH/USDT', timeframe: '15m', start: '', end: '', initial_cash: 10000, position_pct: 100, data_gap_policy: 'reject', intrabar_profit_protection: false, execution_gap_policy: 'reject' })
const compareTimeframe = ref(false), timeframeValues = ref('15m, 30m, 1h'), offset = ref(0), minimumTrades = ref(0), sort = ref<GetParameterSweepQueryParams['sort']>('return_pct')
const comparePosition = ref(false), positionValues = ref('100, 50, 25'), compareExecution = ref(false), executionValues = ref('5m, 1m'), compareProtection = ref(false), protectionValues = ref('false, true')
const previewStamp = ref(''), formSection = ref<HTMLElement>(), resultSection = ref<HTMLElement>()
const strategy = computed(() => catalog.value?.strategies.find(s => s.id === base.strategy))
const availableTimeframes = computed(() => catalog.value?.timeframes[base.symbol ?? 'ETH/USDT'] ?? ['5m', '15m', '30m', '1h', '4h', '1d'])
const minutes: Record<string, number> = { '1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440 }
const executionFrames = computed(() => ['1m', '5m', '15m', '30m', '1h'].filter(t => minutes[t]! < minutes[base.timeframe ?? '15m']!))
const split = (s: string) => [...new Set(s.split(/[,，\s]+/).filter(Boolean))]
const configurationCount = computed(() => (compareTimeframe.value ? split(timeframeValues.value).length : 1) * (comparePosition.value ? split(positionValues.value).length : 1) * (compareExecution.value ? split(executionValues.value).length : 1) * (compareProtection.value ? split(protectionValues.value).length : 1))
const combinationCount = computed(() => rows.value.filter(r => r.enabled && rowActive(r)).reduce((n, r) => n * (r.mode === 'range' ? Math.max(0, Math.floor((r.end - r.start) / r.step + 1e-9) + 1) : split(r.values).length), configurationCount.value))
const varyingCount = computed(() => rows.value.filter(r => r.enabled && rowActive(r)).length + Number(compareTimeframe.value) + Number(comparePosition.value) + Number(compareExecution.value) + Number(compareProtection.value))
const draftStamp = computed(() => JSON.stringify({ title: title.value, base, rows: rows.value, start: start.value, end: end.value, execution: execution.value, tf: [compareTimeframe.value, timeframeValues.value], position: [comparePosition.value, positionValues.value], fills: [compareExecution.value, executionValues.value], protection: [compareProtection.value, protectionValues.value] }))
const statuses: Record<string, string> = { completed: '已完成', running: '计算并记录', saving: '校验与保存', queued: '等待计算', preparing: '准备行情', failed: '失败', interrupted: '已中断', cancelled: '已取消', attention: '有项目待处理', not_submitted: '未提交' }
const status = (s: string) => statuses[s] || s
const countSummary = computed(() => Object.entries(selected.value?.counts ?? {}).map(([k, v]) => `${status(k)} ${v} 组`).join('，'))
const percent = (v: unknown) => typeof v === 'number' ? `${v.toLocaleString('zh-CN', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}%` : '—'
const integer = (v: unknown) => typeof v === 'number' ? v.toLocaleString('zh-CN') : '—'
const tone = (v: unknown) => typeof v === 'number' && v !== 0 ? (v > 0 ? 'positive' : 'negative') : ''
const date = (v: string) => new Date(v).toLocaleString('zh-CN', { hour12: false })
const configurationLabels: Record<string, string> = { timeframe: '信号周期', position_pct: '每笔仓位 %', execution_timeframe: '模拟成交周期', intrabar_profit_protection: '细周期保护' }
const parameterLabel = (name: string) => configurationLabels[name] || selected.value?.strategy?.parameters[name.replace('parameters.', '')]?.label || name.replace('parameters.', '')
const combination = (item: ParameterSweepItem) => Object.keys(selected.value?.axes ?? {}).map(k => { const v = k.startsWith('parameters.') ? item.parameters[k.slice(11)] : item.config?.[k]; return `${parameterLabel(k)} ${k === 'intrabar_profit_protection' ? v ? '开启' : '关闭' : k.startsWith('parameters.') ? parameterValue(selected.value?.strategy?.parameters[k.slice(11)], v) : v ?? '信号周期'}` }).join(' · ') || '固定参数'
const rowSpec = (r: Row) => strategy.value?.parameters[r.name]
const rowOptions = (r: Row) => rowSpec(r)?.options ?? []
const fixedParameters = computed(() => Object.fromEntries(rows.value.map(r => [r.name, r.type === "int" || r.type === "float" ? Number(r.value) : r.value])))
function rowActive(r: Row) {
  const spec = rowSpec(r)
  if (!spec) return true
  if (spec.enabled_when?.some(c => rows.value.some(other => other.name === c.parameter && other.enabled))) return true
  return parameterEnabled(spec, fixedParameters.value)
}
function toggleOption(r: Row, value: unknown, selected: boolean) {
  const values = new Set(split(r.values)); selected ? values.add(String(value)) : values.delete(String(value)); r.values = [...values].join(', '); r.mode = 'list'
}
const utc = (v: number) => new Date(v).toISOString().replace('T', ' ').slice(0, 16)
const effectPairs = (e: Record<string, unknown>) => (e.pairs ?? []) as Record<string, unknown>[]

function resetParameters() {
  rows.value = Object.entries(strategy.value?.parameters ?? {}).map(([name, p]) => ({ name, label: p.label || name, type: p.type, value: p.default as Scalar, enabled: false, mode: 'list', values: p.type === 'bool' ? 'true, false' : String(p.default), start: Number(p.default), end: Number(p.default), step: p.type === 'int' ? 1 : 0.1, min: p.min, max: p.max }))
  sourceRun.value = undefined; preview.value = undefined
}
function scalar(v: Scalar, r: Row): Scalar {
  if (r.type === 'str') return String(v)
  if (r.type === 'bool') { if (v === true || v === 'true') return true; if (v === false || v === 'false') return false; throw Error(`${r.label} 请填 true 或 false`) }
  const n = Number(v)
  if (String(v).trim() === '' || !Number.isFinite(n) || r.type === 'int' && !Number.isInteger(n)) throw Error(`${r.label} 请填有效${r.type === 'int' ? '整数' : '数字'}`)
  return n
}
function request(): ParameterSweepCommand {
  const axes: NonNullable<ParameterSweepCommand['axes']> = {}, parameters: Record<string, Scalar> = {}
  for (const r of rows.value) {
    parameters[r.name] = scalar(r.value, r)
    if (r.enabled && rowActive(r)) axes[`parameters.${r.name}`] = r.mode === 'range' ? { start: Number(r.start), end: Number(r.end), step: Number(r.step) } : split(r.values).map(v => scalar(v, r))
  }
  if (compareTimeframe.value) axes.timeframe = split(timeframeValues.value)
  if (comparePosition.value) axes.position_pct = split(positionValues.value).map(v => { const n = Number(v); if (!Number.isFinite(n) || n <= 0 || n > 100) throw Error('仓位应为大于 0 且不超过 100 的百分比'); return n })
  if (compareExecution.value) axes.execution_timeframe = split(executionValues.value).map(v => v === 'none' ? null : v)
  if (compareProtection.value) axes.intrabar_profit_protection = split(protectionValues.value).map(v => { if (!['false','true'].includes(v)) throw Error('保护更新方式请填写 false、true'); return v === 'true' })
  if (!title.value.trim()) throw Error('请填写记录名称')
  return { title: title.value.trim(), base: { ...base, parameters, start: new Date(`${start.value}Z`).toISOString(), end: new Date(`${end.value}Z`).toISOString(), execution_timeframe: (execution.value || null) as LocalBacktestCommand['execution_timeframe'], intrabar_profit_protection: !!execution.value && base.intrabar_profit_protection }, axes, source_run: sourceRun.value, parent: parent.value, max_runs: 512 }
}
async function guard(fn: () => Promise<unknown>) { error.value = ''; try { await fn() } catch (e) { error.value = apiErrorMessage(e, '操作失败，请检查输入或后台运行状态。') } }
async function job(fn: () => Promise<unknown>) { if (busy.value) return; busy.value = true; await guard(fn); busy.value = false }
async function previewRequest() { await job(async () => { const stamp = draftStamp.value; preview.value = await api.preview(request()); previewStamp.value = stamp }) }
async function submit() { await job(async () => { const v = await api.create(request()); notice.value = '已保存并加入后台队列，可关闭此页面后再回来查看。'; await choose(v.id); await refreshHistory(); await nextTick(); resultSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }) }
async function refreshHistory() { const v = await api.list(historyOffset.value); history.value = v.items; historyTotal.value = v.total }
async function refreshSelected() { const id = selected.value?.id; if (!id) return; const v = await api.get(id, { offset: offset.value, limit: 30, sort: sort.value, descending: sort.value !== 'max_drawdown_pct', minimum_trades: minimumTrades.value }); if (selected.value?.id === id) selected.value = v }
async function choose(id: string) { offset.value = 0; minimumTrades.value = 0; effects.value = undefined; selected.value = await api.get(id); await router.replace({ query: { sweep: id } }) }
async function act(action: 'resume' | 'cancel') { await job(async () => { if (!selected.value) return; await api.action(selected.value.id, action); await refreshSelected(); await refreshHistory() }) }
async function download() { if (!selected.value) return; const file = await api.export(selected.value.id); const url = URL.createObjectURL(new Blob([file.content], { type: file.media_type })); const a = document.createElement('a'); a.href = url; a.download = file.filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }
async function showEffects() { await job(async () => { if (selected.value) effects.value = await api.effects(selected.value.id) }) }
function loadRequest(v: ParameterSweepCommand) {
  Object.assign(base, { intrabar_profit_protection: false, execution_timeframe: null, execution_gap_policy: 'coarse_fallback' }, v.base); resetParameters()
  for (const r of rows.value) {
    if (v.base.parameters && r.name in v.base.parameters) r.value = v.base.parameters[r.name] as Scalar
    const axis = v.axes?.[`parameters.${r.name}`]; r.enabled = !!axis
    if (Array.isArray(axis)) r.values = axis.join(', ')
    else if (axis) { r.mode = 'range'; r.start = axis.start; r.end = axis.end; r.step = axis.step }
    else r.values = String(r.value)
  }
  title.value = v.title; sourceRun.value = v.source_run ?? undefined; parent.value = v.parent ?? undefined
  start.value = new Date(v.base.start).toISOString().slice(0, 16); end.value = new Date(v.base.end).toISOString().slice(0, 16); execution.value = v.base.execution_timeframe ?? ''
  compareTimeframe.value = !!v.axes?.timeframe; if (Array.isArray(v.axes?.timeframe)) timeframeValues.value = v.axes.timeframe.join(', ')
  comparePosition.value = !!v.axes?.position_pct; if (Array.isArray(v.axes?.position_pct)) positionValues.value = v.axes.position_pct.join(', ')
  compareExecution.value = !!v.axes?.execution_timeframe; if (Array.isArray(v.axes?.execution_timeframe)) executionValues.value = v.axes.execution_timeframe.map(x => x ?? 'none').join(', ')
  compareProtection.value = !!v.axes?.intrabar_profit_protection; if (Array.isArray(v.axes?.intrabar_profit_protection)) protectionValues.value = v.axes.intrabar_profit_protection.join(', ')
}
function copyVersion() { if (!selected.value) return; loadRequest({ ...selected.value.request, axes: selected.value.axes, title: `${selected.value.title} · 新版`, parent: selected.value.id }); notice.value = '已把旧设置复制到下方。修改后点击开始，会新建记录，旧版保留。'; formSection.value?.scrollIntoView({ behavior: 'smooth' }) }
let timer: ReturnType<typeof setTimeout> | undefined, disposed = false
async function poll() { if (disposed) return; if (!busy.value && selected.value?.status === 'running') await guard(async () => { await refreshSelected(); await refreshHistory() }); if (!disposed) timer = setTimeout(poll, 4000) }
onMounted(async () => { await guard(async () => { catalog.value = await localBacktestApi.catalog(); if (!strategy.value) base.strategy = catalog.value.strategies.find(s => !s.error)?.id ?? ''; resetParameters(); await refreshHistory(); if (typeof route.query.base_run === 'string') { const run = await localBacktestApi.get(route.query.base_run); loadRequest({ title: `${run.config.symbol} ${run.config.timeframe} 参数比较`, base: run.config as unknown as LocalBacktestCommand, source_run: run.id, axes: {} }) } else if (typeof route.query.sweep === 'string') await choose(route.query.sweep) }); void poll() })
onUnmounted(() => { disposed = true; if (timer) clearTimeout(timer) })
</script>

<style scoped>
.options{display:flex;flex-wrap:wrap;gap:12px}.options label{font-size:13px}input:disabled,select:disabled{opacity:.5}

.sweeps{max-width:1600px;margin:auto}.page-head,.actions{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}.actions{justify-content:flex-end;align-items:center}.layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:20px;margin-top:24px}.section,.history{padding:24px}.history{align-self:start;padding:18px;position:sticky;top:12px}.history-item{text-align:left;display:grid;gap:5px;padding:14px 8px;border-bottom:1px solid #8883;width:100%;border-radius:6px}.history-item span,.history-item small{opacity:.65}.history-item.active{background:#5688ed18}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.wide{grid-column:1/-1}label{display:flex;flex-direction:column;gap:7px;font-size:13px}input,select{background:transparent;color:inherit;border:1px solid #8885;border-radius:7px;padding:9px 11px;min-width:0;width:100%}select option{background:var(--app-bg,#fff);color:var(--app-text,#20232a)}input[type=checkbox]{width:16px;height:16px;flex:none;accent-color:#477de6}.check{display:flex;flex-direction:row;align-items:center;gap:9px}.parameter-heading{margin:26px 0 12px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}.axis-row{display:grid;grid-template-columns:minmax(220px,1fr) 150px minmax(180px,1fr);gap:12px;align-items:center;padding:10px 0;border-top:1px solid #8882}.range-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.range-fields label{font-size:11px}.submit-bar{display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap;margin-top:24px;border-top:1px solid #8883;padding-top:20px}.filters{display:flex;gap:16px;align-items:end;flex-wrap:wrap;margin:24px 0 16px}.filters input{max-width:130px}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:13px 10px;border-bottom:1px solid #8883;white-space:nowrap}th{font-weight:500;opacity:.65}.combination{white-space:normal;min-width:190px;max-width:320px;line-height:1.65}.pager{display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:12px;margin-top:16px}.pager button:disabled{opacity:.3}.error{color:#d95055;background:#d950550c;border-radius:6px;padding:10px;margin-top:12px}.cell-error{white-space:normal;max-width:250px;font-size:12px}.notice{color:#487fd7;background:#5688ed10;border-radius:6px;padding:12px;font-size:13px}.positive{color:#168468}.negative{color:#d25355}.link{color:#487fd7;text-decoration:underline;text-underline-offset:4px}pre{max-height:320px;overflow:auto;font-size:12px;background:#8881;padding:14px;border-radius:8px}.local-path{overflow-wrap:anywhere;font-size:12px}.effect-panel{margin-top:24px;border-top:1px solid #8883;padding-top:20px}.badge{font-size:12px;border:1px solid #8884;padding:5px 9px;border-radius:20px}progress{accent-color:#477de6;height:7px}summary{cursor:pointer;font-size:13px}button:disabled{opacity:.5;cursor:default}@media(max-width:1150px){.layout{grid-template-columns:1fr}.history{position:static;max-height:260px;overflow:auto}.axis-row{grid-template-columns:minmax(180px,1fr) 130px minmax(150px,1fr)}}@media(max-width:700px){.section{padding:16px}.form-grid{grid-template-columns:1fr}.axis-row{grid-template-columns:1fr 1fr}.axis-row>label{grid-column:1/-1}.axis-row>input:last-child,.range-fields{grid-column:1/-1}.submit-bar{align-items:stretch}.filters{gap:10px}}
</style>
