<template>
  <section class="chart-workspace" :class="{ 'cw-dark':theme==='dark' }">
    <header class="cw-header">
      <button class="cw-menu" :aria-label="cw('openMenu')" @click="openNavigation"><Bars3Icon class="cw-icon" aria-hidden="true" /></button><strong class="cw-brand">OpenTrading</strong>
      <button class="cw-symbol" aria-haspopup="dialog" :aria-expanded="searchOpen && searchMode==='chart'" @click="searchOpen=true;searchMode='chart'">{{ activeSymbol?.name??cw('selectSymbol') }} <small>{{ cw(activeSymbol?.market==='usdm'?'perpetual':activeSymbol?.market==='index'?'index':'spot') }}</small><MagnifyingGlassIcon class="cw-icon" aria-hidden="true" /></button>
      <div class="cw-periods"><button v-for="tf in availablePeriods" :key="tf.value" :class="{active:activeTimeframe===tf.value}" :aria-pressed="activeTimeframe===tf.value" @click="setPeriod(tf.value)">{{ tf.label }}</button></div>
      <button :aria-expanded="indicatorsOpen" @click="indicatorsOpen=!indicatorsOpen"><AdjustmentsHorizontalIcon class="cw-icon" aria-hidden="true" /> {{ cw('indicators') }}</button>
      <details class="cw-sync"><summary>{{ cw('settings') }}</summary><div><label>{{ cw('historyDepth') }} <select :aria-label="cw('historyDepth')" :value="historyDepth" @change="setHistoryDepth(Number(($event.target as HTMLSelectElement).value))"><option :value="1000">1,000</option><option :value="5000">5,000</option><option :value="10000">10,000</option></select></label><button @click="workspace?.chart.renderer.set('logScale',!workspace.chart.renderer.get('logScale'))">{{ cw('priceScale') }}</button></div></details>
      <select :aria-label="cw('layout')" :value="layout" @change="setLayout(($event.target as HTMLSelectElement).value)"><option value="1">{{ cw('single') }}</option><option value="2h">{{ cw('horizontal') }}</option><option value="2v">{{ cw('vertical') }}</option><option value="4">{{ cw('four') }}</option></select>
      <details class="cw-sync"><summary>{{ cw('sync') }}</summary><div><label v-for="link in syncOptions" :key="link.key"><input type="checkbox" :checked="sync[link.key]" @change="setSync(link.key,($event.target as HTMLInputElement).checked)" />{{ link.label }}</label></div></details>
      <span class="cw-spacer" /><button @click="saveNow">{{ cw(saveStatus) }}</button><button @click="saveAsLayout">{{ cw('saveLayoutAs') }}</button>
      <select v-if="layouts.length>1" :aria-label="cw('savedLayouts')" :value="layoutId" @change="switchLayout(($event.target as HTMLSelectElement).value)"><option v-for="item in layouts" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <button @click="toggleTheme" :aria-label="cw('toggleTheme')"><SunIcon v-if="theme==='dark'" class="cw-icon" aria-hidden="true" /><MoonIcon v-else class="cw-icon" aria-hidden="true" /></button><button @click="toggleWatchlist" :aria-expanded="watchlistVisible">{{ cw('watchlist') }}</button>
    </header>
    <div v-if="error" class="cw-notice" role="alert"><span>{{ messageText(error) }}</span><button v-if="conflictDraft" @click="recoverDraft">{{ cw('recoverLayout') }}</button><button @click="error=''">{{ cw('close') }}</button><button v-if="!workspace" @click="initialize">{{ cw('reload') }}</button></div>
    <div v-if="snapshotRun" class="cw-notice"><span>{{ cw('viewingSnapshot',{run:snapshotRun.slice(0,8)}) }}</span><button @click="returnLive">{{ cw('returnLive') }}</button></div>
    <div class="cw-body">
      <div class="cw-center">
        <div ref="chartHost" class="cw-chart" />
        <div v-if="loading" class="cw-loading" role="status" aria-live="polite">{{ cw('loadingChart') }}</div>
        <div v-if="indicatorsOpen" class="cw-indicator-picker"><header><strong>{{ cw('indicators') }}</strong><button :aria-label="cw('close')" @click="indicatorsOpen=false"><XMarkIcon class="cw-icon" aria-hidden="true" /></button></header><input v-model="indicatorQuery" :aria-label="cw('searchIndicators')" :placeholder="cw('searchIndicators')" type="search" /><label><input type="checkbox" v-model="favoritesOnly" />{{ cw('favoritesOnly') }}</label><div v-for="item in filteredIndicators" :key="item.type" class="cw-indicator-row"><button :aria-label="cw('favoritesOnly')+': '+item.name" :aria-pressed="favoriteIndicators.includes(item.type)" @click="toggleFavorite(item.type)"><StarIcon class="cw-icon" :class="{'cw-starred':favoriteIndicators.includes(item.type)}" aria-hidden="true" /></button><button @click="addNative(item.type)">{{ item.name }}</button></div><button @click="bottomTab='editor';indicatorsOpen=false">{{ cw('scriptLibrary') }}</button></div>
        <div class="cw-bottom" :style="{height:bottomTab?bottomHeight+'px':'34px'}">
          <div v-if="bottomTab" class="cw-horizontal-resizer" role="separator" aria-orientation="horizontal" tabindex="0" :aria-valuenow="bottomHeight" :aria-valuemin="180" :aria-valuemax="maxBottomHeight" :aria-label="cw('resizeBottom')" @keydown.up.prevent="bottomHeight=Math.min(maxBottomHeight,bottomHeight+20)" @keydown.down.prevent="bottomHeight=Math.max(180,bottomHeight-20)" @pointerdown="resizeBottom" />
          <nav class="cw-bottom-tabs"><button :aria-expanded="bottomTab==='editor'" :class="{active:bottomTab==='editor'}" @click="toggleBottom('editor')">{{ cw('pineEditor') }}</button><button :aria-expanded="bottomTab==='tester'" :class="{active:bottomTab==='tester'}" @click="toggleBottom('tester')">{{ cw('strategyTester') }}</button><button :aria-expanded="bottomTab==='logs'" :class="{active:bottomTab==='logs'}" @click="toggleBottom('logs')">{{ cw('runLogs') }} <small>{{ logs.length||'' }}</small></button><span class="cw-spacer" /><span class="cw-feed" :title="messageText(feedError)">● {{ feedText }}</span><small>{{ cw('activeChart',{cell:activeCell}) }} · {{ activeSymbol?.currency }} · {{ historyText }}</small><button v-if="bottomTab" :aria-label="cw('close')" @click="bottomTab=''"><ChevronDownIcon class="cw-icon" aria-hidden="true" /></button></nav>
          <div v-show="bottomTab==='editor'" class="cw-editor-panel">
            <div class="cw-editor-tools"><select v-model="scriptId" :aria-label="cw('myScript')" @change="openScript"><option v-for="item in scripts" :key="item.id" :value="item.id">{{ item.name }}{{ item.readonly?' · '+cw('original'):'' }}</option></select><button @click="newScript('indicator')">{{ cw('newIndicator') }}</button><button @click="newScript('strategy')">{{ cw('newStrategy') }}</button><button @click="saveScript(false)">{{ cw('save') }}</button><button @click="saveScript(true)">{{ cw('saveAs') }}</button><button @click="importFile?.click()">{{ cw('import') }}</button><button @click="exportScript">{{ cw('export') }}</button><button @click="showCapabilities">{{ cw('compatibility') }}</button><input ref="importFile" type="file" accept=".pine,text/plain" hidden @change="importScript" /><span class="cw-spacer" /><span class="cw-version">{{ scriptDirty?cw('draft'):selectedScript?cw('version',{version:selectedScript.version}):'' }} {{ scriptRunning?'· '+messageText(scriptRunning):'' }}</span><button class="cw-primary" :disabled="executing" @click="addPine">{{ cw(executing?'calculating':'addToActive') }}</button><button v-if="executing" @click="cancelPine">{{ cw('stop') }}</button></div>
            <PineEditor v-if="editorMounted" v-model="source" :dark="theme==='dark'" :error="pineError" @run="addPine" @save="saveScript(false)" />
          </div>
          <StrategyTester v-if="testerMounted" v-show="bottomTab==='tester'" :symbol="activeSymbol" :timeframe="backendPeriod" :script="selectedScript" :dark="theme==='dark'" @locate="locateTrade" @log="addLog" />
          <div v-if="bottomTab==='logs'" class="cw-log"><p v-if="!logs.length">{{ cw('noLogs') }}</p><p v-for="(item,index) in logs" :key="index">{{ formatDate(item.time,true) }}  {{ messageText(item.message) }}</p></div>
        </div>
      </div>
      <div v-if="rightOpen && !compactWorkspace" class="cw-vertical-resizer" role="separator" aria-orientation="vertical" tabindex="0" :aria-valuenow="rightWidth" :aria-valuemin="240" :aria-valuemax="520" :aria-label="cw('resizeWatchlist')" @keydown.left.prevent="rightWidth=Math.min(520,rightWidth+20)" @keydown.right.prevent="rightWidth=Math.max(240,rightWidth-20)" @pointerdown="resizeRight" />
      <button v-if="compactWorkspace && watchlistDrawerOpen" class="cw-watch-backdrop" :aria-label="cw('close')" @click="watchlistDrawerOpen=false" /><aside v-if="watchlistVisible" ref="watchlistDialogRef" tabindex="-1" class="cw-watchlist" :role="compactWorkspace ? 'dialog' : undefined" :aria-modal="compactWorkspace ? 'true' : undefined" :aria-label="cw('watchlist')" :style="{width:rightWidth+'px'}">
        <header><button v-if="compactWorkspace" :aria-label="cw('close')" @click="watchlistDrawerOpen=false"><XMarkIcon class="cw-icon" aria-hidden="true" /></button><select v-model="watchlistId" :aria-label="cw('watchlists')"><option v-for="item in watchlists" :key="item.id" :value="item.id">{{ item.name }}</option></select><button @click="newWatchlist">{{ cw('newList') }}</button><button @click="renameWatchlist" :aria-label="cw('renameList')"><PencilSquareIcon class="cw-icon" aria-hidden="true" /></button><button @click="searchMode='watchlist';searchOpen=true" :aria-label="cw('addWatchSymbol')"><PlusIcon class="cw-icon" aria-hidden="true" /></button></header>
        <div v-if="pendingWatch.includes(watchlistId)" class="cw-notice"><span>{{ cw('pendingWatch') }}</span><button @click="persistWatch(watchSymbols)">{{ cw('retrySave') }}</button></div>
        <div class="cw-watch-scroll"><table><thead><tr><th>{{ cw('symbol') }}</th><th>{{ cw('lastAndChange') }}</th><th>{{ cw('changePercent') }}</th><th /></tr></thead><tbody><tr v-for="(key,index) in watchSymbols" :key="key" :class="{selected:activeSymbol?.id===key}" draggable="true" @dragstart="dragIndex=index" @dragover.prevent @drop.prevent="moveWatch(index)" @click="selectSymbol(key)"><td><strong>{{ displaySymbol(key) }}</strong><small>{{ marketLabel(key) }}</small></td><td :class="quoteClass(key)">{{ priceText(quotes[key]?.price) }}<small :class="quoteClass(key)">{{ priceText(quotes[key]?.change) }}</small></td><td :class="quoteClass(key)" :title="messageText(quotes[key]?.error??quotes[key]?.basis)">{{ quotes[key]?.change_pct==null?'—':quotes[key]!.change_pct!.toFixed(2)+'%' }}<small>{{ quotes[key]?.basis==='交易日'?cw('tradingDay'):'24h' }}</small></td><td><button class="cw-remove" @click.stop="removeWatch(key)" :aria-label="cw('removeSymbol',{symbol:displaySymbol(key)??key})">×</button></td></tr></tbody></table></div>
        <div class="cw-instrument"><strong>{{ activeSymbol?.name }}</strong><small>{{ activeSymbol?.exchange.toUpperCase() }} · {{ marketLabel(activeSymbol?.id??'') }}</small><div class="cw-last" :class="quoteClass(activeSymbol?.id??'')">{{ priceText(activeQuote?.price) }} <small>{{ activeSymbol?.currency }}</small></div><p v-if="activeQuote?.error" class="cw-error">{{ messageText(activeQuote.error) }}</p><dl><dt>{{ cw('unit') }}</dt><dd>{{ activeSymbol?.metadata?.basecurrency??cw('notProvided') }}</dd><dt>{{ cw('quoteCurrency') }}</dt><dd>{{ activeSymbol?.currency }}</dd><dt>{{ cw('change') }}</dt><dd>{{ priceText(activeQuote?.change) }}</dd><dt>{{ cw('minimumTick') }}</dt><dd>{{ activeSymbol?.metadata?.mintick??cw('notProvided') }}</dd><dt>{{ cw('updatedAt') }}</dt><dd>{{ activeQuote?.updated_at?formatDate(activeQuote.updated_at,true):'—' }}</dd></dl><button @click="workspace?.context().togglePanel('objects')">{{ cw('objects') }}</button><button @click="workspace?.context().togglePanel('dataWindow')">{{ cw('dataWindow') }}</button></div>
      </aside>
    </div>
    <div v-if="nameRequest" class="cw-modal-backdrop" @click.self="finishName(false)"><form ref="nameDialogRef" tabindex="-1" class="cw-name-dialog" role="dialog" aria-modal="true" :aria-label="messageText(nameRequest.title)" @submit.prevent="finishName(true)"><label>{{ messageText(nameRequest.title) }}<input ref="nameInput" v-model="nameRequest.value" maxlength="160" required /></label><footer><button type="button" @click="finishName(false)">{{ cw('cancel') }}</button><button class="cw-primary" type="submit" :disabled="!nameRequest.value.trim()">{{ cw('confirm') }}</button></footer></form></div>
    <div v-if="capabilitiesOpen" class="cw-modal-backdrop" @click.self="capabilitiesOpen=false"><section ref="capabilitiesDialogRef" tabindex="-1" class="cw-search cw-capabilities" role="dialog" aria-modal="true" :aria-label="cw('pineCompatibility')"><header><strong>Pine v5/v6 · PineTS {{ capabilities?.version }}</strong><button @click="capabilitiesOpen=false">{{ cw('close') }}</button></header><div><h3>{{ cw('supported') }}</h3><p v-for="item in capabilities?.supported" :key="item">{{ messageText(item) }}</p><h3>{{ cw('limited') }}</h3><p v-for="item in capabilities?.limited" :key="item">{{ messageText(item) }}</p><h3>{{ cw('unsupported') }}</h3><p v-for="item in capabilities?.unsupported" :key="item">{{ messageText(item) }}</p><p>{{ cw('analysisOnly') }}</p></div></section></div>
    <div v-if="searchOpen" class="cw-modal-backdrop" @click.self="searchOpen=false"><section ref="searchDialogRef" tabindex="-1" class="cw-search" role="dialog" aria-modal="true" :aria-label="cw('searchSymbol')"><header><strong>{{ cw(searchMode==='watchlist'?'addWatch':'switchSymbol') }}</strong><button :aria-label="cw('close')" @click="searchOpen=false"><XMarkIcon class="cw-icon" aria-hidden="true" /></button></header><input ref="symbolSearchInput" v-model="symbolQuery" type="search" :aria-label="cw('searchSymbolHint')" :placeholder="cw('searchSymbolHint')" /><div class="cw-market-filter"><button v-for="filter in marketFilters" :key="filter.value" :class="{active:marketFilter===filter.value}" :aria-pressed="marketFilter===filter.value" @click="marketFilter=filter.value">{{ filter.label }}</button></div><div class="cw-search-results"><button v-for="item in searchResults" :key="item.id" @click="pickSearch(item.id)"><strong>{{ item.name }}</strong><span>{{ item.exchange.toUpperCase() }}</span><small>{{ marketLabel(item.id) }}</small></button><p v-if="!searchResults.length">{{ cw('noSymbols') }}</p></div></section></div>
  </section>
