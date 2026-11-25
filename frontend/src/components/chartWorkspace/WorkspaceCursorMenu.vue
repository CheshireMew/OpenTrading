<template>
  <Teleport v-if="controller.toolbarTarget.value" :to="controller.toolbarTarget.value">
    <div ref="trigger" class="vela-dtb-cell cw-cursor-control" :class="{'vela-open':open}" :data-active="controller.active.value ? '1' : ''">
      <button ref="mainButton" type="button" class="vela-dtb-icon" :title="label(controller.mode.value)" :aria-label="label(controller.mode.value)" aria-haspopup="menu" :aria-expanded="open" :aria-controls="menuId" @click="toggle(true)" @keydown.down.prevent="show">
        <span class="vela-dtb-hit"><span class="cw-cursor-glyph" :class="{'cw-demonstration-glyph':controller.mode.value==='highlight'}"><component :is="cursorIcons[controller.mode.value]" :size="24" stroke="1.25" aria-hidden="true" /></span></span>
      </button>
      <button type="button" class="vela-dtb-arrow" :title="cw('cursorMenu')" :aria-label="cw('cursorMenu')" aria-haspopup="menu" :aria-expanded="open" :aria-controls="menuId" @click="toggle(false)" @keydown.down.prevent="show">
        <span class="vela-dtb-hit"><span><IconChevronRight :size="9" stroke="1.25" aria-hidden="true" /></span></span>
      </button>
    </div>
  </Teleport>
  <Teleport to="body">
    <div v-if="open" :id="menuId" ref="menu" class="cw-cursor-menu" role="menu" :aria-label="cw('cursorMenu')" :style="position" @keydown="onKeydown">
      <button v-for="(value,index) in cursorModes" :key="value" type="button" role="menuitemradio" :aria-checked="controller.mode.value===value" :tabindex="index===focusIndex?0:-1" :data-cursor-mode="value" :title="value==='highlight'?cw('cursorHighlightHint'):undefined" :aria-description="value==='highlight'?cw('cursorHighlightHint'):undefined" @focus="focusIndex=index" @click="select(value)">
        <span class="cw-cursor-menu-glyph" :class="{'cw-demonstration-glyph':value==='highlight'}"><component :is="cursorIcons[value]" :size="24" stroke="1.25" aria-hidden="true" /></span>
        <span>{{ label(value) }}</span><kbd v-if="value==='highlight'">Alt</kbd>
      </button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import IconChevronRight from '@tabler/icons-vue/icons/IconChevronRight'
import { cursorIcons, cursorModes, type CursorMode } from '@/modules/chartWorkspace/cursorIcons'
import { cw } from '@/modules/chartWorkspace/locale'
import type { WorkspaceCursor } from '@/modules/chartWorkspace/workspaceCursor'

