<template>
  <main class="results-page">
    <div class="heading"><h1 class="text-2xl font-semibold">研究结果目录</h1><button class="app-button-secondary" :disabled="busy" @click="refreshImports">更新旧资料索引</button></div>
    <p v-if="message" class="notice" role="status">{{ message }}</p><p v-if="error" class="error" role="alert">{{ error }}</p>
    <form class="app-panel filters" @submit.prevent="search(true)">
      <label>标的<input v-model.trim="symbol" placeholder="例如 ETH/USDT" /></label>
      <label>策略标识<input v-model.trim="strategy" placeholder="留空查询全部策略" /></label>
      <label>策略系列<input v-model.trim="family" placeholder="例如 EMA 通道" /></label>
      <label>信号周期<select v-model="timeframe"><option value="">全部</option><option v-for="t in frames" :key="t">{{ t }}</option></select></label>
      <label>区间起点（UTC）<input v-model="start" type="datetime-local" /></label><label>区间终点（UTC）<input v-model="end" type="datetime-local" /></label>
      <label>成交周期<select v-model="executionTimeframe"><option value="">全部</option><option value="none">信号周期成交</option><option v-for="t in frames" :key="t">{{ t }}</option></select></label>
      <label>保护更新<select v-model="protection"><option value="">全部</option><option value="signal">信号周期收盘</option><option value="execution">细周期收盘</option></select></label>
      <label class="parameter-filter">参数精确匹配（JSON）<input v-model="parameters" placeholder='例如 {"center_length":55,"width_length":31}' /></label>
      <label>排序<select v-model="sort"><option value="return_pct">收益率从高到低</option><option value="win_rate">胜率从高到低</option><option value="max_drawdown_pct">回撤从小到大</option><option value="total_trades">交易次数从多到少</option></select></label>
      <label>至少交易笔数<input v-model.number="minimumTrades" type="number" min="0" step="1" /></label>
      <label class="checkbox"><input v-model="includeArchived" type="checkbox" />包括归档结果</label><button class="app-button-primary" :disabled="busy" type="submit">{{ busy ? '读取中…' : '查询已有结果' }}</button>
    </form>
    <div class="scope"><strong>{{ reference ? '同条件排序' : '历史记录排序' }}</strong><span v-if="reference">参照：{{ reference.label }}</span><button v-if="reference" class="app-button-secondary" :disabled="busy" @click="reference = null; search(true)">返回历史排序</button><p class="app-muted">{{ page?.note }}</p></div>
    <section class="app-panel">
      <div class="table-scroll"><table><thead><tr><th>结果 / 来源</th><th>标的 / 周期</th><th>测试区间（UTC）</th><th>收益率</th><th>最大回撤</th><th>胜率 / 笔数</th><th>版本证据</th></tr></thead>
        <tbody><tr v-for="item in page?.items" :key="item.id" :class="{ selected: selected?.id === item.id }"><td><button class="entry-link" @click="select(item)">{{ item.label }}</button><small>{{ item.source_type === 'native' ? '本地运行' : '旧研究汇总' }}{{ item.archived ? ' · 已归档' : '' }} · {{ item.family || '系列未登记' }}</small></td><td>{{ item.config.symbol || '未记录' }}<small>{{ item.config.timeframe || '未知周期' }} · {{ item.config.execution_timeframe ? `${item.config.execution_timeframe} 成交` : '成交周期见详情' }}</small></td><td>{{ date(item.config.start) }}<small>至 {{ date(item.config.end) }}</small></td><td>{{ percent(item.report.return_pct) }}</td><td>{{ percent(item.report.max_drawdown_pct) }}</td><td>{{ percent(item.report.win_rate) }}<small>{{ item.report.total_trades ?? '—' }} 笔</small></td><td>{{ item.cohort ? '可按同条件筛选' : '证据不全' }}</td></tr></tbody>
      </table></div><p v-if="page && !page.items.length" class="app-muted py-5">没有匹配结果。旧资料首次使用时，请更新索引。</p>
      <div class="pager"><button :disabled="busy || offset === 0" @click="offset -= 30; search()">上一页</button><span>{{ page?.total ? offset + 1 : 0 }}–{{ offset + (page?.items.length ?? 0) }} / {{ page?.total ?? 0 }}</span><button :disabled="busy || offset + 30 >= (page?.total ?? 0)" @click="offset += 30; search()">下一页</button></div>
    </section>
    <section v-if="selected" class="app-panel detail">
      <div class="heading"><h2 class="text-lg font-semibold">{{ selected.label }}</h2><div class="actions"><RouterLink v-if="selected.run_id" :to="{ path: '/research/backtests', query: { run: selected.run_id } }" class="app-button-primary">打开回测详情</RouterLink><button class="app-button-secondary" :disabled="busy || !selected.cohort" @click="compareConditions">查看同条件结果</button><button class="app-button-secondary" @click="download">导出这条记录</button></div></div>
      <p v-if="selected.context_note" class="app-muted my-3">{{ selected.context_note }}</p>
      <ExecutionSummary :config="selected.config" :summary="selected.execution_summary" completed />
      <p v-if="selected.missing.length" class="notice">下列内容缺少记录，不能确认同条件：{{ selected.missing.map(name => evidenceNames[name] || name).join('、') }}</p>
      <details class="my-3" open><summary>本次保存的配置与参数</summary><pre>{{ JSON.stringify(selected.config, null, 2) }}</pre></details>
      <h3 class="font-semibold mt-4">来源位置</h3><p class="app-muted text-sm my-2">校验值用于核对导入时的文件。旧资料变更后需重新更新索引。</p>
      <div v-for="(source, i) in selected.sources" :key="i" class="source"><p>{{ source.path }} · {{ source.pointer }}</p><small>{{ source.exists ? (source.unchanged === false ? '文件已经变化，请重新导入' : source.unchanged === true ? '已核对，内容未变化' : '文件存在') : '来源文件缺失' }}</small><code v-if="source.sha256_at_import">SHA-256 {{ source.sha256_at_import }}</code></div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import ExecutionSummary from '@/components/research/ExecutionSummary.vue'
