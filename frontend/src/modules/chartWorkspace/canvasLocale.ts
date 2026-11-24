import { watch } from 'vue'
import i18n from '@/i18n'

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export function chartDateText(text: string): string {
  if (i18n.global.locale.value === 'en') return text
  const date = text.match(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) (\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) '(\d{2})( \d{2}:\d{2})?$/)
  if (date) return `${date[4]}年${months.indexOf(date[3]) + 1}月${date[2]}日 周${'日一二三四五六'[weekdays.indexOf(date[1])]}${date[5] ?? ''}`
  const tick = text.match(/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?: (\d{1,2}))?$/)
  return tick ? `${months.indexOf(tick[1]) + 1}月${tick[2] ? tick[2] + '日' : ''}` : text
}

// Vela 0.7.6 has no date formatter option. Adapt only the native axes and
// crosshair canvases, including measurement so translated chips fit. Pine
// plots, user drawings and the global canvas prototype are left untouched.
export function localizeCanvasDates(host: HTMLElement, repaint: () => void) {
  const canvases = [...host.querySelectorAll('canvas')].slice(-3)
  const restores: (() => void)[] = []
  for (const canvas of [canvases[0], canvases[2]]) {
    const context = canvas?.getContext('2d')
    if (!context) continue
    const fill = context.fillText, stroke = context.strokeText, measure = context.measureText
    context.fillText = function (text, x, y, maxWidth) {
      const value = chartDateText(text)
      if (maxWidth === undefined) fill.call(this, value, x, y)
      else fill.call(this, value, x, y, maxWidth)
    }
    context.strokeText = function (text, x, y, maxWidth) {
      const value = chartDateText(text)
      if (maxWidth === undefined) stroke.call(this, value, x, y)
      else stroke.call(this, value, x, y, maxWidth)
    }
    context.measureText = function (text) { return measure.call(this, chartDateText(text)) }
    restores.push(() => { context.fillText = fill; context.strokeText = stroke; context.measureText = measure })
  }
  const stop = watch(i18n.global.locale, repaint)
  return () => { stop(); for (const restore of restores) restore() }
}