const props = defineProps<{ controller: WorkspaceCursor }>()
const menuId = useId(), open = ref(false), focusIndex = ref(0)
const trigger = ref<HTMLElement>(), mainButton = ref<HTMLButtonElement>(), menu = ref<HTMLElement>()
const position = ref({ left: '0px', top: '0px' })
const labels: Record<CursorMode, string> = { cross: 'cursorCross', dot: 'cursorDot', arrow: 'cursorArrow', highlight: 'cursorHighlight', eraser: 'cursorEraser' }
const label = (mode: CursorMode) => cw(labels[mode])
function place() {
  const rect = trigger.value?.getBoundingClientRect(), popup = menu.value
  if (!rect || !popup) return
  const width = popup.offsetWidth, height = popup.offsetHeight
  let left = rect.right + 6
  if (left + width > window.innerWidth - 8) left = rect.left - width - 6
  position.value = { left: Math.max(8, Math.min(left, window.innerWidth - width - 8)) + 'px', top: Math.max(8, Math.min(rect.top, window.innerHeight - height - 8)) + 'px' }
}
function focusItem() { menu.value?.querySelectorAll<HTMLButtonElement>('button')[focusIndex.value]?.focus() }
async function show() {
  open.value = true
  focusIndex.value = cursorModes.indexOf(props.controller.mode.value)
  await nextTick(); place(); focusItem()
}
function close(restoreFocus = false) { open.value = false; if (restoreFocus) mainButton.value?.focus() }
function toggle(activate: boolean) {
  if (activate) props.controller.choose(props.controller.mode.value)
  if (open.value) close(true); else void show()
}
function select(mode: CursorMode) { props.controller.choose(mode); close(true) }
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); return }
  if (event.key === 'Tab') { close(true); return }
  const current = focusIndex.value, count = cursorModes.length
  const next = event.key === 'ArrowDown' ? (current + 1) % count : event.key === 'ArrowUp' ? (current + count - 1) % count : event.key === 'Home' ? 0 : event.key === 'End' ? count - 1 : -1
  if (next >= 0) { event.preventDefault(); focusIndex.value = next; focusItem() }
}
function outside(event: Event) {
  if (open.value && !trigger.value?.contains(event.target as Node) && !menu.value?.contains(event.target as Node)) close()
}
function scroll(event: Event) { if (open.value && !menu.value?.contains(event.target as Node)) close() }
onMounted(() => { document.addEventListener('pointerdown', outside, true); document.addEventListener('scroll', scroll, true); window.addEventListener('resize', place) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', outside, true); document.removeEventListener('scroll', scroll, true); window.removeEventListener('resize', place) })
</script>

<style>
.cw-chart .cw-native-cursor{display:none!important}
.cw-cursor-mount{width:100%;flex-shrink:0}
.cw-cursor-glyph,.cw-cursor-menu-glyph{display:grid;place-items:center;width:24px;height:24px;flex-shrink:0;box-sizing:border-box}
.cw-cursor-glyph svg,.cw-cursor-menu-glyph svg{width:24px;height:24px;stroke-width:1.25}
.cw-demonstration-glyph{border:1.25px solid currentColor;border-radius:50%}
.cw-demonstration-glyph svg{width:18px;height:18px}
.cw-cursor-menu{position:fixed;z-index:80;box-sizing:border-box;width:218px;max-width:calc(100vw - 16px);max-height:calc(100dvh - 16px);overflow-y:auto;padding:6px;background:var(--ui-panel);color:var(--ui-text);border:1px solid var(--ui-border);border-radius:8px;box-shadow:0 8px 28px #0004;font:14px/1.3 Arial,"Microsoft YaHei",sans-serif}
.cw-cursor-menu button{display:flex;align-items:center;gap:12px;width:100%;height:42px;padding:0 12px;border:0;border-radius:5px;background:transparent;color:inherit;font:inherit;text-align:left;cursor:pointer}
.cw-cursor-menu button:hover{background:var(--ui-hover)}
.cw-cursor-menu button[aria-checked=true]{background:var(--ui-accent);color:var(--ui-onAccent)}
.cw-cursor-menu button:focus-visible{outline:1px solid currentColor;outline-offset:-3px}
.cw-cursor-menu kbd{margin-left:auto;font:inherit;font-size:11px;line-height:1.2;opacity:.7}
.cw-cursor-menu button[data-cursor-mode=eraser]{margin-top:6px;border-top:1px solid var(--ui-border);border-radius:0 0 5px 5px}
.cw-cursor-trail{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
[data-cw-cursor-mode=arrow] [data-cw-cursor-layer],[data-cw-cursor-mode=highlight] [data-cw-cursor-layer],[data-cw-cursor-mode=eraser] [data-cw-cursor-layer]{visibility:hidden}
[data-cw-pointer=cross]>canvas{cursor:crosshair!important}
[data-cw-pointer=dot]>canvas{cursor:var(--cw-dot-pointer)!important}
[data-cw-pointer=arrow]>canvas,[data-cw-pointer=highlight]>canvas{cursor:default!important}
[data-cw-pointer=eraser]>canvas{cursor:var(--cw-eraser-pointer)!important}
@media(pointer:coarse){.cw-cursor-menu button{height:44px}}
</style>
