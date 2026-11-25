import type { VelaWorkspace } from '@luxalgo/vela/workspace'
import type { InputValue } from '@luxalgo/vela'
import { cw } from './locale'

const guides: Record<string, string> = {
  sma: 'Ma', ema: 'Ema', rsi: 'Rsi', volume: 'Volume', 'bollinger-bands': 'Boll',
  macd: 'Macd', 'average-true-range': 'Atr', vwap: 'Vwap', 'average-directional-index': 'Adx',
}
const ADX_SOURCE = 'https://www.tradingview.com/support/solutions/43000502250-directional-movement-dmi/'

export function installIndicatorHelp(host: HTMLElement, workspace: () => VelaWorkspace | undefined) {
  const settings = (event: Event) => {
    const detail = (event as CustomEvent<{ id: string; values: Record<string, InputValue>; propValues: Record<string, InputValue>;
      tabs: { name: string; inputs: []; body: HTMLElement }[] }>).detail
    const handle = workspace()?.cells().flatMap(cell => cell.chart.indicators()).find(handle => handle.id === detail.id)
    if (handle) {
      // Read the chart's live values before the dialog takes its Cancel snapshot.
      detail.values = handle.inputValues()
      detail.propValues = handle.propValues()
    }
    const guide = guides[handle?.nativeType ?? '']
    if (!guide) return
    const body = document.createElement('div')
    body.className = 'cw-indicator-help'
    const section = (heading: string, content: string) => {
      const title = document.createElement('h3'), paragraph = document.createElement('p')
      title.textContent = cw(heading); paragraph.textContent = cw(content)
      body.append(title, paragraph)
    }
    section('indicatorWhat', 'guide' + guide + 'Intro')
    if (guide === 'Adx') {
      for (const [key, color] of [['Adx', '#3786ff'], ['PlusDi', '#089981'], ['MinusDi', '#f23645']]) {
        const row = document.createElement('p'), dot = document.createElement('span')
        dot.className = 'cw-indicator-help-swatch'; dot.style.background = color
        row.append(dot, document.createTextNode(cw('guideAdx' + key)))
        body.append(row)
      }
    }
    section('indicatorHow', 'guide' + guide + 'Use')
    section('indicatorParameters', 'guide' + guide + 'Parameters')
    if (guide === 'Adx') {
      const link = document.createElement('a')
      link.href = ADX_SOURCE; link.target = '_blank'; link.rel = 'noopener noreferrer'
      link.textContent = cw('indicatorReference')
      body.append(link)
    }
    detail.tabs.push({ name: cw('indicatorExplanation'), inputs: [], body })
  }
  host.addEventListener('opentrading:indicator-settings', settings)
  return () => host.removeEventListener('opentrading:indicator-settings', settings)
}
