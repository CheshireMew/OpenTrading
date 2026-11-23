<template>
  <aside v-if="alertNotices.length" class="price-alert-notices" aria-live="assertive" :aria-label="cw('priceAlerts')">
    <article v-if="alertDeliveryStatus === 'alertSoundBlocked'" role="status"><div><p>{{ cw('alertSoundBlocked') }}</p><button class="app-button-secondary" type="button" @click="retryAudio">{{ cw('alertTestSound') }}</button></div></article>
    <article v-for="event in alertNotices" :key="event.id" role="alert">
      <div><strong>{{ event.title }}</strong><p>{{ event.body }}</p><time>{{ formatDate(new Date(event.occurredAt).getTime()) }}</time></div>
      <button type="button" class="app-icon-button" :aria-label="cw('close')" @click="dismissAlertNotice(event.id)">×</button>
    </article>
  </aside>
</template>
<script setup lang="ts">
import { alertNotices, dismissAlertNotice, alertDeliveryStatus, playAlertSound } from '@/modules/research/alertDelivery'
import { cw, formatDate } from '@/modules/chartWorkspace/locale'
async function retryAudio() { if (await playAlertSound()) alertDeliveryStatus.value = '' }
</script>
<style scoped>
.price-alert-notices{position:fixed;right:20px;bottom:20px;z-index:150;display:grid;gap:10px;width:min(390px,calc(100vw - 32px));max-height:70dvh;overflow:auto}
article{display:flex;align-items:flex-start;gap:12px;background:var(--ui-panel);color:var(--ui-text);border:1px solid var(--ui-border);border-left:3px solid #d99a24;box-shadow:0 8px 28px #0003;padding:14px}
article>div{flex:1;min-width:0;overflow-wrap:anywhere}p{margin:6px 0;font-size:13px}time{font-size:11px;opacity:.7}
</style>
