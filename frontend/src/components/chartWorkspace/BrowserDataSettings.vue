<template>
  <section id="settings-browser-data" class="app-settings-section">
    <div><h2 class="app-section-title">{{ cw('browserDataTitle') }}</h2><p class="app-settings-description">{{ cw('browserDataHint') }}</p></div>
    <div>
      <p class="mb-4 text-sm app-muted">{{ cw('browserBackupHint') }}</p>
      <div class="flex flex-wrap items-center gap-3">
        <button type="button" class="app-button-secondary app-touch-target" :disabled="busy" @click="download">{{ cw('browserBackupExport') }}</button>
        <button type="button" class="app-button-secondary app-touch-target" :disabled="busy" @click="input?.click()">{{ cw('browserBackupImport') }}</button>
        <button v-if="imported" type="button" class="app-button-primary app-touch-target" @click="reload">{{ cw('browserBackupApply') }}</button>
        <input ref="input" class="hidden" type="file" accept="application/json,.json" @change="restore" />
      </div>
      <p v-if="status" class="mt-3 text-sm app-muted" role="status">{{ status }}</p>
      <p v-if="error" class="mt-3 text-sm text-rose-600 dark:text-rose-300" role="alert">{{ error }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { cw } from '@/modules/chartWorkspace/locale'
import { exportBrowserData, importBrowserData } from '@/modules/chartWorkspace/browserDataBackup'

const input = ref<HTMLInputElement>(), busy = ref(false), imported = ref(false), status = ref(''), error = ref('')
const reload = () => window.location.reload()
async function download() {
  busy.value = true; status.value = ''; error.value = ''
  try {
    const backup = await exportBrowserData()
    const url = URL.createObjectURL(new Blob([JSON.stringify(backup)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = 'opentrading-personal-data-' + new Date().toISOString().slice(0, 10) + '.json'
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    status.value = cw('browserBackupExported')
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { busy.value = false }
}
async function restore(event: Event) {
  const control = event.target as HTMLInputElement, file = control.files?.[0]
  if (!file) return
  busy.value = true; status.value = ''; error.value = ''
  try {
    const count = await importBrowserData(await file.text())
    imported.value = true; status.value = cw('browserBackupImported', { count })
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { busy.value = false; control.value = '' }
}
</script>
