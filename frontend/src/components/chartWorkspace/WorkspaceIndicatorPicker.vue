<template>
  <Teleport to="body">
    <div v-if="modelValue" class="workspace-dialog-backdrop" @click.self="close">
      <section ref="dialogRef" class="workspace-dialog indicator-library" role="dialog" aria-modal="true" :aria-label="cw('indicators')" tabindex="-1">
        <header><strong>{{ cw('indicators') }}</strong><button type="button" class="app-icon-button" :aria-label="cw('close')" @click="close"><XMarkIcon /></button></header>
        <div class="indicator-search"><MagnifyingGlassIcon aria-hidden="true" /><input ref="search" v-model="query" class="app-control" type="search" :aria-label="cw('searchIndicators')" :placeholder="cw('searchIndicators')" /></div>
        <div class="indicator-library-body">
          <nav :aria-label="cw('indicatorCategories')"><button v-for="tab in tabs" :key="tab.id" type="button" :class="{active:category===tab.id}" :aria-pressed="category===tab.id" @click="category=tab.id">{{ tab.label }}</button></nav>
          <div class="indicator-results">
            <template v-if="category!=='added'">
              <section v-if="nativeRows.length"><h3>{{ cw('builtInIndicators') }}</h3><div v-for="item in nativeRows" :key="item.type" class="indicator-row"><button type="button" class="indicator-star" :aria-label="cw('favoriteIndicator',{name:item.name})" :aria-pressed="favorites.includes(item.type)" @click="emit('favorite',item.type)"><StarIcon :class="{starred:favorites.includes(item.type)}" /></button><button class="indicator-name" type="button" @click="emit('native',item.type);close()">{{ item.name }}</button></div></section>
              <section v-if="scriptRows.length"><h3>{{ cw('pineScripts') }}</h3><div v-for="script in scriptRows" :key="script.id" class="indicator-row"><button type="button" class="indicator-star" :aria-label="cw('favoriteIndicator',{name:script.name})" :aria-pressed="favorites.includes('script:'+script.id)" @click="emit('favorite','script:'+script.id)"><StarIcon :class="{starred:favorites.includes('script:'+script.id)}" /></button><button class="indicator-name" type="button" :disabled="busy" @click="emit('script',script);close()">{{ script.name }}</button><button type="button" class="app-icon-button" :aria-label="cw('viewIndicatorSource',{name:script.name})" @click="emit('edit',script.id);close()"><CodeBracketIcon /></button></div></section>
              <p v-if="!nativeRows.length&&!scriptRows.length" class="indicator-empty">{{ cw('noIndicatorsFound') }}</p>
            </template>
            <template v-else>
              <article v-for="item in addedRows" :key="item.id" class="indicator-added"><strong :class="{muted:!item.visible}">{{ item.title }}</strong><div><button type="button" class="app-icon-button" :aria-label="cw('configureIndicator',{name:item.title})" @click="settings(item.id)"><Cog6ToothIcon /></button><button type="button" class="app-icon-button" :aria-label="cw(item.visible?'hideIndicator':'showIndicator',{name:item.title})" :aria-pressed="item.visible" @click="item.handle.setVisible(!item.visible)"><EyeIcon v-if="item.visible"/><EyeSlashIcon v-else/></button><button type="button" class="app-icon-button" :aria-label="cw('removeIndicator',{name:item.title})" @click="item.handle.remove()"><XMarkIcon /></button></div></article>
              <p v-if="!addedRows.length" class="indicator-empty">{{ cw('noAddedIndicators') }}</p>
            </template>
          </div>
        </div>
        <footer><button class="app-button-secondary" type="button" @click="emit('editor');close()">{{ cw('pineEditor') }}</button><span v-if="busy">{{ cw('calculating') }}</span></footer>
      </section>
    </div>
  </Teleport>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { WorkspaceDocument } from '@/modules/chartWorkspace/api'
import { useModalDialog } from '@/composables/useModalDialog'
import { cw } from '@/modules/chartWorkspace/locale'
import { WORKSPACE_INDICATORS } from '@/modules/chartWorkspace/workspaceIndicators'
import { CodeBracketIcon, Cog6ToothIcon, EyeIcon, EyeSlashIcon, MagnifyingGlassIcon, StarIcon, XMarkIcon } from '@heroicons/vue/24/outline'

