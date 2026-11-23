<template>
  <Teleport to="body">
    <div v-if="request" class="workspace-dialog-backdrop" @click.self="finish(false)">
      <form ref="dialogRef" tabindex="-1" class="workspace-dialog name-prompt" role="dialog" aria-modal="true" :aria-label="messageText(request.title)" @submit.prevent="finish(true)">
        <label>{{ messageText(request.title) }}<input ref="input" v-model="request.value" class="app-control" maxlength="160" required /></label>
        <footer><button class="app-button-secondary" type="button" @click="finish(false)">{{ cw('cancel') }}</button><button class="app-button-primary" type="submit" :disabled="!request.value.trim()">{{ cw('confirm') }}</button></footer>
      </form>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { useModalDialog } from '@/composables/useModalDialog'
import { cw, messageText } from '@/modules/chartWorkspace/locale'

const request = ref<{ title: string; value: string; resolve: (value: string | null) => void } | null>(null)
const input = ref<HTMLInputElement>()
const { dialogRef } = useModalDialog(computed(() => request.value !== null), () => finish(false), input)
function finish(accept: boolean) {
  const current = request.value
  if (!current) return
  request.value = null
  current.resolve(accept ? current.value.trim() : null)
}
function requestName(title: string, value: string): Promise<string | null> {
  finish(false)
  return new Promise(resolve => {
    request.value = { title, value, resolve }
    void nextTick(() => { input.value?.focus(); input.value?.select() })
  })
}
onBeforeUnmount(() => finish(false))
defineExpose({ requestName })
</script>

<style scoped>
.name-prompt { width: min(360px, 92vw); padding: 16px; }
.name-prompt label { display: grid; gap: 8px; }
.name-prompt footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
</style>
