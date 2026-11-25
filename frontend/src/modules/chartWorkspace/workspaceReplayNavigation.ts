import { ref, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount, type Ref } from 'vue'
import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { WorkspaceReplay } from './workspaceReplay'
import { replayDateInput, replayDateTime } from './replayModel'
import { cw } from './locale'

export function useWorkspaceReplayNavigation(deps: {
  replay: WorkspaceReplay; workspace: () => VelaWorkspace | undefined; timeZone: Ref<string>; prepare: () => void
}) {
const r=deps.replay,timeZone=deps.timeZone
const pageActive=ref(true),dateOpen=ref(false),date=ref(defaultDate())
function defaultDate() { return replayDateInput(Date.now()-86400000,'Asia/Shanghai').slice(0,10)+'T00:00' }
function togglePlayback() { if(r.playing.value)r.pause();else r.play() }
function playbackKey(event:KeyboardEvent) {
  if ((event.code!=='Space' && event.key!==' ') || event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  if (!pageActive.value || document.hidden || !r.open.value || !r.active.value || r.ended.value || r.loading.value && !r.playing.value || dateOpen.value) return
  if (!deps.workspace()?.context().host.getClientRects().length) return
  const target=event.target instanceof Element?event.target:undefined
  if (target?.closest('input,textarea,select,form,[contenteditable]:not([contenteditable="false"]),[role="textbox"],[role="menu"],[role="listbox"],summary,[popover]:popover-open,.pine-editor,.cw-replay-menu,.cw-replay-price-editor')) return
  const modal=Array.from(document.querySelectorAll<HTMLElement>('[aria-modal="true"],[role="dialog"],[role="alertdialog"]'))
    .some(element=>element.getClientRects().length>0 && getComputedStyle(element).visibility!=='hidden')
  if (modal) return
  event.preventDefault();event.stopImmediatePropagation()
  if (!event.repeat) togglePlayback()
}
function showDate() {
  r.pause();r.picking.value=false;deps.prepare()
  date.value=r.active.value?replayDateInput(r.now.value,timeZone.value):replayDateInput(Date.now()-86400000,timeZone.value).slice(0,10)+'T00:00'
  dateOpen.value=true
}
function closeDate(){dateOpen.value=false;if(!r.active.value)void r.exit()}
async function chooseDate(value:string) {
  date.value=value
  const time=replayDateTime(value,timeZone.value)
  if(!Number.isFinite(time)){r.error.value=cw('replayPastDate');return}
  await r.start(time); if (r.active.value && !r.error.value) dateOpen.value=false
}
async function chooseRandom(){
  await r.startRandom()
  if(r.active.value&&!r.error.value){date.value=replayDateInput(r.now.value,timeZone.value);dateOpen.value=false}
}
async function retryDate(){await r.retry();if(r.active.value&&!r.error.value){date.value=replayDateInput(r.now.value,timeZone.value);dateOpen.value=false}}
watch(r.open,value=>{if(value&&!r.active.value)showDate();else if(!value)dateOpen.value=false})
onMounted(()=>window.addEventListener('keydown',playbackKey,{ capture: true }))
onActivated(()=>{pageActive.value=true})
onDeactivated(()=>{pageActive.value=false})
onBeforeUnmount(()=>window.removeEventListener('keydown',playbackKey,{ capture: true }))
return {pageActive,dateOpen,date,showDate,closeDate,chooseDate,chooseRandom,retryDate,togglePlayback,
  picked(){dateOpen.value=false} }
}
