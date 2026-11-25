import { h, render, type Component } from 'vue'
import IconPlus from '@tabler/icons-vue/icons/IconPlus'
import IconPointFilled from '@tabler/icons-vue/icons/IconPointFilled'
import IconPointer from '@tabler/icons-vue/icons/IconPointer'
import IconEraser from '@tabler/icons-vue/icons/IconEraser'

export const cursorIcons = { cross: IconPlus, dot: IconPointFilled, arrow: IconPointer, highlight: IconPointer, eraser: IconEraser }
export type CursorMode = keyof typeof cursorIcons
export const cursorModes = Object.keys(cursorIcons) as CursorMode[]

// Keep the actual mouse pointer consistent with the library icon, with a white
// halo so it remains legible on both chart themes and over candles.
export function cursorImage(icon: Component, hotspot: string) {
  const host = document.createElement('div')
  render(h(icon, { size: 24, stroke: 1.5, color: '#202020', style: { filter: 'drop-shadow(0 0 1px white) drop-shadow(0 0 1px white)' } }), host)
  const svg = host.innerHTML
  render(null, host)
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${hotspot}, auto`
}
