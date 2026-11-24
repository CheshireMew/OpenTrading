<template>
  <section @keydown.esc="indicatorsOpen = false" class="chart-workspace" :class="{ 'cw-dark':theme==='dark' }">
    <header class="cw-header">
      <button class="cw-symbol" aria-haspopup="dialog" :aria-expanded="searchOpen && searchMode==='chart'" @click="searchOpen=true;searchMode='chart'">{{ activeSymbol?.name??cw('selectSymbol') }} <small>{{ cw(activeSymbol?.market==='usdm'?'perpetual':activeSymbol?.market==='index'?'index':'spot') }}</small><MagnifyingGlassIcon class="cw-icon" aria-hidden="true" /></button>
      <div class="cw-periods"><button v-for="tf in availablePeriods" :key="tf.value" :class="{active:activeTimeframe===tf.value}" :aria-pressed="activeTimeframe===tf.value" @click="setPeriod(tf.value)">{{ tf.label }}</button></div>
      <button ref="indicatorTrigger" :aria-expanded="indicatorsOpen" @click="indicatorsOpen=!indicatorsOpen"><AdjustmentsHorizontalIcon class="cw-icon" aria-hidden="true" /> {{ cw('indicators') }}</button>
      <button type="button" :aria-expanded="alertsController.open.value" @click="alertsController.show()"><BellIcon class="cw-icon" aria-hidden="true" /> {{ cw('priceAlerts') }}</button>
      <WorkspacePopover class="cw-sync" :label="cw('settings')"><div><label>{{ cw('historyDepth') }} <select :aria-label="cw('historyDepth')" :value="historyDepth" @change="setHistoryDepth(Number(($event.target as HTMLSelectElement).value))"><option :value="1000">1,000</option><option :value="5000">5,000</option><option :value="10000">10,000</option></select></label><button @click="workspace?.chart.renderer.set('logScale',!workspace.chart.renderer.get('logScale'))">{{ cw('priceScale') }}</button></div></WorkspacePopover>
      <select :aria-label="cw('layout')" :value="layout" @change="setLayout(($event.target as HTMLSelectElement).value)"><option value="1">{{ cw('single') }}</option><option value="2h">{{ cw('horizontal') }}</option><option value="2v">{{ cw('vertical') }}</option><option value="4">{{ cw('four') }}</option></select>
      <WorkspacePopover class="cw-sync" :label="cw('sync')"><div><label v-for="link in syncOptions" :key="link.key"><input type="checkbox" :checked="sync[link.key]" @change="setSync(link.key,($event.target as HTMLInputElement).checked)" />{{ link.label }}</label></div></WorkspacePopover>
      <span class="cw-spacer" /><button @click="saveNow">{{ cw(saveStatus) }}</button><button @click="saveAsLayout">{{ cw('saveLayoutAs') }}</button>
      <select v-if="layouts.length>1" :aria-label="cw('savedLayouts')" :value="layoutId" @change="switchLayout(($event.target as HTMLSelectElement).value)"><option v-for="item in layouts" :key="item.id" :value="item.id">{{ item.name }}</option></select>
      <button @click="toggleTheme" :aria-label="cw('toggleTheme')"><SunIcon v-if="theme==='dark'" class="cw-icon" aria-hidden="true" /><MoonIcon v-else class="cw-icon" aria-hidden="true" /></button><button @click="toggleWatchlist" :aria-expanded="watchlistVisible">{{ cw('watchlist') }}</button>
    </header>
    <div v-if="error" class="cw-notice" role="alert"><span>{{ messageText(error) }}</span><button @click="clearError">{{ cw('close') }}</button><button v-if="!workspace" @click="initialize">{{ cw('reload') }}</button></div>
    <div v-if="snapshotRun" class="cw-notice"><span>{{ cw('viewingSnapshot',{run:snapshotRun.slice(0,8)}) }}</span><button @click="returnLive">{{ cw('returnLive') }}</button></div>
    <div class="cw-body">
      <div class="cw-center">
        <div ref="chartHost" class="cw-chart" />
        <div v-if="loading" class="cw-loading" role="status" aria-live="polite">{{ cw('loadingChart') }}</div>
        <WorkspaceIndicatorPicker v-model="indicatorsOpen" :workspace="workspace" :scripts="scripts" :favorites="favoriteIndicators" :busy="executing" @native="addNative" @script="execution.addSavedScript" @edit="editIndicatorScript" @favorite="toggleFavorite" @editor="bottomTab='editor'" />
        <div class="cw-bottom" :style="{height:bottomTab?bottomHeight+'px':'34px'}">
          <div v-if="bottomTab" class="cw-horizontal-resizer" role="separator" aria-orientation="horizontal" tabindex="0" :aria-valuenow="bottomHeight" :aria-valuemin="180" :aria-valuemax="maxBottomHeight" :aria-label="cw('resizeBottom')" @keydown.up.prevent="bottomHeight=Math.min(maxBottomHeight,bottomHeight+20)" @keydown.down.prevent="bottomHeight=Math.max(180,bottomHeight-20)" @pointerdown="resizeBottom" />
          <nav class="cw-bottom-tabs"><button :aria-expanded="bottomTab==='editor'" :class="{active:bottomTab==='editor'}" @click="toggleBottom('editor')">{{ cw('pineEditor') }}</button><button :aria-expanded="bottomTab==='tester'" :class="{active:bottomTab==='tester'}" @click="toggleBottom('tester')">{{ cw('strategyTester') }}</button><button :aria-expanded="bottomTab==='logs'" :class="{active:bottomTab==='logs'}" @click="toggleBottom('logs')">{{ cw('runLogs') }} <small>{{ logs.length||'' }}</small></button><span class="cw-spacer" /><span class="cw-feed" :title="messageText(feedError)">● {{ feedText }}</span><small>{{ cw('activeChart',{cell:activeCell}) }} · {{ activeSymbol?.currency }} · {{ historyText }}</small><button v-if="bottomTab" :aria-label="cw('close')" @click="bottomTab=''"><ChevronDownIcon class="cw-icon" aria-hidden="true" /></button></nav>
          <div v-show="bottomTab==='editor'" class="cw-editor-panel">
            <div class="cw-editor-tools"><select v-model="scriptId" :aria-label="cw('myScript')" @change="openScript"><option v-for="item in scripts" :key="item.id" :value="item.id">{{ item.name }}{{ item.readonly?' · '+cw('original'):'' }}</option></select><button @click="newScript('indicator')">{{ cw('newIndicator') }}</button><button @click="newScript('strategy')">{{ cw('newStrategy') }}</button><button @click="saveScript(false)">{{ cw('save') }}</button><button @click="saveScript(true)">{{ cw('saveAs') }}</button><button @click="importFile?.click()">{{ cw('import') }}</button><button @click="exportScript">{{ cw('export') }}</button><button @click="showCapabilities">{{ cw('compatibility') }}</button><input ref="importFile" type="file" accept=".pine,text/plain" hidden @change="importScript" /><span class="cw-spacer" /><span class="cw-version">{{ scriptDirty?cw('draft'):selectedScript?cw('version',{version:selectedScript.version}):'' }} {{ scriptRunning?'· '+messageText(scriptRunning):'' }}</span><button class="cw-primary" :disabled="executing" @click="addPine">{{ cw(executing?'calculating':'addToActive') }}</button><button v-if="executing" @click="cancelPine">{{ cw('stop') }}</button></div>
            <div v-if="scriptConflict" role="alert" class="cw-editor-tools"><span>{{ cw('scriptConflict') }}</span><button @click="useSavedScript">{{ cw('useSavedScript') }}</button><button @click="saveScript(true)">{{ cw('saveAs') }}</button></div>
            <PineEditor v-if="editorMounted" v-model="source" :dark="theme==='dark'" :read-only="scriptLoading" :error="pineError" @run="addPine" @save="saveScript(false)" />
          </div>
          <StrategyTester v-if="testerMounted" v-show="bottomTab==='tester'" :symbol="activeSymbol" :timeframe="backendPeriod" :script="selectedScript" :dark="theme==='dark'" @locate="locateTrade" @log="addLog" />
          <div v-if="bottomTab==='logs'" class="cw-log"><p v-if="!logs.length">{{ cw('noLogs') }}</p><p v-for="(item,index) in logs" :key="index">{{ formatDate(item.time,true) }}  {{ messageText(item.message) }}</p></div>
        </div>
      </div>
      <div v-if="rightOpen && !compactWorkspace" class="cw-vertical-resizer" role="separator" aria-orientation="vertical" tabindex="0" :aria-valuenow="rightWidth" :aria-valuemin="320" :aria-valuemax="520" :aria-label="cw('resizeWatchlist')" @keydown.left.prevent="rightWidth=Math.min(520,rightWidth+20)" @keydown.right.prevent="rightWidth=Math.max(320,rightWidth-20)" @pointerdown="resizeRight" />
      <WorkspaceWatchlist :controller="listsController" :symbols="symbols" :active-symbol-id="activeSymbolId"
        :visible="watchlistVisible" :compact="compactWorkspace" :width="rightWidth"
        @select="selectSymbol" @add="searchMode='watchlist';searchOpen=true" @close="watchlistDrawerOpen=false">
        <template #actions>
          <button type="button" @click="workspace?.context().togglePanel('objects')">{{ cw('objects') }}</button>
          <button type="button" @click="workspace?.context().togglePanel('dataWindow')">{{ cw('dataWindow') }}</button>
        </template>
      </WorkspaceWatchlist>
    </div>
    <WorkspaceNamePrompt ref="namePrompt" />
    <WorkspacePriceAlerts :controller="alertsController" />
    <div v-if="capabilitiesOpen" class="cw-modal-backdrop" @click.self="capabilitiesOpen=false"><section ref="capabilitiesDialogRef" tabindex="-1" class="cw-search cw-capabilities" role="dialog" aria-modal="true" :aria-label="cw('pineCompatibility')"><header><strong>Pine v5/v6 · PineTS {{ capabilities?.version }}</strong><button @click="capabilitiesOpen=false">{{ cw('close') }}</button></header><div><h3>{{ cw('supported') }}</h3><p v-for="item in capabilities?.supported" :key="item">{{ messageText(item) }}</p><h3>{{ cw('limited') }}</h3><p v-for="item in capabilities?.limited" :key="item">{{ messageText(item) }}</p><h3>{{ cw('unsupported') }}</h3><p v-for="item in capabilities?.unsupported" :key="item">{{ messageText(item) }}</p><p>{{ cw('analysisOnly') }}</p></div></section></div>
    <WorkspaceSymbolPicker v-model="searchOpen" :symbols="symbols" :title="searchMode === 'watchlist' ? 'addWatch' : 'switchSymbol'" @select="pickSearch" />
  </section>
