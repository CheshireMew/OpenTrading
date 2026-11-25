<template>
  <Teleport to="body">
    <div v-if="open" class="workspace-dialog-backdrop" @click.self="close">
      <section ref="dialogRef" class="workspace-dialog price-alert-dialog" tabindex="-1" role="dialog" aria-modal="true" :aria-label="cw('priceAlerts')">
        <header><strong>{{ cw(editing ? form.id ? 'alertEdit' : 'addPriceAlert' : 'priceAlerts') }}</strong><button class="app-icon-button" type="button" :aria-label="cw('close')" @click="close">×</button></header>
        <div v-if="error" class="alert-message" role="alert">{{ error }}</div>
        <form v-if="editing" @submit.prevent="save">
          <p class="alert-symbol">{{ selectedSymbol?.name }} · {{ selectedSymbol ? workspaceMarketLabel(selectedSymbol.id) : '' }}</p>
          <label>{{ cw('alertCondition') }}<select v-model="form.operator" class="app-control"><option value="crosses">{{ cw('alertCrosses') }}</option><option value="crosses_above">{{ cw('alertCrossesAbove') }}</option><option value="crosses_below">{{ cw('alertCrossesBelow') }}</option><option value="gte">{{ cw('alertAbove') }}</option><option value="lte">{{ cw('alertBelow') }}</option></select></label>
          <label>{{ cw('alertPrice') }}<input v-model="form.price" class="app-control" type="number" inputmode="decimal" step="any" min="0" required /></label>
          <label>{{ cw('alertFrequency') }}<select v-model="form.once" class="app-control"><option :value="true">{{ cw('alertOnce') }}</option><option :value="false">{{ cw('alertRepeat') }}</option></select></label>
          <fieldset><legend>{{ cw('alertNotify') }}</legend><label><input v-model="form.sound" type="checkbox" />{{ cw('alertSound') }}</label><label><input v-model="form.windows" type="checkbox" />{{ cw('alertDesktop') }}</label><button type="button" class="app-button-secondary" @click="testSound">{{ cw('alertTestSound') }}</button></fieldset>
          <p class="alert-hint">{{ cw(replayMode ? 'alertReplayHint' : 'alertRuntimeHint') }}</p>
          <p v-if="alertDeliveryStatus" class="alert-message" role="status">{{ cw(alertDeliveryStatus) }}</p>
          <footer><button type="button" class="app-button-secondary" :disabled="saving" @click="editing=false">{{ cw('cancel') }}</button><button type="submit" class="app-button-primary" :disabled="saving || !(Number(form.price)>0)">{{ cw(saving ? 'saving' : 'save') }}</button></footer>
        </form>
        <div v-else class="alert-list">
          <div class="alert-list-tools"><button class="app-button-primary" type="button" @click="startForm()">{{ cw('addPriceAlert') }}</button><button class="app-button-secondary" type="button" @click="enable">{{ cw('alertEnableDelivery') }}</button></div>
          <p v-if="alertDeliveryStatus" class="alert-message" role="status">{{ cw(alertDeliveryStatus) }}</p>
          <p v-if="!alerts.length" class="alert-hint">{{ cw('alertEmpty') }}</p>
          <article v-for="alert in alerts" :key="alert.id">
            <div><strong>{{ alert.name }}</strong><p>{{ conditionLabel(alert.operator) }} · {{ formatNumber(alert.threshold,10) }} · {{ cw(alert.enabled ? 'alertActive' : alert.lastTriggeredAt ? 'alertTriggered' : 'alertPaused') }}</p><p v-if="alert.lastTriggeredAt">{{ cw('alertLastTriggered') }} {{ formatDate(new Date(alert.lastTriggeredAt).getTime()) }}</p></div>
            <div class="alert-actions"><button type="button" class="app-button-secondary" :disabled="saving" @click="edit(alert)">{{ cw('alertEdit') }}</button><button type="button" class="app-button-secondary" :disabled="saving" @click="change(alert)">{{ cw(alert.enabled ? 'alertPause' : 'alertResume') }}</button><button type="button" class="app-button-secondary alert-delete" :disabled="saving" @click="remove(alert)">{{ cw('alertDelete') }}</button></div>
          </article>
          <p class="alert-hint">{{ cw(replayMode ? 'alertReplayHint' : 'alertRuntimeHint') }}</p>
        </div>
      </section>
    </div>
  </Teleport>
</template>
<script setup lang="ts">
import { useModalDialog } from '@/composables/useModalDialog'
import type { createWorkspaceAlerts } from '@/modules/chartWorkspace/workspaceAlerts'
import { cw, formatNumber, formatDate, workspaceMarketLabel } from '@/modules/chartWorkspace/locale'
import { alertDeliveryStatus, enableAlertDelivery, playAlertSound } from '@/modules/research/alertDelivery'
const props = defineProps<{ controller: ReturnType<typeof createWorkspaceAlerts> }>()
const { open, editing, saving, error, form, selectedSymbol, alerts, replayMode, startForm, edit, save, change, remove } = props.controller
function close() { if (!saving.value) open.value = false }
const { dialogRef } = useModalDialog(open, close)
function conditionLabel(operator: string) { return cw(({crosses:'alertCrosses',crosses_above:'alertCrossesAbove',crosses_below:'alertCrossesBelow',gte:'alertAbove',lte:'alertBelow'} as Record<string,string>)[operator] ?? operator) }
async function testSound() { if (!await playAlertSound()) alertDeliveryStatus.value = 'alertSoundBlocked' }
function enable() { void enableAlertDelivery(true, true) }
</script>
<style scoped>
.price-alert-dialog{display:flex;flex-direction:column;width:min(540px,calc(100vw - 24px));height:min(600px,calc(100dvh - 32px));overflow:hidden;color:var(--app-text)}
.price-alert-dialog>header,.price-alert-dialog>.alert-message{flex-shrink:0}
.price-alert-dialog>form,.price-alert-dialog>.alert-list{flex:1;min-height:0;overflow:auto;align-content:start;scrollbar-gutter:stable;overscroll-behavior:contain}
header{display:flex;align-items:center;justify-content:space-between;padding:12px 18px;border-bottom:1px solid var(--app-border)}
form,.alert-list{padding:18px}form{display:grid;gap:16px}form>label{display:grid;gap:6px;font-size:13px}form .app-control{width:100%;min-height:40px}
.alert-symbol{font-weight:600;margin:0}fieldset{display:flex;flex-wrap:wrap;gap:14px;align-items:center;border:0;padding:0}legend{font-size:13px;margin-bottom:10px}fieldset label{display:flex;align-items:center;gap:6px;font-size:13px}
.alert-hint{font-size:12px;line-height:1.7;color:var(--ui-muted);margin:0}.alert-message{font-size:13px;line-height:1.6;padding:12px 18px;background:var(--ui-elevated);overflow-wrap:anywhere}
footer,.alert-list-tools,.alert-actions{display:flex;gap:8px;flex-wrap:wrap}footer{justify-content:flex-end}.alert-list{display:grid;gap:16px}article{border-top:1px solid var(--app-border);padding-top:16px;display:grid;gap:12px}article strong{font-size:14px}article p{font-size:12px;color:var(--ui-muted);margin:6px 0;overflow-wrap:anywhere}
</style>