import { researchResultsApi as api } from '@/modules/research/researchResultsApi'
import type { ResearchResultEntry, ResearchResultPage, ResearchResultQuery } from '@/modules/research/generatedContracts'

const frames = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
const evidenceNames: Record<string, string> = { 'config.strategy': '策略', 'config.symbol': '标的', 'config.timeframe': '信号周期', 'config.start': '起点', 'config.end': '终点', 'config.initial_cash': '初始资金', 'config.position_pct': '仓位', 'config.execution_timeframe': '成交周期', 'config.intrabar_profit_protection': '保护更新方式', 'config.data_gap_policy': '主行情缺口处理', 'config.execution_gap_policy': '细行情缺口处理', 'config.parameters': '完整参数', 'metadata.source': '数据来源', 'metadata.environment': '运行环境', 'metadata.strategy_hash': '策略版本', 'metadata.data_hash': '主行情版本', 'metadata.execution_data_hash': '细行情版本', 'metadata.execution_alignment_hash': '细周期对齐证据', 'metadata.execution_bundle': '完整执行依赖', 'metadata.warmup_bars': '预热设置' }
const symbol = ref(''), strategy = ref(''), family = ref(''), timeframe = ref(''), start = ref(''), end = ref('')
const executionTimeframe = ref(''), protection = ref(''), parameters = ref(''), minimumTrades = ref(0), includeArchived = ref(false)
const sort = ref<NonNullable<ResearchResultQuery['sort']>>('return_pct'), offset = ref(0), busy = ref(false), error = ref(''), message = ref('')
const page = ref<ResearchResultPage | null>(null), selected = ref<ResearchResultEntry | null>(null), reference = ref<ResearchResultEntry | null>(null)
const percent = (value: unknown) => typeof value === 'number' ? `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%` : '—'
const date = (value: unknown) => typeof value === 'string' ? value.replace('T', ' ').replace('+00:00', '').replace('Z', '') : '未记录'
async function guard(task: () => Promise<void>) { busy.value = true; error.value = ''; try { await task() } catch (e) { error.value = e instanceof Error ? e.message : String(e) } finally { busy.value = false } }
async function search(reset = false) { await guard(async () => {
  const params: unknown = parameters.value.trim() ? JSON.parse(parameters.value) : {}
  if (!params || Array.isArray(params) || typeof params !== 'object') throw new Error('参数应为 JSON 对象，例如 {"center_length":55}')
  if (reset) offset.value = 0
  page.value = await api.query({ symbol: symbol.value || null, strategy: strategy.value || null, family: family.value || null,
    timeframe: timeframe.value || null, start: start.value ? new Date(`${start.value}Z`).toISOString() : null, end: end.value ? new Date(`${end.value}Z`).toISOString() : null,
    execution_timeframe: executionTimeframe.value || null, intrabar_profit_protection: protection.value ? protection.value === 'execution' : null,
    parameters: params as Record<string, unknown>, reference_id: reference.value?.id ?? null, sort: sort.value,
    descending: sort.value !== 'max_drawdown_pct', minimum_trades: minimumTrades.value, include_archived: includeArchived.value, offset: offset.value, limit: 30 })
}) }
async function select(item: ResearchResultEntry) { await guard(async () => { selected.value = await api.get(item.id) }) }
async function compareConditions() { reference.value = selected.value; await search(true) }
async function refreshImports() {
  await guard(async () => { const r = await api.refresh(); message.value = `已登记 ${r.native_runs} 次本地运行，处理 ${r.imported_references} 条旧资料引用。${r.issues.length ? `${r.issues.length} 个文件需核对：${r.issues.slice(0, 5).map(i => `${i.path}：${i.issue}`).join('；')}` : '来源检查完成。'}` })
  if (!error.value) await search(true)
}
function download() { const url = URL.createObjectURL(new Blob([JSON.stringify(selected.value, null, 2)], { type: 'application/json;charset=utf-8' })); const a = document.createElement('a'); a.href = url; a.download = `${selected.value?.id.replace(':', '-')}.json`; a.click(); URL.revokeObjectURL(url) }
onMounted(() => search())
</script>

