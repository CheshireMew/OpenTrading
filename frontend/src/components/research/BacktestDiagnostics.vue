<template>
  <section class="app-panel p-5 diagnostics">
    <div class="controls"><h3 class="font-semibold">账户与交易诊断</h3><label>统计曲线<select v-model="equityKind"><option value="equity">信号周期收盘权益</option><option value="execution_equity">实际成交周期收盘权益</option></select></label><button class="app-button-secondary" :disabled="busy" @click="load">{{ busy ? '读取保存记录…' : '读取诊断' }}</button></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="summary">
      <p class="app-muted text-sm my-3">{{ summary.account_basis }}</p>
      <div class="stat-grid"><p>最长连续亏损<strong>{{ summary.trade_summary.max_consecutive_losses }} 笔</strong></p><p>等额本金毛利<strong>{{ number(summary.normalized.gross_profit) }}</strong></p><p>等额本金毛亏<strong>{{ number(summary.normalized.gross_loss) }}</strong></p><p>最大 10 笔盈利占毛利<strong>{{ percent(summary.normalized.top_10_gross_profit_share_pct) }}</strong></p></div>
      <p class="app-muted text-xs my-3">{{ summary.normalized.basis }} 每笔换算本金 {{ number(summary.normalized.principal_per_trade) }}；毛亏显示为正的损失金额。</p>
      <template v-if="summary.available">
        <div class="controls"><h4 class="font-semibold">连续账户收益</h4><label>分组<select v-model="calendar"><option value="annual">按年</option><option value="monthly">按月</option></select></label></div>
        <div class="table-scroll"><table><thead><tr><th>期间（UTC）</th><th>期初权益</th><th>期末权益</th><th>期间收益</th><th>边界记录</th></tr></thead><tbody><tr v-for="p in summary[calendar]" :key="p.label"><td>{{ p.label }}{{ p.partial ? '（非完整期间）' : '' }}</td><td>{{ number(p.start_equity) }}</td><td>{{ number(p.end_equity) }}</td><td>{{ percent(p.return_pct) }}</td><td :title="`期初记录 ${date(p.start_mark_time)}；期末记录 ${date(p.end_mark_time)}`">{{ p.boundary_carried ? '沿用边界前权益，悬停查看时间' : '边界有权益记录' }}</td></tr></tbody></table></div>
        <h4 class="font-semibold mt-5">主要回撤过程</h4><p class="app-muted text-xs my-2">{{ summary.drawdown.basis }} 共 {{ summary.drawdown.total_episodes }} 段，显示幅度最大的 20 段。</p>
        <p v-if="summary.drawdown.longest" class="text-sm">最长回撤持续 {{ days(summary.drawdown.longest.duration_ms) }} 天{{ summary.drawdown.longest.recovered ? '，已恢复' : '，截至结束仍未恢复' }}。</p>
        <div class="table-scroll"><table><thead><tr><th>回撤起点 UTC</th><th>谷底 UTC</th><th>幅度</th><th>恢复 UTC</th><th>持续天数</th></tr></thead><tbody><tr v-for="p in summary.drawdown.worst_episodes" :key="p.peak_time"><td>{{ date(p.peak_time) }}</td><td>{{ date(p.trough_time) }}</td><td>{{ number(p.drawdown_pct) }}%</td><td>{{ p.recovered ? date(p.recovery_time) : '结束时未恢复' }}</td><td>{{ days(p.duration_ms) }}</td></tr></tbody></table></div>
      </template>
      <details class="my-4"><summary>按退出原因和方向查看已实现盈亏贡献</summary><p class="app-muted text-xs my-2">{{ summary.basis }}</p><div v-for="group in ['exit_reason','side']" :key="group" class="table-scroll"><table><thead><tr><th>{{ group === 'side' ? '方向' : '退出原因' }}</th><th>交易次数</th><th>毛利</th><th>毛亏</th><th>利润因子</th></tr></thead><tbody><tr v-for="(v, label) in summary.groups[group]" :key="label"><td>{{ group === 'exit_reason' ? exitReason(label) : names[String(label)] || label }}</td><td>{{ v.trades }}</td><td>{{ number(v.gross_profit) }}</td><td>{{ number(v.gross_loss) }}</td><td>{{ number(v.profit_factor) }}</td></tr></tbody></table></div></details>
    </template>
    <details class="mt-5"><summary>比较另一版增加、减少或改变的交易</summary><form class="controls my-3" @submit.prevent="changeOffset = 0; compare()"><label>对照运行编号<input v-model.trim="otherId" placeholder="另一份已完成回测的运行编号" required /></label><button class="app-button-secondary" :disabled="busy || !otherId || otherId === runId">读取交易差异</button></form>
      <template v-if="changes"><p class="app-muted text-sm">{{ changes.note }}</p><p v-if="changes.comparison.issues?.length" class="notice">本次为描述性比较：{{ changes.comparison.issues.join('；') }}</p><p class="my-3 text-sm">减少 {{ changes.dropped.trades }} 笔（{{ changes.dropped.wins }} 笔盈利、{{ changes.dropped.losses }} 笔亏损），新增 {{ changes.added.trades }} 笔，改变 {{ changes.changed }} 笔，成交路径相同 {{ changes.unchanged }} 笔。</p><p class="text-sm mb-3">按每笔等额本金 {{ number(changes.dropped.principal_per_trade) }} 换算：减少交易同时避开毛亏 {{ number(changes.dropped.gross_loss) }}、失去毛利 {{ number(changes.dropped.gross_profit) }}；新增交易产生毛利 {{ number(changes.added.gross_profit) }}、毛亏 {{ number(changes.added.gross_loss) }}。</p>
        <div class="table-scroll"><table><thead><tr><th>变化</th><th>开仓 UTC</th><th>方向</th><th>原交易收益</th><th>对照收益</th><th>改变内容</th></tr></thead><tbody><tr v-for="(c, i) in changes.items" :key="i"><td>{{ names[c.kind] }}</td><td>{{ date(c.entry_time) }}</td><td>{{ names[c.side] }}</td><td>{{ percent(c.before?.return_pct) }}</td><td>{{ percent(c.after?.return_pct) }}</td><td>{{ c.changed_fields.map((f: string) => names[f] || f).join('、') }}</td></tr></tbody></table></div>
        <div class="pager"><button :disabled="busy || !changeOffset" @click="changeOffset -= 100; compare()">上一页</button><span>{{ changeOffset + changes.items.length }} / {{ changes.total }}</span><button :disabled="busy || changeOffset + 100 >= changes.total" @click="changeOffset += 100; compare()">下一页</button></div>
      </template>
    </details>
  </section>