</template>

<script setup lang="ts">
import WorkspacePopover from '@/components/chartWorkspace/WorkspacePopover.vue'
import { useRequestError } from '@/composables/useRequestError'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { MagnifyingGlassIcon, AdjustmentsHorizontalIcon, SunIcon, MoonIcon, ChevronDownIcon, BellIcon } from '@heroicons/vue/24/outline'
import { useI18n } from 'vue-i18n'
import { useModalDialog } from '@/composables/useModalDialog'
import { useTheme } from '@/composables/useTheme'
import WorkspaceWatchlist from '@/components/chartWorkspace/WorkspaceWatchlist.vue'
import WorkspaceNamePrompt from '@/components/chartWorkspace/WorkspaceNamePrompt.vue'
import WorkspaceSymbolPicker from '@/components/chartWorkspace/WorkspaceSymbolPicker.vue'
import StrategyTester from '@/components/chartWorkspace/StrategyTester.vue'
import { chartApi, type PineCapabilities } from '@/modules/chartWorkspace/api'
import { timeframes } from '@/modules/chartWorkspace/provider'
import { cw, messageText, formatDate } from '@/modules/chartWorkspace/locale'
import { createWorkspaceChart } from '@/modules/chartWorkspace/workspaceChart'
import { createWorkspaceLayouts } from '@/modules/chartWorkspace/workspaceLayouts'
import { createSharedWorkspaceWatchlists } from '@/modules/chartWorkspace/workspaceWatchlists'
import { createPineDocuments } from '@/modules/chartWorkspace/pineDocuments'
import { createPineExecution } from '@/modules/chartWorkspace/pineExecution'
import { useWorkspacePanels } from '@/modules/chartWorkspace/workspacePanels'
import WorkspaceIndicatorPicker from '@/components/chartWorkspace/WorkspaceIndicatorPicker.vue'
import { createWorkspaceAlerts } from '@/modules/chartWorkspace/workspaceAlerts'
import WorkspacePriceAlerts from '@/components/chartWorkspace/WorkspacePriceAlerts.vue'

