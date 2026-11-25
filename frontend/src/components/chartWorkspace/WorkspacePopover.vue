<template>
  <details ref="surface" @toggle="toggled">
    <summary><slot name="trigger">{{ label }}</slot></summary>
    <slot />
  </details>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onBeforeUnmount, onDeactivated, ref } from 'vue'
defineProps<{ label: string }>()
const surface = ref<HTMLDetailsElement>()
let panel: HTMLElement | undefined, observer: ResizeObserver | undefined
const close = (restoreFocus = true) => {
  if (!surface.value?.open) return
  surface.value.open = false
  if (panel?.matches(':popover-open')) panel.hidePopover()
  if (restoreFocus) surface.value.querySelector('summary')?.focus()
}
defineExpose({ close })
function place() {
  const trigger = surface.value?.querySelector('summary')?.getBoundingClientRect()
  if (!surface.value?.open || !trigger || !panel) return
  const width = panel.offsetWidth, height = panel.offsetHeight
  const below = window.innerHeight - trigger.bottom - 8, above = trigger.top - 8
  const top = height > below && above > below ? trigger.top - height - 5 : trigger.bottom + 5
  panel.style.left = Math.max(8, Math.min(trigger.left, window.innerWidth - width - 8)) + 'px'
  panel.style.top = Math.max(8, Math.min(top, window.innerHeight - height - 8)) + 'px'
}
async function toggled() {
  if (!surface.value?.open) { observer?.disconnect(); if (panel?.matches(':popover-open')) panel.hidePopover(); return }
  await nextTick()
  if (!surface.value?.open) return
  panel = surface.value.querySelector<HTMLElement>(':scope > :not(summary)') ?? undefined
  if (!panel) return
  panel.setAttribute('popover', 'manual')
  panel.classList.add('cw-popover-panel')
  Object.assign(panel.style, { position: 'fixed', inset: 'auto', margin: '0', boxSizing: 'border-box', maxWidth: 'calc(100vw - 16px)', maxHeight: 'calc(100dvh - 16px)', overflow: 'auto' })
  if (!panel.matches(':popover-open')) panel.showPopover()
  observer?.disconnect(); observer = new ResizeObserver(place)
  observer.observe(panel); observer.observe(surface.value)
  place()
}
const modal = () => close(false)
function pointer(event: PointerEvent) {
  if (surface.value?.open && !surface.value.contains(event.target as Node)) close(false)
}
function keyboard(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !surface.value?.open) return
  event.preventDefault()
  close()
}
onMounted(() => { document.addEventListener('pointerdown', pointer); document.addEventListener('keydown', keyboard); window.addEventListener('resize', place); window.addEventListener('scroll', place, true); window.addEventListener('opentrading:modal-open', modal) })
onDeactivated(() => close(false))
onBeforeUnmount(() => { close(false); observer?.disconnect(); document.removeEventListener('pointerdown', pointer); document.removeEventListener('keydown', keyboard); window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); window.removeEventListener('opentrading:modal-open', modal) })
</script>
