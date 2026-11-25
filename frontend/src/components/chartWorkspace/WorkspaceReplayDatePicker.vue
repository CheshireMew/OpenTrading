<template>
  <Teleport to="body">
    <div v-if="open" class="workspace-dialog-backdrop replay-date-backdrop" @click.self="!busy && emit('close')">
      <section ref="dialogRef" class="workspace-dialog replay-date-dialog" role="dialog" aria-modal="true" :aria-label="cw('replayDate')" :aria-busy="busy" tabindex="-1">
        <header>
          <h2>{{ cw('replayDate') }}</h2>
          <div class="replay-date-actions">
            <button type="button" :aria-label="cw('replayRandom')" :title="cw('replayRandom')" :disabled="busy" @pointerdown.prevent @click="emit('random')"><IconDice :size="18" stroke-width="1.5" aria-hidden="true" /></button>
            <button type="button" :aria-label="cw('close')" :disabled="busy" @click="emit('close')"><XMarkIcon /></button>
          </div>
        </header>
        <form class="replay-date-fields" @submit.prevent="selectDate(date)">
          <label>{{ cw('replayCalendarDate') }}<input ref="dateInput" v-model="date" type="text" inputmode="numeric" placeholder="YYYY-MM-DD" maxlength="10" :disabled="busy" @change="selectDate(date)" /></label>
          <label>{{ cw('replayCalendarTime') }}<input v-model="time" type="time" :disabled="busy" @change="selectTime" /></label>
        </form>
        <div class="replay-month-controls">
          <button type="button" :aria-label="cw('replayPreviousMonth')" :disabled="busy || (year===1970 && month===0)" @click="moveMonth(-1)"><ChevronLeftIcon /></button>
          <select v-model.number="year" :aria-label="cw('replayCalendarYear')" :disabled="busy"><option v-for="item in years" :key="item" :value="item">{{ item }}</option></select>
          <select v-model.number="month" :aria-label="cw('replayCalendarMonth')" :disabled="busy"><option v-for="(label,index) in months" :key="index" :value="index">{{ label }}</option></select>
          <button type="button" :aria-label="cw('replayNextMonth')" :disabled="busy || (year===currentYear && month===currentMonth)" @click="moveMonth(1)"><ChevronRightIcon /></button>
        </div>
        <div class="replay-calendar-weekdays" aria-hidden="true"><span v-for="day in weekdays" :key="day">{{ day }}</span></div>
        <div class="replay-calendar-days" role="group" :aria-label="monthTitle">
          <button v-for="day in days" :key="day.value" type="button" :data-date="day.value" :aria-label="day.label" :aria-pressed="date===day.value"
            :class="{outside:day.outside,selected:date===day.value}" :disabled="busy || day.value>today || day.value<'1970-01-01'" @click="selectDate(day.value)">{{ day.number }}</button>
        </div>
        <p v-if="busy" class="replay-date-status" role="status">{{ cw('replayPreparing') }}</p>
        <p v-else-if="error" class="replay-date-error" role="alert">{{ error }} <button type="button" @click="emit('retry')">{{ cw('replayRetry') }}</button></p>
        <footer><span>{{ timeZone }}</span><button type="button" :disabled="busy" @click="emit('pick')">{{ cw('replayPick') }}</button></footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeftIcon, ChevronRightIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { IconDice } from '@tabler/icons-vue'
import { useModalDialog } from '@/composables/useModalDialog'
import { cw } from '@/modules/chartWorkspace/locale'
import { replayDateInput, replayDateTime } from '@/modules/chartWorkspace/replayModel'

