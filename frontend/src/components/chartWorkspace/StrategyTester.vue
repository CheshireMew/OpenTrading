<template>
  <div class="tester">
    <div class="tester-controls">
      <span>{{ symbol?.name }} · {{ timeframe }}</span>
      <label>{{ cw('start') }} <input type="datetime-local" v-model="start" /></label><label>{{ cw('end') }} <input type="datetime-local" v-model="end" /></label>
      <button :disabled="busy||!script||declaration!=='strategy'" @click="run">{{ cw('runStrategy') }}</button>
      <button v-if="selected&&running" @click="cancel">{{ cw('cancel') }}</button>
      <button v-if="selected?.status==='completed'" :disabled="exporting" @click="downloadReport">{{ cw('export') }}</button>
      <select :aria-label="cw('pastRuns')" v-model="selectedId" @change="loadSelected"><option value="">{{ cw('pastRuns') }}</option><option v-for="item in runs" :key="item.id" :value="item.id">{{ stamp(item.created_at) }} · {{ statusText(item.status) }}</option></select>
    </div>
    <details v-if="script" class="effective-config"><summary>{{ cw('effectiveParameters') }} · {{ script.name }} v{{ script.version }} · {{ cw(declaration==='strategy'?'strategy':declaration==='indicator'?'indicatorNoBacktest':'parsing') }}</summary><dl><template v-for="item in effectiveConfig" :key="item.key"><dt>{{ item.label }}</dt><dd>{{ configValue(item.value) }} <small>{{ item.origin }}</small></dd></template></dl></details>
    <div class="tester-properties">
      <label>{{ cw('initialCapital') }} <input type="number" v-model="capital" :placeholder="cw('scriptDefault')" min="1" /></label>
      <label>{{ cw('positionType') }} <select v-model="qtyType"><option value="">{{ cw('scriptDefault') }}</option><option value="fixed">{{ cw('fixedQuantity') }}</option><option value="percent_of_equity">{{ cw('equityPercent') }}</option><option value="cash">{{ cw('fixedCash') }}</option></select></label>
      <label>{{ cw('quantity') }} <input type="number" v-model="quantity" :placeholder="cw('scriptDefault')" min="0" /></label>
      <label>{{ cw('commissionPercent') }} <input type="number" v-model="commission" :placeholder="cw('scriptDefault')" min="0" step="0.01" /></label>
      <label>{{ cw('slippage') }} <input type="number" v-model="slippage" :placeholder="cw('scriptDefault')" min="0" /></label>
      <button @click="showInputs=!showInputs">{{ cw('scriptInputs') }}</button>
    </div>
    <div v-if="showInputs" class="tester-inputs"><label v-for="field in inputFields" :key="field.title" :title="field.tooltip">{{ field.title }}
      <input v-if="field.type==='bool'" type="checkbox" v-model="inputs[field.title]" />
      <select v-else-if="field.options" v-model="inputs[field.title]"><option v-for="option in field.options" :key="String(option)" :value="option">{{ option }}</option></select>
      <input v-else v-model="inputs[field.title]" :type="['int','float','price','time'].includes(field.type)?'number':'text'" :step="field.step??'any'" />
    </label></div>
    <p v-if="error" role="alert" class="cw-error">{{ messageText(error) }}</p>
    <div v-if="selected" class="run-status">{{ statusText(selected.status) }} <progress v-if="running" :value="selected.progress" max="100" /> {{ running?Math.round(selected.progress??0)+'%':'' }} <span v-if="selected.error" class="cw-error">{{ messageText(selected.error) }}</span></div>
    <div v-if="selected?.status==='completed'" class="tester-result">
      <p class="result-context">{{ selected.request.symbol }} · {{ selected.request.timeframe }} · {{ stamp(selected.request.start) }} – {{ stamp(selected.request.end) }}</p>
      <div class="result-metrics"><div v-for="metric in metrics" :key="metric.label" :title="metric.hint"><small>{{ metric.label }}</small><strong>{{ metric.value }}</strong></div></div>
      <nav><button v-for="tab in tabs" :key="tab.key" :class="{active:tab.key===recordKind}" @click="selectRecords(tab.key)">{{ tab.label }}</button></nav>
      <div v-if="recordKind==='equity'" ref="equityHost" class="equity-chart" />
      <div v-else class="record-table"><table><thead><tr><th v-for="col in columns" :key="col.key">{{ col.label }}</th></tr></thead><tbody><tr v-for="(row,index) in records" :key="index"><td v-for="col in columns" :key="col.key">{{ formatCell(row[col.key],col.key) }}</td></tr></tbody></table></div>
      <footer v-if="recordKind!=='equity'"><button :disabled="offset===0" @click="page(-1)">{{ cw('previous') }}</button><span>{{ total?offset+1:0 }}–{{ Math.min(offset+records.length,total) }} / {{ total }}</span><button :disabled="offset+records.length>=total" @click="page(1)">{{ cw('next') }}</button></footer>
    </div>
    <p v-else-if="!selected" class="tester-empty">{{ cw('testerEmpty') }}</p>
  </div>
