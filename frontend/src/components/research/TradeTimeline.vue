<template>
  <div class="timeline mt-4"><button class="app-button-secondary" :disabled="busy" @click="offset = 0; load()">{{ busy ? '读取过程…' : `查看第 ${tradeId} 笔交易过程` }}</button><p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="timeline"><p class="app-muted text-xs my-3">{{ timeline.basis }}</p><p v-for="message in timeline.limitations" :key="message" class="notice">{{ message }}</p><p v-if="timeline.fallback_intervals?.length" class="text-sm my-2">回退主周期的区间起点：{{ timeline.fallback_intervals.map(date).join('、') }}</p>
      <details v-if="timeline.signals.length" class="my-3"><summary>关联原信号</summary><pre>{{ JSON.stringify(timeline.signals, null, 2) }}</pre></details>
      <div class="table-scroll"><table><thead><tr><th>时间 UTC</th><th>事件</th><th>保存的执行信息</th></tr></thead><tbody><tr v-for="(e,i) in timeline.items" :key="i"><td>{{ date(e.timestamp) }}</td><td>{{ names[String(e.event)] || e.event }}</td><td>{{ detail(e) }}<details><summary>完整记录</summary><pre>{{ JSON.stringify(e,null,2) }}</pre></details></td></tr></tbody></table></div>
      <div class="pager"><button :disabled="busy || !offset" @click="offset -= 100; load()">上一页</button><span>{{ offset + timeline.items.length }} / {{ timeline.total }}</span><button :disabled="busy || offset + 100 >= timeline.total" @click="offset += 100; load()">下一页</button></div>
    </template>
  </div>
</template>
<script setup lang="ts">
import { signalStatus, exitReason } from '@/modules/research/tradePresentation'
import { ref, watch } from 'vue'
import { localBacktestApi as api } from '@/modules/research/localBacktestApi'
import type { BacktestTradeTimeline } from '@/modules/research/generatedContracts'
const props=defineProps<{runId:string;tradeId:number}>()
const timeline=ref<BacktestTradeTimeline|null>(null),error=ref(''),busy=ref(false),offset=ref(0)
let request=0
const names:Record<string,string>={signal:'产生信号',stop_entry_order:'建立突破委托',order_checked:'检查委托条件',signal_processed:'处理信号',entry:'开仓成交',exit:'退出成交',protection_updated:'更新利润保护',saved_fill:'已保存成交',strategy_observation:'决策时的指标条件'}
const date=(v:unknown)=>typeof v==='number'?new Date(v).toISOString().replace('T',' ').slice(0,19):'—'
function detail(e:Record<string,any>) { if(e.event === 'strategy_observation') return [...Object.entries(e.values ?? {}).filter(([,v])=>v != null).map(([k,v])=>`${k}：${['确认起点时间','最初信号时间'].includes(k) && typeof v === 'number' ? date(v) : v}`), ...Object.entries(e.checks ?? {}).map(([k,v])=>`${k}：${v ? '是' : '否'}`)].join('；'); return [e.price!=null?`价格 ${e.price}`:'',e.stop!=null?`止损价 ${e.stop}`:'',e.effective_from!=null?`生效于 ${date(e.effective_from)}`:'',e.status?`状态 ${signalStatus(e.status)}`:'',e.reason?`原因 ${exitReason(e.reason)}`:'',e.trigger_price!=null?`突破价 ${e.trigger_price}`:'',e.worst_price!=null?`追价上限 ${e.worst_price}`:'',e.resolution_ms?`行情间隔 ${e.resolution_ms/60000} 分钟`:'',e.fallback?'本区间回退主周期':''].filter(Boolean).join('；') }
async function load(){const token=++request;busy.value=true;error.value='';try{const r=await api.tradeTimeline(props.runId,props.tradeId,offset.value);if(token===request)timeline.value=r}catch(e){if(token===request)error.value=String(e)}finally{if(token===request)busy.value=false}}
watch(()=>[props.runId,props.tradeId],()=>{request++;timeline.value=null;offset.value=0;busy.value=false;error.value=''})
</script>
<style scoped>
.table-scroll{overflow:auto;max-height:400px}table{width:100%;font-size:12px;text-align:left}td,th{padding:9px;border-bottom:1px solid #8883;vertical-align:top}td:first-child{white-space:nowrap}pre{font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;max-width:700px}.pager{display:flex;justify-content:space-between;margin-top:12px;font-size:12px}.notice,.error{font-size:13px;background:#8881;padding:12px;margin-top:12px}.error{color:#d55}summary{cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}
</style>
