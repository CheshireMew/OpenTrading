<template>
  <div class="tester">
    <div class="tester-controls">
      <strong>策略测试器</strong><span>{{ symbol?.name }} · {{ timeframe }}</span>
      <label>开始 <input type="datetime-local" v-model="start" /></label><label>结束 <input type="datetime-local" v-model="end" /></label>
      <button :disabled="busy||!script||declaration!=='strategy'" @click="run">运行策略</button>
      <button v-if="selected&&running" @click="cancel">取消</button>
      <button v-if="selected&&!running" @click="rerun">用原快照重跑</button>
      <select aria-label="历史回测" v-model="selectedId" @change="loadSelected"><option value="">历史回测</option><option v-for="item in runs" :key="item.id" :value="item.id">{{ stamp(item.created_at) }} · {{ statusText(item.status) }}</option></select>
    </div>
    <details class="effective-config"><summary>本次生效参数 · {{ script?.name }} v{{ script?.version }} · {{ declaration==='strategy'?'策略':declaration==='indicator'?'指标不能回测':'正在解析' }}</summary><dl><template v-for="item in effectiveConfig" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ item.value }} <small>{{ item.origin }}</small></dd></template></dl></details>
    <div class="tester-properties">
      <label>初始资金 <input type="number" v-model="capital" placeholder="采用脚本声明" min="1" /></label>
      <label>仓位方式 <select v-model="qtyType"><option value="">采用脚本声明</option><option value="fixed">固定数量</option><option value="percent_of_equity">权益百分比</option><option value="cash">固定金额</option></select></label>
      <label>数量 <input type="number" v-model="quantity" placeholder="采用脚本声明" min="0" /></label>
      <label>手续费 % <input type="number" v-model="commission" placeholder="采用脚本声明" min="0" step="0.01" /></label>
      <label>滑点（跳） <input type="number" v-model="slippage" placeholder="采用脚本声明" min="0" /></label>
      <button @click="showInputs=!showInputs">脚本输入参数</button>
    </div>
    <div v-if="showInputs" class="tester-inputs"><label v-for="field in inputFields" :key="field.title" :title="field.tooltip">{{ field.title }}
      <input v-if="field.type==='bool'" type="checkbox" v-model="inputs[field.title]" />
      <select v-else-if="field.options" v-model="inputs[field.title]"><option v-for="option in field.options" :key="String(option)" :value="option">{{ option }}</option></select>
      <input v-else v-model="inputs[field.title]" :type="['int','float','price','time'].includes(field.type)?'number':'text'" :step="field.step??'any'" />
    </label></div>
    <p v-if="error" role="alert" class="cw-error">{{ error }}</p>
    <div v-if="selected" class="run-status">{{ statusText(selected.status) }} <progress v-if="running" :value="selected.progress" max="100" /> {{ running?Math.round(selected.progress??0)+'%':'' }} <span v-if="selected.error" class="cw-error">{{ selected.error }}</span></div>
    <div v-if="selected?.status==='completed'" class="tester-result">
      <div class="result-metrics"><div v-for="metric in metrics" :key="metric.label"><small>{{ metric.label }}</small><strong>{{ metric.value }}</strong></div></div>
      <nav><button v-for="tab in tabs" :key="tab.key" :class="{active:tab.key===recordKind}" @click="selectRecords(tab.key)">{{ tab.label }}</button></nav>
      <div v-if="recordKind==='equity'" ref="equityHost" class="equity-chart" />
      <div v-else class="record-table"><table><thead><tr><th v-for="col in columns" :key="col.key">{{ col.label }}</th></tr></thead><tbody><tr v-for="(row,index) in records" :key="index" @click="locate(row)"><td v-for="col in columns" :key="col.key">{{ formatCell(row[col.key],col.key) }}</td></tr></tbody></table></div>
      <footer><button :disabled="offset===0" @click="page(-1)">上一页</button><span>{{ offset+1 }}–{{ Math.min(offset+records.length,total) }} / {{ total }}</span><button :disabled="offset+records.length>=total" @click="page(1)">下一页</button><details><summary>实际配置与数据来源</summary><pre>{{ JSON.stringify({config:selected.summary?.config,...selected.provenance},null,2) }}</pre></details></footer>
    </div>
    <p v-else-if="!selected" class="tester-empty">选择 strategy() 脚本后运行。指标中的买卖标签不作为策略成交记录。结果保存在本工作台。</p>
  </div>