</template>
<script setup lang="ts">
import { DARK_PALETTE } from '@/theme/palette.mjs'
import { computed,nextTick,onBeforeUnmount,onMounted,ref,watch } from 'vue'
import { createChart,LineSeries, type IChartApi, type UTCTimestamp } from 'lightweight-charts'
import { readPineMetadata } from '@/modules/chartWorkspace/pineEngine'
import { chartApi, type ChartSymbol,type WorkspaceDocument,type PineRun } from '@/modules/chartWorkspace/api'
import { cw,messageText,formatNumber,formatDate } from '@/modules/chartWorkspace/locale'
import { payoffRatio } from '@/modules/chartWorkspace/metrics.mjs'
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
  ['initial_capital',cw('initialCapital')],['default_qty_type',cw('positionType')],['default_qty_value',cw('positionQuantity')],['commission_type',cw('commissionType')],['commission_value',cw('commissionValue')],['slippage',cw('slippage')],['pyramiding',cw('pyramiding')],['process_orders_on_close',cw('ordersOnClose')],['calc_on_order_fills',cw('recalculateFills')],['currency',cw('accountCurrency')],
].map(([key,label])=>({key:key!,label,value:overrides.value[key!]??declarationProps.value[key!],origin:key! in overrides.value?cw('override'):cw('declarationDefault')})))
const busy=ref(false),exporting=ref(false),error=ref(''),runs=ref<PineRun[]>([]),selectedId=ref(''),selected=ref<PineRun>()
const records=ref<Record<string,any>[]>([]),offset=ref(0),total=ref(0),recordKind=ref('equity'),equityHost=ref<HTMLElement>()
let timer:ReturnType<typeof setTimeout>|undefined,chart:IChartApi|undefined
let disposed=false,selectionGeneration=0,recordGeneration=0,refreshGeneration=0
const running=computed(()=>selected.value&&['queued','loading','running'].includes(selected.value.status))
const tabs=computed(()=>[{key:'equity',label:cw('equity')},{key:'trades',label:cw('trades')},{key:'open_trades',label:cw('openTrades')},{key:'warnings',label:cw('warnings')}])
const statusText=(s:string)=>({queued:cw('queued'),loading:cw('loadingMarket'),running:cw('running'),completed:cw('completed'),failed:cw('failed'),cancelled:cw('cancelled'),interrupted:cw('interrupted')}[s]??s)
const stamp=(value:number)=>formatDate(value)
const number=(value:unknown)=>formatNumber(value)
const metrics=computed(()=>{
  const s=selected.value?.summary??{},ratio=payoffRatio(s)
  return [
    {label:cw('netProfit'),value:number(s.netprofit)},
    {label:cw('drawdown'),value:number(s.max_drawdown_percent_value)},
    {label:cw('winRate'),value:number(s.win_rate)},
    {label:cw('profitFactor'),value:number(s.profit_factor),hint:cw('profitFactorHint')},
    {label:cw('payoffRatio'),value:number(ratio),hint:cw(ratio===null?'payoffUnavailable':'payoffRatioHint')},
    {label:cw('commission'),value:number(s.commission)},
    {label:cw('openProfit'),value:number(s.openprofit)},
  ]
})
const columns=computed(()=>recordKind.value==='warnings'?[{key:'bar',label:cw('bar')},{key:'message',label:cw('description')}]:['orders','fills'].includes(recordKind.value)?[
  {key:'id',label:cw('order')},{key:'time',label:cw('sentTime')},{key:'type',label:cw('type')},{key:'direction',label:cw('direction')},{key:'qty',label:cw('quantity')},{key:'status',label:cw('status')},{key:'fill_time',label:cw('fillTime')},{key:'fill_price',label:cw('fillPrice')},
]:[{key:'entry_id',label:cw('entry')},{key:'entry_time',label:cw('entryTime')},{key:'entry_price',label:cw('entryPrice')},{key:'size',label:cw('signedQuantity')},{key:'exit_time',label:cw('exitTime')},{key:'exit_price',label:cw('exitPrice')},{key:'profit',label:cw('profit')},{key:'commission',label:cw('commission')}])
const formatCell=(value:unknown,key:string)=>value==null?'—':key.includes('time')?stamp(Number(value)):key==='direction'&&Number.isFinite(Number(value))&&Number(value)!==0?cw(Number(value)>0?'long':'short'):typeof value==='number'?number(value):['type','status'].includes(key)?recordValue(value):key==='message'?messageText(value):String(value)
const enumKeys:Record<string,string>={fixed:'fixedQuantity',percent_of_equity:'equityPercent',cash:'fixedCash',percent:'percent',cash_per_order:'cashPerOrder',cash_per_contract:'cashPerContract',pending:'pending',filled:'filled',cancelled:'cancelled',market:'marketOrder',limit:'limitOrder',stop:'stopOrder',stop_limit:'stopLimit'}
function recordValue(value:unknown){const key=enumKeys[String(value)];return key?cw(key):messageText(value)}
function configValue(value:unknown){return typeof value==='boolean'?cw(value?'yes':'no'):typeof value==='number'?number(value):recordValue(value)}
watch(()=>props.script,async(script,_,cleanup)=>{
  metadataTask?.cancel();declaration.value='';declarationProps.value={};error.value=''
  inputs.value={};inputFields.value=[]
  if(!script)return
  let stale=false;cleanup(()=>{stale=true;metadataTask?.cancel()})
  try{metadataTask=readPineMetadata(String(script.data.source));const meta=await metadataTask.result;if(stale)return;declaration.value=meta.kind;declarationProps.value=meta.props;inputFields.value=meta.inputs;for(const f of inputFields.value)inputs.value[f.title??f.varId]=f.defval}
  catch(e){if(!stale&&!disposed)error.value=String(e)}
},{immediate:true})
async function run(){
  if(!props.script||!props.symbol)return
  const generation=selectionGeneration,previousId=selectedId.value
  busy.value=true;error.value=''
  try{
    checkPine(String(props.script.data.source))
    const begin=new Date(start.value).getTime(),finish=new Date(end.value).getTime()
    if(!Number.isFinite(begin)||!Number.isFinite(finish)||begin>=finish)throw new Error(cw('invalidDates'))
    const typedInputs={...inputs.value}
    for(const f of inputFields.value)if(['int','float','price','time'].includes(f.type))typedInputs[f.title??f.varId]=Number(typedInputs[f.title??f.varId])
    const item=await chartApi.run({script_id:props.script.id,script_version:props.script.version,script_source:String(props.script.data.source),script_name:props.script.name,symbol:props.symbol.id,timeframe:props.timeframe,start:begin,end:finish,inputs:typedInputs,props:overrides.value})
    if(disposed||generation!==selectionGeneration||previousId!==selectedId.value)return
    ++selectionGeneration;++recordGeneration;clearTimeout(timer)
    const accepted=selectionGeneration
    selectedId.value=item.id;selected.value=item;void poll()
    await refresh().catch(e=>{if(!disposed&&accepted===selectionGeneration)error.value=String(e)})
  }catch(e){if(!disposed&&generation===selectionGeneration){error.value=String(e);emit('log',String(e))}}finally{busy.value=false}
}
async function refresh(){const generation=++refreshGeneration;const result=await chartApi.runs();if(!disposed&&generation===refreshGeneration)runs.value=result}
async function loadSelected(){
  if(disposed)return
  clearTimeout(timer);const generation=++selectionGeneration,id=selectedId.value;++recordGeneration
  selected.value=undefined;records.value=[];total.value=0;chart?.remove();chart=undefined
  const result=id?await chartApi.getRun(id):undefined
  if(disposed||generation!==selectionGeneration||id!==selectedId.value)return
  selected.value=result;offset.value=0;if(running.value)void poll();else await loadRecords()
}
async function poll(){
  clearTimeout(timer);const id=selectedId.value,generation=selectionGeneration
  const current=()=>!disposed&&id===selectedId.value&&generation===selectionGeneration
  if(!id||!current())return
  try{const result=await chartApi.getRun(id);if(!current())return;selected.value=result
    if(running.value)timer=setTimeout(poll,1500);else{await refresh().catch(e=>{if(current())error.value=String(e)});if(current())await loadRecords()}
  }catch(e){if(current())error.value=String(e)}
}
async function cancel(){if(selected.value){const id=selected.value.id,generation=selectionGeneration;await chartApi.cancel(id);if(!disposed&&id===selectedId.value&&generation===selectionGeneration)await loadSelected()}}
async function downloadReport(){
  const run=selected.value
  if(!run||exporting.value)return
  exporting.value=true
  try{
    const result:Record<string,unknown>={run}
    for(const kind of ['equity','trades','open_trades','warnings']){
      const rows:Record<string,any>[]=[]
      for(let offset=0;;offset+=10000){const page=await chartApi.records(run.id,kind,offset,10000);rows.push(...page.items);if(rows.length>=page.total)break;if(!page.items.length)throw new Error(cw('invalidReport'))}
      result[kind]=rows
    }
    const url=URL.createObjectURL(new Blob([JSON.stringify(result)],{type:'application/json;charset=utf-8'}))
    const link=document.createElement('a');link.href=url;link.download=`${run.id}.json`;link.click();URL.revokeObjectURL(url)
  }catch(e){if(!disposed)error.value=String(e)}finally{exporting.value=false}
}
async function selectRecords(kind:string){recordKind.value=kind;offset.value=0;await loadRecords()}
async function page(direction:number){offset.value=Math.max(0,offset.value+direction*200);await loadRecords()}
async function loadRecords(){
  if(disposed)return
  const generation=++recordGeneration,requestedOffset=offset.value
  chart?.remove();chart=undefined
  records.value=[];total.value=0
  if(selected.value?.status!=='completed')return
  const id=selected.value.id,kind=recordKind.value
  const current=()=>!disposed&&generation===recordGeneration&&id===selected.value?.id&&kind===recordKind.value&&requestedOffset===offset.value
  const result=await chartApi.records(id,kind,offset.value,kind==='equity'?1000:200,kind==='equity')
  if(!current())return
  records.value=result.items;total.value=result.total
  if(kind==='equity'){
    await nextTick();if(!equityHost.value||!current())return
    chart=createChart(equityHost.value,{autoSize:true,height:150,layout:{background:{color:props.dark?DARK_PALETTE.canvas:'#ffffff'},textColor:props.dark?DARK_PALETTE.muted:'#4b5563'},grid:{vertLines:{visible:false},horzLines:{visible:false}},timeScale:{timeVisible:true}})
    const line=chart.addSeries(LineSeries,{color:'#22ab94',lineWidth:2})
    const points=[...new Map(result.items.filter(r=>r.time).map(r=>[r.time,{time:Number(r.time)/1000 as UTCTimestamp,value:Number(r.equity)}])).values()].sort((a,b)=>Number(a.time)-Number(b.time))
    line.setData(points);chart.timeScale().fitContent()
  }
}
onMounted(async()=>{try{await refresh();if(!disposed&&runs.value[0]){selectedId.value=runs.value[0].id;await loadSelected()}}catch(e){if(!disposed)error.value=String(e)}})
onBeforeUnmount(()=>{disposed=true;++selectionGeneration;++recordGeneration;metadataTask?.cancel();clearTimeout(timer);chart?.remove()})
</script>
<style scoped>
.result-context{padding:8px 18px 0;color:var(--cw-muted);margin:0}.effective-config{margin:0;padding:6px 12px;border-bottom:1px solid var(--cw-border)}.effective-config dl{display:grid;grid-template-columns:140px 1fr;gap:4px 12px;padding:8px}.effective-config small{color:var(--cw-muted);margin-left:8px}
.tester{height:100%;overflow:auto;font-size:12px}.tester-controls,.tester-properties,.tester-inputs{display:flex;align-items:center;gap:10px;padding:8px 12px;flex-wrap:wrap;border-bottom:1px solid var(--cw-border)}label{display:flex;align-items:center;gap:5px}input{max-width:160px}.tester-properties input{width:115px}.tester-inputs{max-height:150px;overflow:auto}.tester-empty{padding:22px;color:var(--cw-muted)}.run-status{padding:5px 12px}.result-metrics{display:flex;flex-wrap:wrap;gap:16px 32px;padding:12px 18px}.result-metrics div{display:flex;flex-direction:column;gap:3px}.result-metrics strong{font-size:17px}.result-metrics small{color:var(--cw-muted)}nav{display:flex;border-bottom:1px solid var(--cw-border);padding:0 12px;gap:10px}.equity-chart{height:150px}.record-table{max-height:230px;overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:7px 12px;white-space:nowrap;border-bottom:1px solid var(--cw-border)}footer{display:flex;align-items:center;gap:12px;padding:6px 12px}details{margin-left:auto}pre{max-height:150px;overflow:auto}.active{color:var(--cw-accent)!important}
</style>