const PineEditor = defineAsyncComponent(() => import('@/components/chartWorkspace/PineEditor.vue'))
defineOptions({ name: 'ChartWorkspace' })
const { theme, toggleTheme } = useTheme(), { t } = useI18n()
const chartHost = ref<HTMLElement>(), importFile = ref<HTMLInputElement>()
const { error, setError, clearError } = useRequestError(t)
const loading = ref(true), logs = ref<{ time: number; message: string }[]>([])
const addLog = (message: string) => { logs.value = [{ time: Date.now(), message }, ...logs.value].slice(0, 200) }
function fail(cause: unknown) { setError(cause, 'chartWorkspace.loadFailed'); addLog(cause instanceof Error ? cause.message : String(cause)) }
const namePrompt = ref<InstanceType<typeof WorkspaceNamePrompt>>()
const requestName = (title: string, value: string) => namePrompt.value?.requestName(title, value) ?? Promise.resolve(null)
const chart = createWorkspaceChart({ host: chartHost, theme, dirty: () => layoutsController.dirty(), refreshQuotes: () => void listsController.refreshQuotes(), log: addLog, onError: fail })
const { workspace, symbols, activeCell, activeSymbolId, activeTimeframe, activeSymbol, backendPeriod, layout, historyDepth, historyText, feedText, feedError, sync, snapshotRun, selectSymbol, setPeriod, setLayout, setSync, setHistoryDepth, returnLive, locateTrade } = chart
const alertsController = createWorkspaceAlerts({ workspace, symbols })
const panels = useWorkspacePanels({ dirty: () => layoutsController.dirty(), resizeChart: () => workspace.value?.resize() })
const { rightOpen, rightWidth, bottomHeight, bottomTab, editorMounted, testerMounted, compactWorkspace, watchlistDrawerOpen, maxBottomHeight, watchlistVisible, toggleWatchlist, toggleBottom, resizeRight, resizeBottom } = panels
const listsController = createSharedWorkspaceWatchlists({ activeSymbolId, requestName, onError: fail })
const { watchlists, watchlistId, watchSymbols, persistWatch } = listsController
const favoriteIndicators = ref<string[]>([])
let restoringInitialLayout = true
const layoutsController = createWorkspaceLayouts({
  snapshot: () => { const state = chart.snapshot(); return state ? { state, ...panels.snapshot(), watchlistId: watchlistId.value, favoriteIndicators: favoriteIndicators.value } : undefined },
  apply: data => { chart.restore(data); panels.restore(data); listsController.restoreSelection(data.watchlistId ?? watchlists.value[0]?.id ?? 'default', restoringInitialLayout); favoriteIndicators.value = data.favoriteIndicators ?? [] },
  requestName, onError: fail,
})
const { layouts, layoutId, saveStatus, saveNow, saveAsLayout, switchLayout } = layoutsController
const documents = createPineDocuments({ requestName, openEditor: () => { bottomTab.value = 'editor' }, onError: fail })
const { scripts, scriptId, source, scriptDirty, scriptLoading, scriptConflict, useSavedScript, selectedScript, openScript, saveScript, newScript, importScript, exportScript } = documents
const execution = createPineExecution({ workspace: () => workspace.value, documents, onError: fail, log: addLog, dirty: layoutsController.dirty })
const { executing, scriptRunning, pineError, addPine, cancelPine } = execution
watch(scriptId, () => { pineError.value = null })
watch(watchlistId, () => { layoutsController.dirty(); void nextTick(() => workspace.value?.resize()) })
const capabilities = ref<PineCapabilities>(), capabilitiesOpen = ref(false)
async function showCapabilities() { try { capabilities.value = await chartApi.capabilities(); capabilitiesOpen.value = true } catch (cause) { fail(cause) } }
const searchOpen = ref(false), searchMode = ref<'chart' | 'watchlist'>('chart')
function pickSearch(id: string) {
  if (searchMode.value === 'watchlist' && !watchSymbols.value.includes(id)) void persistWatch([...watchSymbols.value, id])
  else if (searchMode.value === 'chart') selectSymbol(id)
}
const { dialogRef: capabilitiesDialogRef } = useModalDialog(capabilitiesOpen, () => { capabilitiesOpen.value = false })
const syncOptions = computed(() => [{ key: 'crosshair', label: cw('crosshair') }, { key: 'viewport', label: cw('timeRange') }, { key: 'symbol', label: cw('symbol') }, { key: 'timeframe', label: cw('timeframe') }])
const periods = computed(() => [{ value: '1', label: cw('minute1') }, { value: '5', label: cw('minute5') }, { value: '15', label: cw('minute15') }, { value: '30', label: cw('minute30') }, { value: '60', label: cw('hour1') }, { value: '240', label: cw('hour4') }, { value: 'D', label: cw('day') }, { value: 'W', label: cw('week') }, { value: 'M', label: cw('month') }])
const availablePeriods = computed(() => periods.value.filter(period => activeSymbol.value?.timeframes.includes(timeframes[period.value]!)))
const indicatorTrigger = ref<HTMLButtonElement>()
const indicatorsOpen = ref(false)
watch(indicatorsOpen, async (open) => { if (!open) { await nextTick(); indicatorTrigger.value?.focus({ preventScroll: true }) } })
async function editIndicatorScript(id: string) { scriptId.value = id; await openScript(); bottomTab.value = 'editor' }
function toggleFavorite(type: string) { favoriteIndicators.value = favoriteIndicators.value.includes(type) ? favoriteIndicators.value.filter(value => value !== type) : [...favoriteIndicators.value, type]; layoutsController.dirty() }
function addNative(type: string) { try { workspace.value?.context().addNativeIndicator(type); indicatorsOpen.value = false } catch (cause) { fail(cause) } }
let disposed = false, initializing = false
async function initialize() {
  if (initializing || disposed) return
  initializing = true; loading.value = true; clearError()
  try {
    const [catalog, , scripts, layouts] = await Promise.all([chartApi.symbols(), listsController.loadWatchlists(), chartApi.documents('scripts'), chartApi.documents('layouts')])
    if (disposed) return
    chart.initialize(catalog)
    await layoutsController.initialize(layouts)
    restoringInitialLayout = false
    if (disposed) return
    await documents.initialize(scripts)
    if (disposed) return
    void listsController.refreshQuotes()
  } catch (cause) { if (!disposed) { chart.initializationFailed(); fail(cause) } }
  finally { initializing = false; if (!disposed) loading.value = false }
}
onMounted(initialize)
onBeforeUnmount(() => {
  disposed = true
  alertsController.dispose(); execution.dispose(); documents.dispose(); listsController.dispose()
  layoutsController.dispose(); chart.dispose()
})
</script>