</template>

<script setup lang="ts">
import { computed,defineAsyncComponent,nextTick,onBeforeUnmount,onMounted,ref,shallowRef,watch } from 'vue'
import { VelaWorkspace } from '@luxalgo/vela/workspace'
import { OpenTradingPineEngine } from '@/modules/chartWorkspace/pineEngine'
import { DARK_THEME,LIGHT_THEME,type IndicatorHandle } from '@luxalgo/vela'
import { Bars3Icon, MagnifyingGlassIcon, AdjustmentsHorizontalIcon, SunIcon, MoonIcon, XMarkIcon, ChevronDownIcon, PencilSquareIcon, PlusIcon, StarIcon } from '@heroicons/vue/24/outline'
import { useModalDialog } from '@/composables/useModalDialog'
import { useTheme } from '@/composables/useTheme'
import { chartApi,type ChartSymbol,type ChartQuote,type WorkspaceDocument,type PineRun,type PineCapabilities } from '@/modules/chartWorkspace/api'
import { OpenTradingProvider,fromVela,velaSymbol,timeframes } from '@/modules/chartWorkspace/provider'
import { writeDraft,readDraft } from '@/modules/chartWorkspace/drafts'
import { migrateWorkspaceState } from '@/modules/chartWorkspace/legacyState'
import { installMarketDrawings,markScript } from '@/modules/chartWorkspace/persistence'
import { checkPine } from '@/modules/chartWorkspace/pineCompatibility.mjs'
import { cw,messageText,formatNumber,formatDate } from '@/modules/chartWorkspace/locale'
import { localizeChart } from '@/modules/chartWorkspace/localize'
import StrategyTester from '@/components/chartWorkspace/StrategyTester.vue'
const PineEditor=defineAsyncComponent(()=>import('@/components/chartWorkspace/PineEditor.vue'))
defineOptions({name:'ChartWorkspace'})
const {theme,toggleTheme}=useTheme()
const symbolSearchInput=ref<HTMLInputElement>()
const chartHost=ref<HTMLElement>(),importFile=ref<HTMLInputElement>()
const workspace=shallowRef<VelaWorkspace>(),provider=shallowRef<OpenTradingProvider>()
const nameRequest=ref<{title:string;value:string;resolve:(value:string|null)=>void}|null>(null),nameInput=ref<HTMLInputElement>()
async function requestName(title:string,value:string):Promise<string|null>{return new Promise(resolve=>{nameRequest.value={title,value,resolve};void nextTick(()=>{nameInput.value?.focus();nameInput.value?.select()})})}
function finishName(accept:boolean){const item=nameRequest.value;if(!item)return;nameRequest.value=null;item.resolve(accept?item.value.trim():null)}
const capabilities=ref<PineCapabilities>(),capabilitiesOpen=ref(false)
async function showCapabilities(){try{capabilities.value=await chartApi.capabilities();capabilitiesOpen.value=true}catch(e){fail(e)}}
const loading=ref(true),error=ref(''),saveStatus=ref('saved'),layout=ref('1'),layoutId=ref('default'),layouts=ref<WorkspaceDocument[]>([])
const symbols=ref<ChartSymbol[]>([]),watchlists=ref<WorkspaceDocument[]>([]),watchlistId=ref('default'),quotes=ref<Record<string,ChartQuote>>({})
const scripts=ref<WorkspaceDocument[]>([]),scriptId=ref('opentrading-v7-2'),source=ref(''),scriptDirty=ref(false),scriptRunning=ref('')
const executing=ref(false),pineError=ref<{message:string;line?:number;column?:number}|null>(null)
const activeCell=ref('c1'),activeSymbolId=ref('binance:spot:BTCUSDT'),activeTimeframe=ref('60')
const historyByCell=ref<Record<string,{loaded:number;state:string}>>({})
const historyText=computed(()=>{const h=historyByCell.value[activeCell.value];return h?cw('historyBars',{count:formatNumber(h.loaded,0)})+(h.state==='loading'?' · '+cw('loading'):h.state==='aborted'?' · '+cw('incomplete'):''):cw('loadingHistory')})
const historyDepth=ref(1000),conflictDraft=ref<Record<string,any>|null>(null),snapshotRun=ref('')
let snapshotChart:import('@luxalgo/vela').Vela|undefined
function returnLive(){if(snapshotChart)void snapshotChart.setMarket({data:undefined});snapshotChart=undefined;snapshotRun.value=''}
const activeSymbol=computed(()=>symbols.value.find(s=>s.id===activeSymbolId.value))
const activeQuote=computed(()=>quotes.value[activeSymbolId.value])
const selectedScript=computed(()=>scripts.value.find(s=>s.id===scriptId.value))
const watchlist=computed(()=>watchlists.value.find(s=>s.id===watchlistId.value))
const pendingWatch=ref<string[]>([])
let watchSave=Promise.resolve()
const watchSymbols=computed<string[]>(()=>(watchlist.value?.data.symbols as string[]|undefined)??[])
const searchOpen=ref(false),symbolQuery=ref(''),searchMode=ref('chart'),marketFilter=ref('all')
const marketFilters=computed(()=>[{value:'all',label:cw('all')},{value:'spot',label:cw('spot')},{value:'usdm',label:cw('perpetual')},{value:'index',label:cw('index')}])
const searchResults=computed(()=>symbols.value.filter(s=>(marketFilter.value==='all'||s.market===marketFilter.value)&&`${s.id} ${s.name}`.toLowerCase().includes(symbolQuery.value.toLowerCase())).slice(0,100))
const {dialogRef:searchDialogRef}=useModalDialog(searchOpen,()=>{searchOpen.value=false},symbolSearchInput)
const {dialogRef:nameDialogRef}=useModalDialog(computed(()=>nameRequest.value!==null),()=>finishName(false),nameInput)
const {dialogRef:capabilitiesDialogRef}=useModalDialog(capabilitiesOpen,()=>{capabilitiesOpen.value=false})
const rightOpen=ref(true),rightWidth=ref(300),bottomHeight=ref(340),bottomTab=ref(''),editorMounted=ref(false),testerMounted=ref(false)
const compactWorkspace=ref(false),watchlistDrawerOpen=ref(false),maxBottomHeight=ref(700)
const watchlistVisible=computed(()=>compactWorkspace.value?watchlistDrawerOpen.value:rightOpen.value)
const {dialogRef:watchlistDialogRef}=useModalDialog(computed(()=>compactWorkspace.value&&watchlistDrawerOpen.value),()=>{watchlistDrawerOpen.value=false})
function toggleWatchlist(){if(compactWorkspace.value)watchlistDrawerOpen.value=!watchlistDrawerOpen.value;else rightOpen.value=!rightOpen.value}
function syncWorkspaceViewport(){compactWorkspace.value=window.innerWidth<=950;maxBottomHeight.value=Math.max(180,window.innerHeight-180);if(!compactWorkspace.value)watchlistDrawerOpen.value=false;if(bottomHeight.value>maxBottomHeight.value)bottomHeight.value=maxBottomHeight.value}
onMounted(()=>{syncWorkspaceViewport();window.addEventListener('resize',syncWorkspaceViewport)})
onBeforeUnmount(()=>window.removeEventListener('resize',syncWorkspaceViewport))