</template>

<script setup lang="ts">
import { exitReason } from '@/modules/research/tradePresentation'
import { ref, watch } from 'vue'
import { localBacktestApi as api } from '@/modules/research/localBacktestApi'
import type { BacktestDiagnosticSummary, BacktestTradeChanges } from '@/modules/research/generatedContracts'
const props = defineProps<{ runId: string }>()
const summary = ref<BacktestDiagnosticSummary | null>(null), changes = ref<BacktestTradeChanges | null>(null)
const equityKind = ref<'equity' | 'execution_equity'>('equity'), calendar = ref<'annual' | 'monthly'>('annual')
const busy = ref(false), error = ref(''), otherId = ref(''), changeOffset = ref(0)
let request = 0
const number = (v: unknown) => typeof v === 'number' ? (v === 0 ? 0 : v).toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'
const percent = (v: unknown) => typeof v === 'number' ? `${number(v)}%` : '—'
const date = (v: unknown) => typeof v === 'number' ? new Date(v).toISOString().replace('T',' ').slice(0,19) : '—'
const days = (v: unknown) => typeof v === 'number' ? number(v/86400000) : '—'
const names: Record<string,string> = { long: '多仓', short: '空仓', signal: '反向信号', reversal: '反向信号', stop: '止损', target: '止盈', protection: '利润保护', end: '区间结束', added: '新增', dropped: '减少', changed: '改变', entry_price:'开仓价格', exit_time:'退出时间', exit_phase:'退出阶段', exit_price:'退出价格', exit_reason:'退出原因', return_pct:'交易收益率', entry_ambiguity_policy:'入场顺序假设' }
async function load() { const token=++request, id=props.runId; busy.value=true; error.value=''; try { const r=await api.diagnostics(id,equityKind.value); if(token===request) summary.value=r } catch(e) { if(token===request) error.value=String(e) } finally { if(token===request) busy.value=false } }
async function compare() { const token=++request, id=props.runId; busy.value=true; error.value=''; try { const r=await api.tradeChanges(id,otherId.value,changeOffset.value); if(token===request) changes.value=r } catch(e) { if(token===request) error.value=String(e) } finally { if(token===request) busy.value=false } }
watch(() => props.runId, () => { request++; summary.value=null; changes.value=null; error.value=''; busy.value=false; changeOffset.value=0 })
watch(equityKind, () => { request++; summary.value=null; busy.value=false })
</script>

<style scoped>
.controls{display:flex;align-items:center;gap:16px;flex-wrap:wrap}label{font-size:13px}input,select{display:block;border:1px solid #8884;border-radius:6px;padding:8px;background:transparent;color:inherit;margin-top:6px}input{min-width:320px}.stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;font-size:13px}.stat-grid strong{display:block;font-size:20px;margin-top:6px}.table-scroll{overflow:auto;max-height:380px;margin-top:12px}table{width:100%;font-size:12px;text-align:left;white-space:nowrap}td,th{padding:10px;border-bottom:1px solid #8883}.error,.notice{font-size:13px;padding:12px;background:#8881;margin-top:12px;overflow-wrap:anywhere}.error{color:#d55}.pager{display:flex;justify-content:space-between;gap:12px;font-size:12px;margin-top:12px}button:disabled{opacity:.5;cursor:not-allowed}summary{cursor:pointer;font-size:14px}@media(max-width:900px){.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}input{min-width:180px}}
</style>