<style>
.cw-capabilities>div{padding:0 18px 18px;overflow:auto;line-height:1.6}.cw-capabilities h3{font-size:13px;margin:15px 0 7px}.cw-capabilities p{margin:5px 0;color:var(--cw-muted)}
.cw-no-drawing-sync{display:none!important}
.chart-workspace{--cw-bg:var(--ui-panel);--cw-panel:var(--ui-toolbar);--cw-border:var(--ui-border);--cw-text:var(--ui-text);--cw-muted:var(--ui-muted);--cw-hover:var(--ui-hover);--cw-accent:var(--ui-accent);display:flex;flex-direction:column;height:100%;min-height:400px;background:var(--cw-bg);color:var(--cw-text);font-family:inherit;font-size:13px;overflow:hidden}.chart-workspace.cw-dark{--cw-bg:var(--ui-panel);--cw-panel:var(--ui-toolbar);--cw-border:var(--ui-border);--cw-text:var(--ui-text);--cw-muted:var(--ui-muted);--cw-hover:var(--ui-hover);--cw-accent:var(--ui-accent)}.chart-workspace :is(.cw-header,.cw-bottom,.cw-notice,.cw-indicator-picker,.cw-modal-backdrop) button,.chart-workspace select,.chart-workspace input{font:inherit;color:inherit;background:transparent;border:1px solid transparent;border-radius:4px;min-height:28px}.chart-workspace :is(.cw-header,.cw-bottom,.cw-notice,.cw-indicator-picker,.cw-modal-backdrop) button{padding:3px 7px;font-weight:600;cursor:pointer;white-space:nowrap}.chart-workspace :is(.cw-header,.cw-bottom,.cw-notice,.cw-indicator-picker,.cw-modal-backdrop) button:hover{background:var(--cw-hover)}.chart-workspace :is(.cw-header,.cw-bottom,.cw-notice,.cw-indicator-picker,.cw-modal-backdrop) button:disabled{opacity:.45;cursor:default}.chart-workspace input,.chart-workspace select{border-color:var(--cw-border);padding:4px 7px;background:var(--cw-panel);max-width:100%}.chart-workspace input[type=checkbox]{min-height:0}.chart-workspace :is(.cw-header,.cw-bottom,.cw-notice,.cw-indicator-picker,.cw-modal-backdrop) button.active{color:var(--cw-accent);background:var(--cw-hover)}.chart-workspace :is(.cw-header,.cw-bottom,.cw-notice,.cw-indicator-picker,.cw-modal-backdrop) button:focus-visible,.chart-workspace select:focus-visible,.chart-workspace input:focus-visible{outline:2px solid var(--cw-accent);outline-offset:1px}.cw-header{height:48px;min-height:48px;display:flex;align-items:center;gap:5px;padding:0 10px;border-bottom:1px solid var(--cw-border);background:var(--cw-panel);z-index:4}.cw-symbol{font-weight:600!important;font-size:14px!important}.cw-symbol small{font-weight:500;color:var(--cw-muted);font-size:11px}.cw-periods{display:flex;border-left:1px solid var(--cw-border);border-right:1px solid var(--cw-border);padding:0 5px}.cw-spacer{flex:1}.cw-body{display:flex;flex:1;min-height:0;position:relative}.cw-center{flex:1;min-width:0;display:flex;flex-direction:column;position:relative}.cw-chart{min-height:100px;flex:1;position:relative;overflow:hidden}.cw-search>header,.cw-indicator-picker>header{display:flex;gap:3px;padding:10px;border-bottom:1px solid var(--cw-border);align-items:center;justify-content:space-between}.cw-vertical-resizer{width:4px;background:var(--cw-border);cursor:col-resize;flex-shrink:0}.cw-horizontal-resizer{height:4px;background:var(--cw-border);cursor:row-resize;position:absolute;top:-2px;width:100%;z-index:5}.cw-bottom{flex-shrink:0;display:flex;flex-direction:column;position:relative;border-top:1px solid var(--cw-border);min-height:34px}.cw-bottom-tabs{display:flex;align-items:center;gap:12px;min-height:33px;padding:0 10px;background:var(--cw-panel);border-bottom:1px solid var(--cw-border)}.cw-bottom-tabs small,.cw-version{color:var(--cw-muted)}.cw-feed{font-size:11px;color:var(--cw-muted)}.cw-editor-panel{display:flex;flex:1;min-height:0;flex-direction:column}.cw-editor-panel[style*="display: none"]{display:none}.cw-editor-tools{display:flex;align-items:center;gap:5px;padding:5px 10px;min-height:38px;border-bottom:1px solid var(--cw-border)}.cw-editor-tools select{max-width:260px}.cw-primary{background:var(--cw-accent)!important;color:var(--ui-onAccent)!important;padding:5px 12px!important}.cw-notice{display:flex;gap:10px;align-items:center;background:#703d1a22;color:#c78131;padding:6px 14px;z-index:5}.cw-notice span{flex:1}.cw-loading{position:absolute;inset:60px 0 40px;display:grid;place-items:center;pointer-events:none;background:var(--cw-bg);z-index:3;color:var(--cw-muted)}.cw-sync{position:relative;padding:4px;cursor:pointer}.cw-sync>div{position:absolute;top:32px;left:0;width:145px;background:var(--cw-panel);border:1px solid var(--cw-border);padding:12px;z-index:25;box-shadow:0 8px 30px #0003}.cw-sync label{display:flex;gap:8px;padding:5px}.cw-log{overflow:auto;padding:10px 16px;color:var(--cw-muted);line-height:1.8}.cw-error{color:#e35b6a;padding:5px 12px}.cw-modal-backdrop{position:fixed;inset:0;background:#0008;z-index:90;display:grid;place-items:center}.cw-search{width:560px;max-width:90vw;height:560px;max-height:85vh;background:var(--cw-bg);border:1px solid var(--cw-border);border-radius:8px;box-shadow:0 20px 80px #0006;display:flex;flex-direction:column}.cw-search>input{margin:12px;min-height:36px}.cw-indicator-picker{position:absolute;left:25%;top:12px;width:310px;z-index:15;background:var(--cw-panel);border:1px solid var(--cw-border);box-shadow:0 10px 35px #0005;padding-bottom:8px}.cw-indicator-picker>input{margin:10px;width:calc(100% - 20px)}.cw-indicator-picker>label{display:flex;align-items:center;gap:6px;margin:0 12px 10px}.cw-indicator-row{display:flex;align-items:center;padding:1px 8px}.cw-indicator-row>button:last-child{flex:1;text-align:left}.cw-chart .vela-workspace{height:100%!important}.cw-chart .vela-topbar{min-height:32px!important}.cw-chart .vela-topbar:empty{display:none}@container app-content (max-width:1250px){.cw-periods button{padding:3px 5px}.cw-version{display:none}.cw-header{gap:2px}}@media(max-width:950px){.cw-vertical-resizer{display:none}.cw-header{overflow-x:auto}.cw-bottom-tabs{gap:3px}}

.cw-icon{display:inline-block;width:18px;height:18px;stroke-width:1.8;flex-shrink:0;vertical-align:middle}
.cw-starred{fill:currentColor}
.chart-workspace :is(.cw-header,.cw-bottom,.cw-notice,.cw-indicator-picker,.cw-modal-backdrop) button:focus-visible,.chart-workspace select:focus-visible,.chart-workspace input:focus-visible,.chart-workspace summary:focus-visible{outline:2px solid var(--cw-accent);outline-offset:1px}
.cw-symbol{display:inline-flex;align-items:center;gap:5px}
.cw-header>.cw-sync{flex-shrink:0;white-space:nowrap}
.cw-header{flex-wrap:wrap;height:auto;padding-block:5px;row-gap:4px}
.cw-header>button,.cw-header>select,.cw-periods{flex-shrink:0}
.cw-header>select{max-width:160px}
.cw-header button.active{font-weight:700}
.cw-bottom-tabs>small{font-size:11px}
.cw-search>header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid var(--cw-border)}
.cw-bottom-tabs{min-width:0}
.cw-bottom-tabs>button{flex-shrink:0}
.cw-editor-tools{flex-wrap:wrap;flex-shrink:0}
.cw-indicator-picker{max-width:calc(100% - 24px);left:50%;transform:translateX(-50%);max-height:calc(100% - 24px);overflow:auto}
@media(max-width:767px){
  .chart-workspace{min-height:0}
  .cw-header{min-height:44px;scrollbar-width:thin;overscroll-behavior-inline:contain}
  .cw-header button,.cw-header select{min-height:36px}
  .cw-bottom-tabs{overflow-x:auto;overscroll-behavior-inline:contain;min-height:40px}
  .cw-bottom-tabs>.cw-spacer,.cw-bottom-tabs>.cw-feed,.cw-bottom-tabs>small{display:none}
  .cw-bottom-tabs>button{min-height:36px;padding-inline:10px}
  .cw-search>input{min-height:44px}
  .cw-notice{flex-wrap:wrap}
  .cw-notice span{flex-basis:100%;overflow-wrap:anywhere}
}