const props=defineProps<{open:boolean;value:string;timeZone:string;busy:boolean;error:string}>()
const emit=defineEmits<{select:[value:string];close:[];pick:[];random:[];retry:[]}>()
const {locale}=useI18n()
const date=ref(''),time=ref('00:00'),year=ref(2026),month=ref(0),dateInput=ref<HTMLInputElement>()
const today=computed(()=>replayDateInput(Date.now(),props.timeZone).slice(0,10))
const currentYear=Number(today.value.slice(0,4)),currentMonth=Number(today.value.slice(5,7))-1
const years=Array.from({length:currentYear-1969},(_,index)=>currentYear-index)
const months=computed(()=>Array.from({length:12},(_,index)=>new Intl.DateTimeFormat(locale.value,{month:'long',timeZone:'UTC'}).format(Date.UTC(2026,index,1))))
const weekdays=computed(()=>Array.from({length:7},(_,index)=>new Intl.DateTimeFormat(locale.value,{weekday:'short',timeZone:'UTC'}).format(Date.UTC(2026,0,5+index))))
const monthTitle=computed(()=>new Intl.DateTimeFormat(locale.value,{year:'numeric',month:'long',timeZone:'UTC'}).format(Date.UTC(year.value,month.value,1)))
const days=computed(()=>{
  const first=Date.UTC(year.value,month.value,1),offset=(new Date(first).getUTCDay()+6)%7
  return Array.from({length:42},(_,index)=>{
    const stamp=first+(index-offset)*86400000,day=new Date(stamp),value=day.toISOString().slice(0,10)
    return{value,number:day.getUTCDate(),outside:day.getUTCMonth()!==month.value,
      label:new Intl.DateTimeFormat(locale.value,{dateStyle:'full',timeZone:'UTC'}).format(stamp)}
  })
})
const {dialogRef}=useModalDialog(toRef(props,'open'),()=>{if(!props.busy)emit('close')},dateInput)
watch(()=>props.open,async open=>{
  if(!open)return
  date.value=props.value.slice(0,10);time.value=props.value.slice(11,16)||'00:00'
  year.value=Number(date.value.slice(0,4));month.value=Number(date.value.slice(5,7))-1
  await nextTick();dateInput.value?.select()
},{immediate:true})
function moveMonth(offset:number){const next=new Date(Date.UTC(year.value,month.value+offset,1));year.value=next.getUTCFullYear();month.value=next.getUTCMonth()}
function selectTime(){
  // While browsing another month, retain the time for the day the user is about to pick.
  if(date.value.slice(0,7)===`${year.value}-${String(month.value+1).padStart(2,'0')}`)selectDate(date.value)
}
function selectDate(value:string){
  if(props.busy || !/^\d{4}-\d{2}-\d{2}$/.test(value) || !/^\d{2}:\d{2}$/.test(time.value))return
  const next=value+'T'+time.value
  if(!Number.isFinite(replayDateTime(next,props.timeZone)))return
  date.value=value
  emit('select',next)
}
</script>

<style scoped>
.replay-date-backdrop{z-index:100}
.replay-date-dialog{width:min(376px,calc(100vw - 32px));padding:20px;color:var(--ui-text);background:var(--ui-panel);border:1px solid var(--ui-border);border-radius:10px;box-shadow:0 16px 64px #0005;font-size:13px;max-height:calc(100dvh - 40px);overflow:auto}
.replay-date-dialog header{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.replay-date-dialog h2{margin:0;color:var(--ui-title);font-size:18px;font-weight:600}
.replay-date-actions{display:flex;gap:4px}.replay-date-actions button{width:34px}
.replay-date-dialog button,.replay-date-dialog select,.replay-date-dialog input{font:inherit;color:inherit;border:1px solid transparent;border-radius:5px;background:transparent;min-height:34px}.replay-date-dialog button{display:inline-flex;align-items:center;justify-content:center;padding:4px;cursor:pointer}.replay-date-dialog button:hover{background:var(--ui-hover)}.replay-date-dialog button:disabled{opacity:.3;cursor:default}.replay-date-dialog svg{width:18px;height:18px}.replay-date-dialog :is(button,input,select):focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}
.replay-date-fields{display:grid;grid-template-columns:minmax(0,1fr) 112px;gap:12px;margin-bottom:18px}.replay-date-fields label{display:grid;gap:7px;color:var(--ui-muted);font-size:12px}.replay-date-fields input{min-width:0;width:100%;box-sizing:border-box;border-color:var(--ui-border);background:var(--ui-toolbar);padding:6px 9px;color:var(--ui-text);font-variant-numeric:tabular-nums;font-size:14px}
.replay-month-controls{display:flex;align-items:center;gap:5px;margin-bottom:8px}.replay-month-controls button{width:32px;flex-shrink:0}.replay-month-controls select{font-weight:600;padding:4px;min-width:0}.replay-month-controls select:nth-of-type(2){flex:1}.replay-month-controls option{background:var(--ui-panel);color:var(--ui-text)}
.replay-calendar-weekdays,.replay-calendar-days{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px}.replay-calendar-weekdays span{text-align:center;font-size:12px;color:var(--ui-muted);padding:8px 0}.replay-calendar-days button{height:37px;min-width:0;font-variant-numeric:tabular-nums;font-size:14px}.replay-calendar-days button.outside{color:var(--ui-muted)}.replay-calendar-days button.selected{background:var(--ui-accent);color:var(--ui-onAccent)}
.replay-date-dialog footer{display:flex;align-items:center;justify-content:space-between;margin-top:16px;padding-top:12px;border-top:1px solid var(--ui-border)}.replay-date-dialog footer span{color:var(--ui-muted);font-size:12px}.replay-date-dialog footer button{padding:5px 9px;color:var(--ui-accent)}.replay-date-status,.replay-date-error{margin:12px 0 0;font-size:12px;line-height:1.5}.replay-date-status{color:var(--ui-muted)}.replay-date-error{color:var(--ui-negative)}
</style>
