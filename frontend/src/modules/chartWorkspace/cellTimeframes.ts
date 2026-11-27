import { watchEffect, type Ref } from 'vue'
import type { ChartCell } from '@luxalgo/vela/workspace'
import { timeframeLabel } from '@luxalgo/vela/widget'
import type { ChartSymbol } from './api'
import { cw } from './locale'
import { fromVela, timeframes } from './provider'

const periods = [
  ['1', 'minute1'], ['5', 'minute5'], ['15', 'minute15'], ['30', 'minute30'],
  ['60', 'hour1'], ['240', 'hour4'], ['D', 'day'], ['W', 'week'], ['M', 'month'],
] as const

export function workspacePeriodOptions(symbol?: Pick<ChartSymbol, 'timeframes'>) {
  return periods.filter(([value]) => symbol?.timeframes.includes(timeframes[value]!))
    .map(([value, key]) => ({ value, label: cw(key) }))
}

export function installCellTimeframe(cell: ChartCell, deps: {
  symbols: Ref<ChartSymbol[]>
  select: (timeframe: string) => Promise<void>
  onError: (error: unknown) => void
}) {
  const meta = cell.host.querySelector<HTMLElement>('.vela-sl-meta')
  if (!meta) return () => {}
  const name = cell.host.querySelector<HTMLElement>('.vela-sl-symbol')
  const select = meta.ownerDocument.createElement('select')
  select.className = 'cw-cell-timeframe'
  // Keep the control outside Vela's venue segment, which it rewrites on every
  // market load and hides first when a multi-chart title runs out of room.
  meta.after(select)
  let optionSignature = ''
  function refresh() {
    const symbol = deps.symbols.value.find(item => item.id === fromVela(cell.symbol))
    const options = workspacePeriodOptions(symbol)
    const signature = JSON.stringify(options)
    if (signature !== optionSignature) {
      optionSignature = signature
      select.replaceChildren(...options.map(item => {
        const option = meta!.ownerDocument.createElement('option')
        option.value = item.value; option.textContent = item.label
        return option
      }))
    }
    select.value = options.find(item => timeframes[item.value] === (timeframes[cell.timeframe] ?? cell.timeframe))?.value ?? ''
    select.disabled = !options.length
    select.hidden = name?.style.display === 'none'
    select.setAttribute('aria-label', `${symbol?.name ?? fromVela(cell.symbol)} · ${cw('timeframe')}`)
    // Remove only the native period text; retain the venue and its separator.
    const label = timeframeLabel(cell.timeframe), text = meta!.textContent ?? ''
    if (text.endsWith(`· ${label}`)) meta!.textContent = text.slice(0, -label.length).trimEnd()
  }
  const change = (event: Event) => {
    event.stopPropagation()
    const value = select.value
    void deps.select(value).catch(deps.onError).finally(refresh)
  }
  const stopKey = (event: Event) => event.stopPropagation()
  select.addEventListener('change', change)
  select.addEventListener('keydown', stopKey)
  const observer = new MutationObserver(refresh)
  observer.observe(meta, { childList: true, characterData: true, subtree: true })
  if (name) observer.observe(name, { attributes: true, attributeFilter: ['style'] })
  const stopWatch = watchEffect(refresh)
  const offMarket = cell.chart.on('market:changed', refresh)
  return () => {
    observer.disconnect(); stopWatch(); offMarket()
    select.removeEventListener('change', change)
    select.removeEventListener('keydown', stopKey)
    select.remove()
  }
}