const props=defineProps<{modelValue:boolean;workspace?:VelaWorkspace;scripts:WorkspaceDocument[];favorites:string[];busy:boolean}>()
const emit=defineEmits<{'update:modelValue':[boolean];native:[string];script:[WorkspaceDocument];edit:[string];favorite:[string];editor:[]}>()
const search=ref<HTMLInputElement>(),query=ref(''),category=ref('all'),revision=ref(0)
const close=()=>emit('update:modelValue',false)
const {dialogRef}=useModalDialog(computed(()=>props.modelValue),close,search)
const tabs=computed(()=>[{id:'all',label:cw('allIndicators')},{id:'favorites',label:cw('favoriteIndicators')},{id:'mine',label:cw('myScripts')},{id:'added',label:cw('addedIndicators')}])
const natives=computed(()=>WORKSPACE_INDICATORS.map(item=>({type:item.type,name:cw(item.name)})))
const matches=(name:string)=>name.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase())
const nativeRows=computed(()=>category.value==='mine'?[]:natives.value.filter(item=>matches(item.name)&&(category.value!=='favorites'||props.favorites.includes(item.type))))
const scriptRows=computed(()=>props.scripts.filter(script=>matches(script.name)&&(category.value!=='mine'||!script.readonly)&&(category.value!=='favorites'||props.favorites.includes('script:'+script.id))))
const addedRows=computed(()=>{
  revision.value
  const chart=props.workspace?.active?.chart,names=new Map(chart?.inspect().indicators.map(item=>[item.id,item.title])??[])
  return (chart?.indicators()??[]).map(handle=>({id:handle.id,title:names.get(handle.id)??props.scripts.find(script=>script.data.source===handle.source)?.name??handle.title,visible:handle.visible,handle})).filter(item=>matches(item.title))
})
let offs:(()=>void)[]=[]
const chartOffs=new Map<object,(()=>void)[]>()
function release(){offs.forEach(off=>off());offs=[];for(const list of chartOffs.values())list.forEach(off=>off());chartOffs.clear()}
function bindCells(){
  const cells=props.workspace?.cells()??[]
  for(const [chart,list] of chartOffs)if(!cells.some(cell=>cell.chart===chart)){list.forEach(off=>off());chartOffs.delete(chart)}
  for(const {chart} of cells)if(!chartOffs.has(chart))chartOffs.set(chart,[chart.on('indicator:added',refresh),chart.on('indicator:removed',refresh),chart.on('indicator:visibility',refresh)])
  refresh()
}
function refresh(){revision.value++}
watch(()=>props.workspace,workspace=>{release();if(workspace){offs=[workspace.on('cell:active',refresh),workspace.on('cell:created',bindCells),workspace.on('layout:changed',bindCells)];bindCells()}},{immediate:true})
watch(()=>props.modelValue,open=>{if(open){bindCells();void nextTick(()=>search.value?.focus())}})
async function settings(id:string){const chart=props.workspace?.active?.chart;close();await nextTick();chart?.renderer.openIndicatorSettings(id)}
onBeforeUnmount(release)
</script>
<style scoped>
.indicator-library{width:min(710px,calc(100vw - 24px));height:min(620px,calc(100dvh - 32px));display:flex;flex-direction:column;overflow:hidden}
header,.indicator-search,footer{flex-shrink:0}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--ui-border)}svg{width:18px;height:18px;flex-shrink:0}button:focus-visible{outline:2px solid var(--ui-blue);outline-offset:-2px}
.indicator-search{position:relative;padding:14px 18px}.indicator-search>svg{position:absolute;left:30px;top:25px;color:var(--ui-muted)}.indicator-search input{width:100%;padding-left:38px}
.indicator-library-body{display:flex;min-height:0;flex:1}nav{width:145px;min-height:0;flex-shrink:0;overflow:auto;border-right:1px solid var(--ui-border);padding:8px}nav button{display:block;width:100%;text-align:left;padding:10px 12px;border-radius:4px;font-size:13px;color:var(--ui-muted)}nav button.active{color:var(--ui-text);background:var(--ui-elevated);font-weight:600}
.indicator-results{min-width:0;flex:1;overflow:auto;padding:6px 12px 18px}h3{font-size:11px;color:var(--ui-muted);padding:10px 8px 5px}.indicator-row{display:flex;align-items:center;min-height:42px;gap:4px;border-radius:4px}.indicator-row:hover{background:var(--ui-hover)}.indicator-star{padding:10px 6px;color:var(--ui-faint)}.starred{fill:var(--ui-favorite);color:var(--ui-favorite)}.indicator-name{flex:1;min-width:0;min-height:42px;text-align:left;font-size:13px;overflow-wrap:anywhere;padding:8px 4px}.indicator-name:disabled{opacity:.5}.indicator-empty{padding:35px 12px;text-align:center;font-size:13px;color:var(--ui-muted)}
.indicator-added{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:48px;border-bottom:1px solid var(--ui-border);font-size:13px}.indicator-added strong{font-weight:500;min-width:0;overflow-wrap:anywhere}.indicator-added>div{display:flex;gap:3px}.muted{color:var(--ui-muted)}footer{display:flex;align-items:center;gap:12px;border-top:1px solid var(--ui-border);padding:12px 18px;font-size:12px;color:var(--ui-muted)}
.indicator-results{min-height:0;scrollbar-gutter:stable;overscroll-behavior:contain}
@media(max-width:560px){.indicator-library{height:min(640px,calc(100dvh - 24px))}.indicator-library-body{flex-direction:column}nav{display:flex;flex:0 0 auto;width:100%;overflow-x:auto;border-right:0;border-bottom:1px solid var(--ui-border);padding:4px}nav button{width:auto;flex-shrink:0;padding:9px 11px}.indicator-results{padding-inline:8px}.indicator-row{min-height:46px}}
@media(max-height:480px){header,footer{padding:8px 12px}.indicator-search{padding:8px 12px}.indicator-search>svg{left:24px;top:19px}.indicator-search input{min-height:36px}}
</style>
