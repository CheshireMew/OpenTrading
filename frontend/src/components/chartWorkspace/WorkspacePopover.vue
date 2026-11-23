<template>
  <details ref="surface">
    <summary>{{ label }}</summary>
    <slot />
  </details>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
defineProps<{ label: string }>()
const surface = ref<HTMLDetailsElement>()
function pointer(event: PointerEvent) {
  if (surface.value?.open && !surface.value.contains(event.target as Node)) surface.value.open = false
}
function keyboard(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !surface.value?.open) return
  event.preventDefault()
  surface.value.open = false
  surface.value.querySelector('summary')?.focus()
}
onMounted(() => { document.addEventListener('pointerdown', pointer); document.addEventListener('keydown', keyboard) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', pointer); document.removeEventListener('keydown', keyboard) })
</script>