<style scoped>
.results-page{max-width:1800px;margin:auto;padding:24px}.heading,.actions{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:24px;padding:20px}.parameter-filter{grid-column:span 2}label{font-size:13px}input:not([type=checkbox]),select{display:block;width:100%;padding:9px 11px;border:1px solid var(--app-border,#d1d5db);border-radius:8px;background:transparent;color:inherit;margin-top:6px}.checkbox{display:flex;align-items:center;gap:8px}.scope{margin:20px 0;display:flex;align-items:center;gap:12px;flex-wrap:wrap}.scope p{width:100%;font-size:13px}.table-scroll{overflow:auto}table{width:100%;font-size:13px;text-align:left}td,th{padding:12px;white-space:nowrap;border-bottom:1px solid #8883}td:first-child{max-width:350px;white-space:normal}.entry-link{color:#0e9d79;text-align:left;text-decoration:underline;text-underline-offset:3px}small{display:block;font-size:11px;opacity:.75;margin-top:5px}.selected{background:#14b88a10}.pager{display:flex;justify-content:space-between;padding:15px;gap:12px}.pager button{border:1px solid #8884;border-radius:6px;padding:6px 10px}.detail{padding:24px;margin-top:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:#8881;font-size:12px}.notice,.error{padding:12px;margin-top:12px;border-radius:8px;background:#8881;overflow-wrap:anywhere}.error{color:#dc5656;background:#e85c5c15}.source{margin-top:14px;font-size:12px;overflow-wrap:anywhere}.source code{display:block;margin-top:4px;font-size:11px}button:disabled{opacity:.5;cursor:not-allowed}summary{cursor:pointer}@media(max-width:1000px){.filters{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.results-page{padding:16px}.filters{grid-template-columns:1fr}.parameter-filter{grid-column:auto}}
</style>
