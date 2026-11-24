import { getDrawingType } from '@luxalgo/vela/plugin'
import { iconMarkup } from '@luxalgo/vela/ui'
import { h, render, type Component } from 'vue'
import IconCrosshair from '@tabler/icons-vue/icons/IconCrosshair'
import IconLine from '@tabler/icons-vue/icons/IconLine'
import IconArrowUpRight from '@tabler/icons-vue/icons/IconArrowUpRight'
import IconMinus from '@tabler/icons-vue/icons/IconMinus'
import IconMinusVertical from '@tabler/icons-vue/icons/IconMinusVertical'
import IconEqual from '@tabler/icons-vue/icons/IconEqual'
import IconAdjustmentsHorizontal from '@tabler/icons-vue/icons/IconAdjustmentsHorizontal'
import IconDimensions from '@tabler/icons-vue/icons/IconDimensions'
import IconBrush from '@tabler/icons-vue/icons/IconBrush'
import IconSquare from '@tabler/icons-vue/icons/IconSquare'
import IconLetterT from '@tabler/icons-vue/icons/IconLetterT'
import IconRuler2 from '@tabler/icons-vue/icons/IconRuler2'
import IconEraser from '@tabler/icons-vue/icons/IconEraser'
import IconMagnet from '@tabler/icons-vue/icons/IconMagnet'
import IconPencil from '@tabler/icons-vue/icons/IconPencil'
import IconCopy from '@tabler/icons-vue/icons/IconCopy'
import IconChartCandle from '@tabler/icons-vue/icons/IconChartCandle'
import IconChevronRight from '@tabler/icons-vue/icons/IconChevronRight'
import IconChevronsLeft from '@tabler/icons-vue/icons/IconChevronsLeft'
import IconChevronsRight from '@tabler/icons-vue/icons/IconChevronsRight'

// Use the library's original geometry, including its proportions and padding.
// Per-icon imports keep the rest of the icon collection out of the chart runtime.
const components: Record<string, Component> = {
  cursor: IconCrosshair, trendline: IconLine, ray: IconArrowUpRight,
  hline: IconMinus, vline: IconMinusVertical, parallelchannel: IconEqual,
  fibretracement: IconAdjustmentsHorizontal, datepricerange: IconDimensions,
  freehand: IconBrush, arrow: IconArrowUpRight, box: IconSquare, text: IconLetterT,
  ruler: IconRuler2, eraser: IconEraser, magnet: IconMagnet,
  'pen-lock': IconPencil, 'pen-sync': IconCopy, 'style-candles': IconChartCandle,
  'chevron-right': IconChevronRight, 'chevrons-left': IconChevronsLeft, 'chevrons-right': IconChevronsRight,
}

const utilityIcons = ['cursor', 'ruler', 'eraser', 'magnet', 'pen-lock', 'pen-sync', 'style-candles', 'chevron-right', 'chevrons-left', 'chevrons-right']
const scope = '.vela-dtb, .vela-dtb-flyout, .vela-widget-style'
const signature = (svg: Element) => `${svg.getAttribute('viewBox')}:${svg.innerHTML}`

export function installDrawingToolbarIcons(host: HTMLElement) {
  const document = host.ownerDocument
  const template = document.createElement('template')
  const icons = new Map<string, Element>()
  const iconHost = document.createElement('div')
  for (const [name, component] of Object.entries(components)) {
    const original = utilityIcons.includes(name) ? iconMarkup(name) : getDrawingType(name)?.icon
    if (!original) continue
    template.innerHTML = original
    const svg = template.content.querySelector('svg')
    if (!svg) continue
    render(h(component, { size: 24, stroke: 1.5, 'aria-hidden': 'true', focusable: 'false', 'data-cw-drawing-icon': name }), iconHost)
    icons.set(signature(svg), iconHost.firstElementChild!.cloneNode(true) as Element)
    render(null, iconHost)
  }

  const replace = (svg: Element) => {
    if (svg.hasAttribute('data-cw-drawing-icon') || !svg.closest(scope)) return
    const replacement = icons.get(signature(svg))
    if (replacement) svg.replaceWith(replacement.cloneNode(true))
  }
  const scan = (node: Node) => {
    if (!(node instanceof Element)) return
    if (node.matches('svg')) replace(node)
    else for (const svg of node.querySelectorAll('svg')) replace(svg)
  }

  // Vela caches utility SVGs before the public icon registry can be overridden.
  // Match their original geometry rather than translated button labels. Reapply
  // only to newly rendered icons when a tool, theme or toolbar layout changes.
  const observer = new MutationObserver(records => {
    observer.disconnect()
    for (const record of records) for (const node of record.addedNodes) scan(node)
    observe()
  })
  const observe = () => observer.observe(host, { subtree: true, childList: true })
  scan(host)
  observe()
  return () => observer.disconnect()
}
