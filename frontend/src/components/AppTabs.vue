<template>
  <div class="app-tabs" role="tablist" :aria-label="label" @keydown="navigate">
    <button v-for="tab in tabs" :id="`${id}-tab-${tab.id}`" :key="tab.id" type="button" role="tab"
      :aria-selected="modelValue === tab.id" :aria-controls="`${id}-panel-${tab.id}`"
      :tabindex="modelValue === tab.id ? 0 : -1" :class="{ 'is-active': modelValue === tab.id }"
      @click="emit('update:modelValue', tab.id)">
      {{ tab.label }}<span v-if="tab.count != null" class="app-tab-count">{{ tab.count }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick } from 'vue'

const props = defineProps<{
  id: string
  label: string
  modelValue: string
  tabs: { id: string; label: string; count?: number }[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
async function navigate(event: KeyboardEvent) {
  const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
  if (!offset && event.key !== 'Home' && event.key !== 'End') return
  const current = props.tabs.findIndex(tab => tab.id === props.modelValue)
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? props.tabs.length - 1
    : (current + offset + props.tabs.length) % props.tabs.length
  if (!props.tabs[next]) return
  event.preventDefault()
  emit('update:modelValue', props.tabs[next].id)
  const list = event.currentTarget as HTMLElement
  await nextTick()
  list.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
}
</script>