.chart-workspace{min-height:0}
.cw-body{position:relative;overflow-y:auto}
.cw-chart .vela-widget-bottombar{min-width:0;overflow-x:auto;overflow-y:hidden;scrollbar-width:thin;overscroll-behavior-inline:contain}
.cw-chart .vela-widget-bottombar>*{flex-shrink:0}
.cw-chart .vela-ot-row[data-selected]{box-shadow:none}
.cw-chart .vela-dtb-cell,.cw-chart .vela-dtb-btn:not(.vela-dtb-collapse){height:40px;flex-shrink:0}
.cw-chart .vela-dtb-icon{width:36px;height:40px}
.cw-chart .vela-dtb-icon,.cw-chart .vela-dtb-btn{opacity:1!important}
.cw-chart .vela-dtb-icon .vela-dtb-hit,.cw-chart .vela-dtb-btn:not(.vela-dtb-collapse) .vela-dtb-hit{width:36px;height:36px;border-radius:6px}
.cw-chart .vela-dtb-icon .vela-dtb-hit>span,.cw-chart .vela-dtb-btn:not(.vela-dtb-collapse) .vela-dtb-hit>span{width:24px!important;height:24px!important}
.cw-chart .vela-dtb svg[data-cw-drawing-icon],.cw-chart .vela-dtb-flyout svg[data-cw-drawing-icon]{width:100%;height:100%}
.cw-chart .vela-dtb-arrow{top:auto;right:1px;bottom:1px;transform:none;width:10px;height:12px}
.cw-chart .vela-dtb-arrow .vela-dtb-hit--arrow{width:10px;height:12px}
.cw-chart .vela-dtb-arrow .vela-dtb-hit--arrow>span{width:9px!important;height:9px!important}
.cw-chart .vela-dtb-flyout .vela-dtb-item{min-height:34px;gap:10px!important;padding:6px 12px!important}
.cw-chart .vela-dtb-flyout .vela-dtb-item>span:first-child:has(svg[data-cw-drawing-icon]){width:24px!important;height:24px!important}
.cw-chart .vela-widget-style svg[data-cw-drawing-icon]{width:24px;height:24px}
@media(max-width:950px){
  .cw-chart .vela-panel{position:absolute;right:0;inset-block:0;z-index:12;max-width:calc(100% - 48px);box-shadow:-6px 0 20px #0002}
}

</style>
