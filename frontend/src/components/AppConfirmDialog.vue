<template>
  <Teleport to="body">
    <div v-if="request" class="workspace-dialog-backdrop" @click.self="finish(false)">
      <section ref="dialogRef" class="workspace-dialog confirm-dialog" tabindex="-1" role="dialog" aria-modal="true" :aria-label="request.title">
        <h2>{{ request.title }}</h2><p>{{ request.message || t('ui.deletePermanent') }}</p>
        <footer><button ref="cancel" type="button" class="app-button-secondary" @click="finish(false)">{{ t('chartWorkspace.cancel') }}</button><button type="button" class="app-button-primary confirm-delete" @click="finish(true)">{{ t('ui.delete') }}</button></footer>
      </section>
    </div>
  </Teleport>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useModalDialog } from '@/composables/useModalDialog'
const { t } = useI18n(), cancel = ref<HTMLButtonElement>()
const request = ref<{title:string;message?:string;resolve:(result:boolean)=>void}>()
function finish(value:boolean) { const current=request.value; request.value=undefined;current?.resolve(value) }
function confirm(name:string,message?:string):Promise<boolean> { finish(false); return new Promise(resolve=>{request.value={title:t('ui.deleteNamed',{name}),message,resolve}}) }
const { dialogRef }=useModalDialog(computed(()=>!!request.value),()=>finish(false),cancel)
onBeforeUnmount(()=>finish(false))
defineExpose({confirm})
</script>
<style scoped>
.confirm-dialog{width:min(420px,calc(100vw - 32px));padding:20px;color:var(--ui-text)}h2{font-size:16px;font-weight:600;margin:0}p{font-size:13px;color:var(--ui-muted);line-height:1.65;margin:12px 0 20px}footer{display:flex;justify-content:flex-end;gap:8px}.confirm-delete{background:var(--ui-negative);color:white}
</style>