</template>
<script setup lang="ts">
import { computed,nextTick,onBeforeUnmount,onMounted,ref,watch } from 'vue'
import { createChart,LineSeries, type IChartApi, type UTCTimestamp } from 'lightweight-charts'
import { readPineMetadata } from '@/modules/chartWorkspace/pineEngine'
import { chartApi, type ChartSymbol,type WorkspaceDocument,type PineRun } from '@/modules/chartWorkspace/api'
import { checkPine } from '@/modules/chartWorkspace/pineCompatibility.mjs'
const props=defineProps<{symbol?:ChartSymbol;timeframe:string;script?:WorkspaceDocument;dark:boolean}>()
const emit=defineEmits<{locate:[{time:number;run:PineRun}];log:[string]}>()
const localDate=(d:Date)=>new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)
const start=ref(localDate(new Date(Date.now()-30*86400000))),end=ref(localDate(new Date()))
const capital=ref(''),quantity=ref(''),qtyType=ref(''),commission=ref(''),slippage=ref('')
const inputs=ref<Record<string,any>>({}),inputFields=ref<any[]>([]),showInputs=ref(false)
const declaration=ref(''),declarationProps=ref<Record<string,any>>({})
let metadataTask:ReturnType<typeof readPineMetadata>|undefined
const overrides=computed(()=>{
  const values:Record<string,any>={}
  if(capital.value!=='')values.initial_capital=Number(capital.value)
  if(quantity.value!=='')values.default_qty_value=Number(quantity.value)
  if(qtyType.value)values.default_qty_type=qtyType.value
  if(commission.value!==''){values.commission_type='percent';values.commission_value=Number(commission.value)}
  if(slippage.value!=='')values.slippage=Number(slippage.value)
  return values
})
const effectiveConfig=computed(()=>[
  ['initial_capital','初始资金'],['default_qty_type','仓位方式'],['default_qty_value','仓位数量'],['commission_type','手续费方式'],['commission_value','手续费数值'],['slippage','滑点（跳）'],['pyramiding','加仓上限'],['process_orders_on_close','收盘成交'],['calc_on_order_fills','成交后重算'],['currency','记账币种'],
].map(([key,label])=>({key:key!,label,value:overrides.value[key!]??declarationProps.value[key!],origin:key! in overrides.value?'本次覆盖':'脚本声明／引擎默认'})))
const busy=ref(false),error=ref(''),runs=ref<PineRun[]>([]),selectedId=ref(''),selected=ref<PineRun>()
const records=ref<Record<string,any>[]>([]),offset=ref(0),total=ref(0),recordKind=ref('equity'),equityHost=ref<HTMLElement>()
let timer:ReturnType<typeof setTimeout>|undefined,chart:IChartApi|undefined
const running=computed(()=>selected.value&&['queued','loading','running'].includes(selected.value.status))
const tabs=[{key:'equity',label:'权益曲线'},{key:'trades',label:'已平仓交易'},{key:'open_trades',label:'未平仓'},{key:'orders',label:'订单'},{key:'fills',label:'成交'},{key:'warnings',label:'日志'}]
const statusText=(s:string)=>({queued:'排队中',loading:'加载行情',running:'计算中',completed:'完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'}[s]??s)
const stamp=(value:number)=>new Date(value).toLocaleString()
const number=(value:unknown)=>typeof value==='number'?value.toLocaleString(undefined,{maximumFractionDigits:4}):'—'
const metrics=computed(()=>{const s=selected.value?.summary??{};return [{label:'净收益',value:number(s.netprofit)},{label:'最大回撤 %',value:number(s.max_drawdown_percent_value)},{label:'胜率 %',value:number(s.win_rate)},{label:'盈利因子',value:number(s.profit_factor)},{label:'手续费',value:number(s.commission)},{label:'未平仓盈亏',value:number(s.openprofit)}]})
const columns=computed(()=>recordKind.value==='warnings'?[{key:'bar',label:'K 线'},{key:'message',label:'说明'}]:['orders','fills'].includes(recordKind.value)?[
  {key:'id',label:'订单'},{key:'time',label:'发出时间'},{key:'type',label:'类型'},{key:'direction',label:'方向'},{key:'qty',label:'数量'},{key:'status',label:'状态'},{key:'fill_time',label:'成交时间'},{key:'fill_price',label:'成交价'},
]:[{key:'entry_id',label:'入场'},{key:'entry_time',label:'入场时间'},{key:'entry_price',label:'入场价'},{key:'size',label:'数量（负为空）'},{key:'exit_time',label:'退出时间'},{key:'exit_price',label:'退出价'},{key:'profit',label:'盈亏'},{key:'commission',label:'手续费'}])
const formatCell=(value:unknown,key:string)=>value==null?'—':key.includes('time')?stamp(Number(value)):typeof value==='number'?number(value):String(value)
function locate(row:Record<string,any>){const t=row.entry_time??row.fill_time??row.time;if(t&&selected.value)emit('locate',{time:t,run:selected.value})}
watch(()=>props.script,async(script,_,cleanup)=>{
  metadataTask?.cancel();declaration.value='';declarationProps.value={};error.value=''
  inputs.value={};inputFields.value=[]
  if(!script)return
  let stale=false;cleanup(()=>{stale=true;metadataTask?.cancel()})
  try{metadataTask=readPineMetadata(String(script.data.source));const meta=await metadataTask.result;if(stale)return;declaration.value=meta.kind;declarationProps.value=meta.props;inputFields.value=meta.inputs;for(const f of inputFields.value)inputs.value[f.title??f.varId]=f.defval}
  catch(e){error.value=String(e)}
},{immediate:true})
async function run(){
  if(!props.script||!props.symbol)return
  busy.value=true;error.value=''
  try{
    checkPine(String(props.script.data.source))
    const begin=new Date(start.value).getTime(),finish=new Date(end.value).getTime()
    if(!Number.isFinite(begin)||!Number.isFinite(finish)||begin>=finish)throw new Error('请填写有效的起止时间')
    const typedInputs={...inputs.value}
    for(const f of inputFields.value)if(['int','float','price','time'].includes(f.type))typedInputs[f.title??f.varId]=Number(typedInputs[f.title??f.varId])
    const item=await chartApi.run({script_id:props.script.id,script_version:props.script.version,symbol:props.symbol.id,timeframe:props.timeframe,start:begin,end:finish,inputs:typedInputs,props:overrides.value})
    selectedId.value=item.id;selected.value=item;await refresh();poll()
  }catch(e){error.value=String(e);emit('log',String(e))}finally{busy.value=false}
}
async function refresh(){runs.value=await chartApi.runs()}
async function loadSelected(){clearTimeout(timer);selected.value=selectedId.value?await chartApi.getRun(selectedId.value):undefined;offset.value=0;if(running.value)poll();else await loadRecords()}
async function poll(){clearTimeout(timer);if(!selectedId.value)return;try{selected.value=await chartApi.getRun(selectedId.value);if(running.value)timer=setTimeout(poll,1500);else{await refresh();await loadRecords()}}catch(e){error.value=String(e)}}
async function cancel(){if(selected.value){await chartApi.cancel(selected.value.id);await loadSelected()}}
async function rerun(){if(selected.value){try{const item=await chartApi.rerun(selected.value.id);selectedId.value=item.id;await loadSelected()}catch(e){error.value=String(e)}}}
async function selectRecords(kind:string){recordKind.value=kind;offset.value=0;await loadRecords()}
async function page(direction:number){offset.value=Math.max(0,offset.value+direction*200);await loadRecords()}
async function loadRecords(){
  chart?.remove();chart=undefined
  records.value=[];total.value=0
  if(selected.value?.status!=='completed')return
  const id=selected.value.id,kind=recordKind.value
  const result=await chartApi.records(id,kind,offset.value,kind==='equity'?10000:200)
  if(id!==selected.value?.id||kind!==recordKind.value)return
  records.value=result.items;total.value=result.total
  if(kind==='equity'){
    // Equity is the full curve, read in pages from the frozen run.
    let all=[...result.items]
    for(let from=all.length;from<result.total;from+=10000)all.push(...(await chartApi.records(id,kind,from,10000)).items)
    await nextTick();if(!equityHost.value||id!==selected.value?.id||kind!==recordKind.value)return
    chart=createChart(equityHost.value,{autoSize:true,height:150,layout:{background:{color:props.dark?'#111318':'#ffffff'},textColor:props.dark?'#aeb7c5':'#4b5563'},grid:{vertLines:{visible:false},horzLines:{visible:false}},timeScale:{timeVisible:true}})
    const line=chart.addSeries(LineSeries,{color:'#22ab94',lineWidth:2})
    const points=[...new Map(all.filter(r=>r.time).map(r=>[r.time,{time:Number(r.time)/1000 as UTCTimestamp,value:Number(r.equity)}])).values()].sort((a,b)=>Number(a.time)-Number(b.time))
    line.setData(points);chart.timeScale().fitContent()
  }
}
onMounted(async()=>{try{await refresh();if(runs.value[0]){selectedId.value=runs.value[0].id;await loadSelected()}}catch(e){error.value=String(e)}})
onBeforeUnmount(()=>{metadataTask?.cancel();clearTimeout(timer);chart?.remove()})
</script>
<style scoped>
.effective-config{margin:0;padding:6px 12px;border-bottom:1px solid var(--cw-border)}.effective-config dl{display:grid;grid-template-columns:140px 1fr;gap:4px 12px;padding:8px}.effective-config small{color:var(--cw-muted);margin-left:8px}
.tester{height:100%;overflow:auto;font-size:12px}.tester-controls,.tester-properties,.tester-inputs{display:flex;align-items:center;gap:10px;padding:8px 12px;flex-wrap:wrap;border-bottom:1px solid var(--cw-border)}label{display:flex;align-items:center;gap:5px}input{max-width:160px}.tester-properties input{width:115px}.tester-inputs{max-height:150px;overflow:auto}.tester-empty{padding:22px;color:var(--cw-muted)}.run-status{padding:5px 12px}.result-metrics{display:flex;gap:32px;padding:12px 18px}.result-metrics div{display:flex;flex-direction:column;gap:3px}.result-metrics strong{font-size:17px}.result-metrics small{color:var(--cw-muted)}nav{display:flex;border-bottom:1px solid var(--cw-border);padding:0 12px;gap:10px}.equity-chart{height:150px}.record-table{max-height:230px;overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:7px 12px;white-space:nowrap;border-bottom:1px solid var(--cw-border)}tbody tr{cursor:pointer}tbody tr:hover{background:var(--cw-hover)}footer{display:flex;align-items:center;gap:12px;padding:6px 12px}details{margin-left:auto}pre{max-height:150px;overflow:auto}.active{color:var(--cw-accent)!important}
</style>