const logs=ref<{time:number;message:string}[]>([]),feedStatus=ref('connecting'),feedError=ref('')
const feedText=computed(()=>({connecting:cw('connecting'),live:cw('live'),polling:cw('polling'),offline:cw('offline'),error:cw('dataError')}[feedStatus.value]??feedStatus.value))
const sync=ref<Record<string,boolean>>({viewport:true,crosshair:true,symbol:false,timeframe:false})
const syncOptions=computed(()=>[{key:'crosshair',label:cw('crosshair')},{key:'viewport',label:cw('timeRange')},{key:'symbol',label:cw('symbol')},{key:'timeframe',label:cw('timeframe')}])
const periods=computed(()=>[{value:'1',label:cw('minute1')},{value:'5',label:cw('minute5')},{value:'15',label:cw('minute15')},{value:'30',label:cw('minute30')},{value:'60',label:cw('hour1')},{value:'240',label:cw('hour4')},{value:'D',label:cw('day')},{value:'W',label:cw('week')},{value:'M',label:cw('month')}])
const availablePeriods=computed(()=>periods.value.filter(p=>activeSymbol.value?.timeframes.includes(timeframes[p.value]!)))
const backendPeriod=computed(()=>timeframes[activeTimeframe.value]??activeTimeframe.value)
const indicatorsOpen=ref(false),indicatorQuery=ref(''),favoriteIndicators=ref<string[]>([]),favoritesOnly=ref(false)
const indicators=computed(()=>[{type:'sma',name:cw('sma')},{type:'ema',name:cw('ema')},{type:'bollinger-bands',name:cw('boll')},{type:'rsi',name:cw('rsi')},{type:'macd',name:'MACD'},{type:'average-true-range',name:cw('atr')},{type:'vwap',name:cw('vwap')},{type:'volume',name:cw('volume')}])
const filteredIndicators=computed(()=>indicators.value.filter(i=>i.name.toLowerCase().includes(indicatorQuery.value.toLowerCase())&&(!favoritesOnly.value||favoriteIndicators.value.includes(i.type))))
let quoteTimer:ReturnType<typeof setTimeout>|undefined,saveTimer:ReturnType<typeof setTimeout>|undefined,localTimer:ReturnType<typeof setTimeout>|undefined
let layoutVersion=0,restoring=false,disposed=false,dragIndex=-1,runEpoch=0
let layoutWrites:Promise<void>=Promise.resolve()
const pendingLayoutData=new Map<string,ReturnType<typeof snapshot>>()
let disposeDrawings:(()=>void)|undefined
let disposeLocale:(()=>void)|undefined
const engines=new Set<OpenTradingPineEngine>()
let editorReady=false
const pendingIndicators=new Set<IndicatorHandle>()
const pendingCancels=new Set<()=>void>()
const addLog=(message:string)=>{logs.value=[{time:Date.now(),message},...logs.value].slice(0,200)}
function fail(e:unknown){error.value=e instanceof Error?e.message:String(e);addLog(error.value)}
function openNavigation(){window.dispatchEvent(new Event('opentrading:open-navigation'))}
function projectActive(){const cell=workspace.value?.active;if(!cell)return;activeCell.value=cell.id;activeSymbolId.value=fromVela(cell.symbol);activeTimeframe.value=cell.timeframe;historyDepth.value=cell.chart.market.bars??1000;layout.value=workspace.value!.getState().layout;const status=provider.value?.statuses.get(activeSymbolId.value);feedStatus.value=status?.status??'connecting';feedError.value=status?.error??''}
function trackHistory(){
  for(const cell of workspace.value?.cells()??[]){
    if(historyCharts.has(cell.chart))continue;historyCharts.add(cell.chart)
    cell.chart.on('load:start',()=>{historyByCell.value[cell.id]={loaded:0,state:'loading'}})
    cell.chart.on('history:progress',e=>{historyByCell.value[cell.id]={loaded:e.loaded,state:'loading'}})
    cell.chart.on('history:complete',e=>{historyByCell.value[cell.id]={loaded:e.barsLoaded,state:e.reason}})
  }
}
const historyCharts=new WeakSet<import('@luxalgo/vela').Vela>()
function setHistoryDepth(depth:number){const ws=workspace.value;if(!ws)return;for(const cell of ws.cells())void cell.chart.setMarket({bars:depth});historyDepth.value=depth;dirty()}
async function recoverDraft(){if(!conflictDraft.value)return;restore(conflictDraft.value);await saveAsLayout();if(saveStatus.value==='saved'){conflictDraft.value=null;error.value=''}}
function displaySymbol(key:string){return symbols.value.find(s=>s.id===key)?.name??key.split(':').slice(-1)[0]}
function marketLabel(key:string){return key.includes(':usdm:')?cw('binancePerpetual'):key.startsWith('index:')?cw('index'):key.startsWith('okx:')?cw('okxSpot'):cw('binanceSpot')}
function priceText(value:unknown){return formatNumber(value,8)}
function quoteClass(key:string){return (quotes.value[key]?.change??0)<0?'cw-down':'cw-up'}
function setPeriod(tf:string){if(snapshotRun.value)returnLive();workspace.value?.context().setTimeframe(tf);projectActive()}
function applyChartTheme(){
  const ws=workspace.value;if(!ws)return
  const next=theme.value==='dark'?DARK_THEME:LIGHT_THEME,previous=theme.value==='dark'?LIGHT_THEME:DARK_THEME
  ws.setTheme(theme.value)
  // Saved renderer colors override the app theme. Migrate built-in palette values
  // while retaining the user's custom colors, candle styles and scale settings.
  for(const cell of ws.cells()){
    const config=cell.chart.renderer.getConfig() as any;if(!config)continue
    const migrate=(value:unknown,from:string,to:string)=>value===from?to:value
    cell.chart.renderer.applyConfig({
      layout:{background:migrate(config.layout?.background,previous.background,next.background),textColor:migrate(config.layout?.textColor,previous.textColor,next.textColor)},
      grid:{vertLines:{color:migrate(config.grid?.vertLines?.color,previous.gridColor,next.gridColor)},horzLines:{color:migrate(config.grid?.horzLines?.color,previous.gridColor,next.gridColor)}},
      priceScale:{borderColor:migrate(config.priceScale?.borderColor,previous.borderColor,next.borderColor)},
      panes:{separatorColor:migrate(config.panes?.separatorColor,previous.borderColor,next.borderColor)},
    })
  }
}
function setLayout(value:string){workspace.value?.setLayout(value);applyChartTheme();projectActive()}
function setSync(key:string,on:boolean){sync.value[key]=on;workspace.value?.sync.set(key as 'symbol',on)}
function selectSymbol(id:string){const info=symbols.value.find(s=>s.id===id);if(!info)return;const context=workspace.value?.context();if(!context)return;if(!info.timeframes.includes(backendPeriod.value))context.setTimeframe('D');if(snapshotRun.value)returnLive();context.setSymbol(velaSymbol(id));if(info.close_only)context.setPriceStyle('line');else context.setPriceStyle('candles');projectActive();void refreshQuotes()}
function pickSearch(id:string){if(searchMode.value==='watchlist')void persistWatch([...new Set([...watchSymbols.value,id])]);else selectSymbol(id);searchOpen.value=false}
async function persistWatch(items:string[]){
  const d=watchlist.value;if(!d)return
  d.data={...d.data,symbols:[...items]};pendingWatch.value=[...new Set([...pendingWatch.value,d.id])]
  await writeDraft('watch:'+d.id,{version:d.version,data:d.data,pending:true})
  watchSave=watchSave.then(async()=>{
    const current=watchlists.value.find(w=>w.id===d.id);if(!current)return
    try{
      const data={...current.data},saved=await chartApi.save('watchlists',d.id,{name:current.name,data,expected_version:current.version})
      current.version=saved.version
      const pending=JSON.stringify(data)!==JSON.stringify(current.data)
      await writeDraft('watch:'+d.id,{version:current.version,data:current.data,pending})
      if(!pending)pendingWatch.value=pendingWatch.value.filter(id=>id!==d.id)
      await refreshQuotes()
    }catch(e){fail(e)}
  })
  await watchSave
}
function removeWatch(id:string){void persistWatch(watchSymbols.value.filter(k=>k!==id))}
function moveWatch(index:number){if(dragIndex<0)return;const list=[...watchSymbols.value];const item=list.splice(dragIndex,1)[0];if(item)list.splice(index,0,item);dragIndex=-1;void persistWatch(list)}
async function newWatchlist(){const name=await requestName(cw('watchlistName'),cw('newWatchlist'));if(!name)return;try{const d=await chartApi.save('watchlists',crypto.randomUUID(),{name,data:{symbols:[]},expected_version:0});watchlists.value.push(d);watchlistId.value=d.id}catch(e){fail(e)}}
async function renameWatchlist(){if(!watchlist.value)return;const name=await requestName(cw('watchlistName'),watchlist.value.name);if(!name)return;try{const d=watchlist.value;const saved=await chartApi.save('watchlists',d.id,{name,data:d.data,expected_version:d.version});watchlists.value=watchlists.value.map(w=>w.id===d.id?saved:w)}catch(e){fail(e)}}
async function refreshQuotes(){clearTimeout(quoteTimer);if(disposed)return;try{const keys=[...new Set([...watchSymbols.value,activeSymbolId.value])];for(let i=0;i<keys.length;i+=100){const data=await chartApi.quotes(keys.slice(i,i+100));for(const q of data)quotes.value[q.id]=q}}catch(e){addLog(String(e))}finally{if(!disposed)quoteTimer=setTimeout(refreshQuotes,5000)}}
function snapshot(){const state=workspace.value?.getState();if(state)for(const saved of state.charts){const live=workspace.value?.cells().find(c=>c.id===saved.id);if(live)saved.bars=live.chart.market.bars??saved.bars}return {state,rightWidth:rightWidth.value,rightOpen:rightOpen.value,bottomHeight:bottomHeight.value,watchlistId:watchlistId.value,favoriteIndicators:favoriteIndicators.value}}
function dirty(){if(restoring||!workspace.value)return;saveStatus.value='saving';clearTimeout(saveTimer);const data=snapshot();pendingLayoutData.set(layoutId.value,data);void writeDraft('layout:'+layoutId.value,{version:layoutVersion,data,pending:true}).catch(fail);saveTimer=setTimeout(saveNow,700)}
async function saveNow(){
  clearTimeout(saveTimer);if(!workspace.value||restoring)return
  const id=layoutId.value,data=snapshot()
  pendingLayoutData.set(id,data);saveStatus.value='saving'
  layoutWrites=layoutWrites.then(async()=>{
    try{
      const previous=layouts.value.find(l=>l.id===id)
      const doc=await chartApi.save('layouts',id,{name:previous?.name??cw('defaultLayout'),data,expected_version:previous?.version??0})
      layouts.value=[doc,...layouts.value.filter(l=>l.id!==id)]
      const latest=pendingLayoutData.get(id)??data,pending=JSON.stringify(latest)!==JSON.stringify(data)
      await writeDraft('layout:'+id,{version:doc.version,data:latest,pending})
      if(layoutId.value===id){layoutVersion=doc.version;saveStatus.value=pending?'saving':'saved'}
    }catch(e){if(layoutId.value===id)saveStatus.value='unsaved';fail(e)}
  })
  await layoutWrites
}
async function switchLayout(id:string){
  await saveNow()
  try{
    const latest=await chartApi.documents('layouts'),doc=latest.find(l=>l.id===id)
    if(!doc)return
    layouts.value=latest;layoutId.value=id;layoutVersion=doc.version;error.value='';conflictDraft.value=null
    restore(doc.data);await writeDraft('last-layout',id)
  }catch(e){fail(e)}
}
async function saveAsLayout(){await saveNow();const name=await requestName(cw('layoutName'),cw('myLayout'));if(!name)return;try{const doc=await chartApi.save('layouts',crypto.randomUUID(),{name,data:snapshot(),expected_version:0});layouts.value.push(doc);layoutId.value=doc.id;layoutVersion=doc.version;await writeDraft('last-layout',doc.id);saveStatus.value='saved'}catch(e){fail(e)}}
function restore(data:Record<string,any>){data=migrateWorkspaceState(data);restoring=true;try{if(data.state)workspace.value?.applyState(data.state);applyChartTheme();rightWidth.value=data.rightWidth??300;rightOpen.value=data.rightOpen??true;bottomHeight.value=data.bottomHeight??340;watchlistId.value=data.watchlistId??watchlists.value[0]?.id??'default';favoriteIndicators.value=data.favoriteIndicators??[];const state=workspace.value?.getState();if(state){layout.value=state.layout;for(const k of Object.keys(sync.value))sync.value[k]=!!state.sync?.[k as 'symbol']}projectActive()}finally{restoring=false}}
function toggleBottom(tab:string){bottomTab.value=bottomTab.value===tab?'':tab}
function resize(start:PointerEvent,update:(dx:number,dy:number)=>void){const x=start.clientX,y=start.clientY;const move=(e:PointerEvent)=>update(e.clientX-x,e.clientY-y);const stop=()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',stop);dirty()};window.addEventListener('pointermove',move);window.addEventListener('pointerup',stop,{once:true});start.preventDefault()}
function resizeRight(e:PointerEvent){const width=rightWidth.value;resize(e,dx=>{rightWidth.value=Math.max(240,Math.min(520,width-dx))})}
function resizeBottom(e:PointerEvent){const height=bottomHeight.value;resize(e,(_,dy)=>{bottomHeight.value=Math.max(180,Math.min(window.innerHeight-180,height-dy))})}
function toggleFavorite(type:string){favoriteIndicators.value=favoriteIndicators.value.includes(type)?favoriteIndicators.value.filter(t=>t!==type):[...favoriteIndicators.value,type];dirty()}
function addNative(type:string){try{workspace.value?.context().addNativeIndicator(type);indicatorsOpen.value=false}catch(e){fail(e)}}
async function openScript(){const script=selectedScript.value;if(!script)return;const draft=await readDraft<{source:string}>('script:'+script.id);source.value=script.readonly&&!draft?.source?.trim()?String(script.data.source):draft?.source??String(script.data.source);editorReady=true;scriptDirty.value=source.value!==script.data.source;pineError.value=null}
function newScript(kind:string){editorReady=true;scriptId.value='';source.value=kind==='indicator'?'//@version=6\nindicator("'+cw('myIndicator')+'", overlay=true)\nlength = input.int(20, "'+cw('timeframe')+'")\nplot(ta.ema(close, length), color=color.orange)\n':'//@version=6\nstrategy("'+cw('crossStrategy')+'", overlay=true, initial_capital=10000)\nfast = ta.ema(close, input.int(10, "'+cw('fast')+'"))\nslow = ta.ema(close, input.int(30, "'+cw('slow')+'"))\nplot(fast, color=color.orange)\nplot(slow, color=color.blue)\nif ta.crossover(fast, slow)\n    strategy.entry("Long", strategy.long)\nif ta.crossunder(fast, slow)\n    strategy.close("Long")\n';scriptDirty.value=true;bottomTab.value='editor'}
async function saveScript(asNew:boolean):Promise<WorkspaceDocument|undefined>{
  try{const old=selectedScript.value;const needsName=asNew||!old||old.readonly;const name=needsName?await requestName(cw('scriptName'),old?cw('copyName',{name:old.name}):cw('myScript')):old.name;if(!name)return;const id=needsName?crypto.randomUUID():old!.id;const saved=await chartApi.save('scripts',id,{name,data:{source:source.value,language:'pine'},expected_version:needsName?0:old!.version});scripts.value=[saved,...scripts.value.filter(s=>s.id!==id)];scriptId.value=id;scriptDirty.value=false;await writeDraft('script:'+id,{source:source.value});return saved}catch(e){fail(e)}
}
async function addPine(){
  const cell=workspace.value?.active;if(!cell)return
  let script=selectedScript.value
  if(scriptDirty.value||!script){script=await saveScript(false);if(!script)return}
  const code=source.value,epoch=++runEpoch;executing.value=true;pineError.value=null
  try{
    checkPine(code)
    const id=crypto.randomUUID()
    workspace.value!.context().addIndicator({script:code,name:script.name,id,language:'pine'})
    const handle=cell.chart.indicators().find(h=>h.id===id)
    if(!handle)throw new Error(cw('cannotCreateIndicator'))
    pendingIndicators.add(handle)
    const result=await new Promise<{ok:boolean;handle:IndicatorHandle|null;error:Error|null}>(resolve=>{
      const finish=(error:Error|null)=>{clearTimeout(timer);ready();failed();pendingCancels.delete(cancel);if(error)handle.remove();resolve({ok:!error,handle:error?null:handle,error})}
      const cancel=()=>finish(new Error(cw('runCancelled')))
      const timer=setTimeout(()=>finish(new Error(cw('scriptTimeout'))),65000)
      const ready=handle.on('ready',()=>finish(null))
      const failed=handle.on('error',({error})=>finish(error))
      pendingCancels.add(cancel)
    })
    pendingIndicators.delete(handle)
    if(epoch!==runEpoch){result.handle?.remove();return}
    if(!result.ok||!result.handle)throw result.error??new Error(cw('scriptFailed'))
    markScript(cell.chart,id,script.id,script.version)
    scriptRunning.value=cw('scriptAdded',{version:script.version,cell:cell.id})
    addLog(cw('scriptRunLog',{name:script.name,version:script.version,cell:cell.id}));dirty()
  }catch(e){const value=e as Error&{line?:number;column?:number};pineError.value={message:value.message??String(e),line:value.line,column:value.column};scriptRunning.value=cw('keptPrevious');fail(e)}finally{if(epoch===runEpoch)executing.value=false}
}
function cancelPine(){runEpoch++;executing.value=false;for(const cancel of pendingCancels)cancel();pendingCancels.clear();pendingIndicators.clear();addLog(cw('stoppedAdding'))}
async function importScript(event:Event){const file=(event.target as HTMLInputElement).files?.[0];if(file){editorReady=true;scriptId.value='';source.value=await file.text();scriptDirty.value=true;bottomTab.value='editor';(event.target as HTMLInputElement).value=''}}
function exportScript(){const url=URL.createObjectURL(new Blob([source.value],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=(selectedScript.value?.name??'indicator')+'.pine';a.click();URL.revokeObjectURL(url)}
async function locateTrade({time,run}:{time:number;run:PineRun}){
  const cell=workspace.value?.active;if(!cell)return
  selectSymbol(run.request.symbol)
  setPeriod(Object.keys(timeframes).find(k=>timeframes[k]===run.request.timeframe)??'60')
  // Load the original interval so an older run remains locatable after today's chart moves on.
  const first=await chartApi.records(run.id,'bars',0,10000),bars=[...first.items]
  for(let offset=bars.length;offset<first.total;offset+=10000)bars.push(...(await chartApi.records(run.id,'bars',offset,10000)).items)
  if(workspace.value?.active!==cell)return
  await cell.chart.setMarket({symbol:velaSymbol(run.request.symbol),timeframe:cell.timeframe,data:bars as unknown as import('@luxalgo/vela').OHLCV[]})
  snapshotChart=cell.chart;snapshotRun.value=run.id
  cell.chart.setVisibleRange({from:time-12*3600000,to:time+12*3600000})
  addLog(cw('locatedTrade',{run:run.id.slice(0,8),time:formatDate(time)}))
}
async function initialize(){
  if(workspace.value)return;loading.value=true;error.value=''
  try{
    const results=await Promise.all([chartApi.symbols(),chartApi.documents('watchlists'),chartApi.documents('scripts'),chartApi.documents('layouts')])
    if(disposed)return
    ;[symbols.value,watchlists.value,scripts.value,layouts.value]=results
    for(const list of watchlists.value){const local=await readDraft<{version:number;data:Record<string,any>;pending:boolean}>('watch:'+list.id);if(local?.pending){if(local.version===list.version){list.data=local.data;pendingWatch.value.push(list.id)}else error.value=cw('watchConflict')}}
    const last=await readDraft<string>('last-layout');const doc=layouts.value.find(l=>l.id===last)??layouts.value[0]
    layoutId.value=doc?.id??'default';layoutVersion=doc?.version??0
    const local=await readDraft<{version:number;data:Record<string,any>;pending:boolean}>('layout:'+layoutId.value)
    provider.value=new OpenTradingProvider((symbol,status,message)=>{if(symbol===activeSymbolId.value){feedStatus.value=status;feedError.value=message??''}})
    provider.value.catalog=symbols.value
    const ws=new VelaWorkspace(chartHost.value!,{layout:'1',symbol:velaSymbol('binance:spot:BTCUSDT'),timeframe:'60',bars:1000,
      live:true,theme:theme.value,volume:true,timezone:'Asia/Shanghai',watermark:false,layoutMode:'desktop',persist:false,
      sync:{viewport:true,crosshair:true},topbar:{left:['style','undo-redo'],right:['panels']},
      drawings:{tools:['trendline','ray','hline','vline','parallelchannel','box','fibretracement','text','arrow','freehand','datepricerange']},
      providers:{opentrading:()=>provider.value!},engines:{pine:()=>{const engine=new OpenTradingPineEngine(()=>symbols.value);engines.add(engine);return engine}},
    })
    workspace.value=ws;trackHistory();ws.on('cell:created',trackHistory);disposeDrawings=installMarketDrawings(ws,dirty);disposeLocale=localizeChart(chartHost.value!)
    if(doc)restore(doc.data)
    ws.sync.set('drawings',false)
    if(local?.pending){if(local.version===layoutVersion){restore(local.data);saveStatus.value='unsaved';dirty()}else{conflictDraft.value=local.data;saveStatus.value='unsaved';error.value=cw('layoutConflict')}}
    ws.on('state:changed',()=>{projectActive();dirty()});ws.on('cell:active',projectActive);ws.on('layout:changed',projectActive)
    ws.on('script:run',event=>{if(event.first)for(const warning of event.warnings)addLog(String(warning.message))})
    const lastScript=await readDraft<string>('last-script')
    if(lastScript===''){const draft=await readDraft<{source:string}>('script:new');if(draft){scriptId.value='';source.value=draft.source;editorReady=true;scriptDirty.value=true}else await openScript()}
    else{if(lastScript&&scripts.value.some(s=>s.id===lastScript))scriptId.value=lastScript;await openScript()}
    projectActive();void refreshQuotes()
  }catch(e){fail(e)}finally{loading.value=false}
}
watch(source,value=>{if(!editorReady)return;scriptDirty.value=value!==selectedScript.value?.data.source;clearTimeout(localTimer);localTimer=setTimeout(()=>void writeDraft('script:'+(scriptId.value||'new'),{source:value}).catch(fail),400)})
watch(scriptId,value=>void writeDraft('last-script',value).catch(fail))
watch(bottomTab,value=>{if(value==='editor')editorMounted.value=true;if(value==='tester')testerMounted.value=true;void nextTick(()=>workspace.value?.resize())})
watch(theme,applyChartTheme)
watch([rightOpen,rightWidth,bottomHeight,watchlistId],()=>{dirty();void nextTick(()=>workspace.value?.resize())})
watch(watchlistId,()=>void refreshQuotes())
onMounted(initialize)
onBeforeUnmount(()=>{finishName(false);cancelPine();disposed=true;clearTimeout(quoteTimer);clearTimeout(localTimer);clearTimeout(saveTimer);if(editorReady)void writeDraft('script:'+(scriptId.value||'new'),{source:source.value});void saveNow();disposeLocale?.();workspace.value?.destroy();disposeDrawings?.();provider.value?.destroy();for(const engine of engines)engine.terminate()})
</script>

<style>
.cw-name-dialog{width:360px;background:var(--cw-panel);padding:20px;border:1px solid var(--cw-border);border-radius:8px}.cw-name-dialog label{display:flex;flex-direction:column;gap:12px}.cw-name-dialog footer{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}
.cw-capabilities>div{padding:0 18px 18px;overflow:auto;line-height:1.6}.cw-capabilities h3{font-size:13px;margin:15px 0 7px}.cw-capabilities p{margin:5px 0;color:var(--cw-muted)}
.cw-no-drawing-sync{display:none!important}
.chart-workspace{--cw-bg:#fff;--cw-panel:#fafbfc;--cw-border:#e0e3e8;--cw-text:#202631;--cw-muted:#7a8492;--cw-hover:#eef1f6;--cw-accent:#128b78;display:flex;flex-direction:column;height:100%;min-height:400px;background:var(--cw-bg);color:var(--cw-text);font-family:inherit;font-size:12px;overflow:hidden}.chart-workspace.cw-dark{--cw-bg:var(--ui-canvas);--cw-panel:var(--ui-toolbar);--cw-border:var(--ui-border);--cw-text:var(--ui-text);--cw-muted:var(--ui-muted);--cw-hover:var(--ui-hover);--cw-accent:var(--ui-accent)}.chart-workspace button,.chart-workspace select,.chart-workspace input{font:inherit;color:inherit;background:transparent;border:1px solid transparent;border-radius:4px;min-height:28px}.chart-workspace button{padding:3px 7px;cursor:pointer;white-space:nowrap}.chart-workspace button:hover{background:var(--cw-hover)}.chart-workspace button:disabled{opacity:.45;cursor:default}.chart-workspace input,.chart-workspace select{border-color:var(--cw-border);padding:4px 7px;background:var(--cw-panel);max-width:100%}.chart-workspace input[type=checkbox]{min-height:0}.chart-workspace button.active{color:var(--cw-accent);background:var(--cw-hover)}.chart-workspace button:focus-visible,.chart-workspace select:focus-visible,.chart-workspace input:focus-visible{outline:2px solid var(--cw-accent);outline-offset:1px}.cw-header{height:48px;min-height:48px;display:flex;align-items:center;gap:5px;padding:0 10px;border-bottom:1px solid var(--cw-border);background:var(--cw-panel);z-index:4}.cw-brand{font-family:Georgia,serif;font-size:18px;margin-right:9px}.cw-symbol{font-weight:600!important;font-size:14px!important}.cw-symbol small{font-weight:400;color:var(--cw-muted);font-size:10px}.cw-periods{display:flex;border-left:1px solid var(--cw-border);border-right:1px solid var(--cw-border);padding:0 5px}.cw-spacer{flex:1}.cw-body{display:flex;flex:1;min-height:0}.cw-center{flex:1;min-width:0;display:flex;flex-direction:column;position:relative}.cw-chart{min-height:100px;flex:1;position:relative;overflow:hidden}.cw-watchlist{display:flex;flex-direction:column;background:var(--cw-panel);min-width:240px;max-width:520px}.cw-watchlist>header,.cw-search>header,.cw-indicator-picker>header{display:flex;gap:3px;padding:10px;border-bottom:1px solid var(--cw-border);align-items:center;justify-content:space-between}.cw-watchlist>header select{flex:1;min-width:60px}.cw-watch-scroll{overflow:auto;flex:1;min-height:120px}.cw-watch-scroll table{width:100%;border-collapse:collapse}.cw-watch-scroll th{position:sticky;top:0;background:var(--cw-panel);color:var(--cw-muted);font-weight:400;text-align:right;padding:8px 5px}.cw-watch-scroll th:first-child{text-align:left;padding-left:12px}.cw-watch-scroll td{padding:7px 5px;text-align:right;border-bottom:1px solid var(--cw-border)}.cw-watch-scroll td:first-child{text-align:left;padding-left:12px}.cw-watch-scroll small{display:block;font-size:10px;color:var(--cw-muted);margin-top:3px}.cw-watch-scroll tr{cursor:pointer}.cw-watch-scroll tr.selected{background:var(--cw-hover);box-shadow:inset 3px 0 var(--cw-accent)}.cw-watch-scroll tbody tr:hover{background:var(--cw-hover)}.cw-remove{opacity:0;padding:0!important;min-width:16px}.cw-watch-scroll tr:hover .cw-remove,.cw-remove:focus{opacity:1}.cw-up{color:#16a18c!important}.cw-down{color:#ef4a60!important}.cw-instrument{padding:18px 14px;border-top:1px solid var(--cw-border);min-height:220px}.cw-instrument>strong{font-size:17px}.cw-instrument>small{display:block;margin-top:6px;color:var(--cw-muted)}.cw-last{font-size:28px;margin:22px 0 16px;font-variant-numeric:tabular-nums}.cw-last small{font-size:11px;color:var(--cw-muted)}.cw-instrument dl{display:grid;grid-template-columns:1fr 1fr;gap:8px}.cw-instrument dt{color:var(--cw-muted)}.cw-instrument dd{text-align:right}.cw-instrument>button{margin-top:16px}.cw-vertical-resizer{width:4px;background:var(--cw-border);cursor:col-resize;flex-shrink:0}.cw-horizontal-resizer{height:4px;background:var(--cw-border);cursor:row-resize;position:absolute;top:-2px;width:100%;z-index:5}.cw-bottom{flex-shrink:0;display:flex;flex-direction:column;position:relative;border-top:1px solid var(--cw-border);min-height:34px}.cw-bottom-tabs{display:flex;align-items:center;gap:12px;min-height:33px;padding:0 10px;background:var(--cw-panel);border-bottom:1px solid var(--cw-border)}.cw-bottom-tabs small,.cw-version{color:var(--cw-muted)}.cw-feed{font-size:10px;color:var(--cw-accent)}.cw-editor-panel{display:flex;flex:1;min-height:0;flex-direction:column}.cw-editor-panel[style*="display: none"]{display:none}.cw-editor-tools{display:flex;align-items:center;gap:5px;padding:5px 10px;min-height:38px;border-bottom:1px solid var(--cw-border)}.cw-editor-tools select{max-width:260px}.cw-primary{background:var(--cw-accent)!important;color:white!important;padding:5px 12px!important}.cw-notice{display:flex;gap:10px;align-items:center;background:#703d1a22;color:#c78131;padding:6px 14px;z-index:5}.cw-notice span{flex:1}.cw-loading{position:absolute;inset:60px 0 40px;display:grid;place-items:center;pointer-events:none;background:var(--cw-bg);z-index:3;color:var(--cw-muted)}.cw-sync{position:relative;padding:4px;cursor:pointer}.cw-sync>div{position:absolute;top:32px;left:0;width:145px;background:var(--cw-panel);border:1px solid var(--cw-border);padding:12px;z-index:25;box-shadow:0 8px 30px #0003}.cw-sync label{display:flex;gap:8px;padding:5px}.cw-log{overflow:auto;padding:10px 16px;color:var(--cw-muted);line-height:1.8}.cw-error{color:#e35b6a;padding:5px 12px}.cw-modal-backdrop{position:fixed;inset:0;background:#0008;z-index:90;display:grid;place-items:center}.cw-search{width:560px;max-width:90vw;height:560px;max-height:85vh;background:var(--cw-bg);border:1px solid var(--cw-border);border-radius:8px;box-shadow:0 20px 80px #0006;display:flex;flex-direction:column}.cw-search>input{margin:12px;min-height:36px}.cw-market-filter{display:flex;gap:8px;padding:0 12px 10px}.cw-search-results{overflow:auto;padding:0 10px}.cw-search-results>button{display:flex;align-items:center;width:100%;text-align:left;padding:11px;border-bottom:1px solid var(--cw-border);gap:14px}.cw-search-results strong{flex:1}.cw-search-results span,.cw-search-results small{color:var(--cw-muted)}.cw-indicator-picker{position:absolute;left:25%;top:12px;width:310px;z-index:15;background:var(--cw-panel);border:1px solid var(--cw-border);box-shadow:0 10px 35px #0005;padding-bottom:8px}.cw-indicator-picker>input{margin:10px;width:calc(100% - 20px)}.cw-indicator-picker>label{display:flex;align-items:center;gap:6px;margin:0 12px 10px}.cw-indicator-row{display:flex;align-items:center;padding:1px 8px}.cw-indicator-row>button:last-child{flex:1;text-align:left}.cw-chart .vela-workspace{height:100%!important}.cw-chart .vela-topbar{min-height:32px!important}.cw-chart .vela-topbar:empty{display:none}@media(max-width:1250px){.cw-brand{display:none}.cw-periods button{padding:3px 5px}.cw-version{display:none}.cw-header{gap:2px}}@media(max-width:950px){.cw-watchlist,.cw-vertical-resizer{display:none}.cw-header{overflow-x:auto}.cw-bottom-tabs{gap:3px}}

.cw-icon{display:inline-block;width:16px;height:16px;flex-shrink:0;vertical-align:middle}
.cw-starred{fill:currentColor}
.chart-workspace button:focus-visible,.chart-workspace select:focus-visible,.chart-workspace input:focus-visible,.chart-workspace summary:focus-visible{outline:2px solid var(--cw-accent);outline-offset:1px}
.cw-symbol{display:inline-flex;align-items:center;gap:5px}
.cw-name-dialog{max-width:calc(100vw - 24px)}
.cw-search>header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid var(--cw-border)}
.cw-search-results>button{min-width:0}
.cw-search-results strong{min-width:0;overflow-wrap:anywhere}
.cw-search-results small{flex-shrink:0}
.cw-bottom-tabs{min-width:0}
.cw-bottom-tabs>button{flex-shrink:0}
.cw-editor-tools{flex-wrap:wrap;flex-shrink:0}
.cw-indicator-picker{max-width:calc(100% - 24px);left:50%;transform:translateX(-50%);max-height:calc(100% - 24px);overflow:auto}
@media(max-width:767px){
  .chart-workspace{min-height:0}
  .cw-header{min-height:44px;scrollbar-width:thin;overscroll-behavior-inline:contain}
  .cw-header button,.cw-header select{min-height:36px}
  .cw-menu{min-width:40px}
  .cw-bottom-tabs{overflow-x:auto;overscroll-behavior-inline:contain;min-height:40px}
  .cw-bottom-tabs>.cw-spacer,.cw-bottom-tabs>.cw-feed,.cw-bottom-tabs>small{display:none}
  .cw-bottom-tabs>button{min-height:36px;padding-inline:10px}
  .cw-search>input{min-height:44px}
  .cw-market-filter{flex-wrap:wrap}
  .cw-search-results>button{gap:8px}
  .cw-notice{flex-wrap:wrap}
  .cw-notice span{flex-basis:100%;overflow-wrap:anywhere}
}

.cw-body{position:relative}
.cw-watch-backdrop{position:absolute;inset:0;z-index:29;background:#0005!important;border-radius:0!important}
.cw-watchlist{outline:none}
@media(max-width:950px){
  .cw-watchlist{display:flex!important;position:absolute;inset-block:0;right:0;z-index:30;max-width:calc(100% - 32px);box-shadow:-8px 0 24px #0003}
  .cw-chart .vela-panel{position:absolute;right:0;inset-block:0;z-index:12;max-width:calc(100% - 48px);box-shadow:-6px 0 20px #0002}
}
</style>
