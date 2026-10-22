import { DARK_PALETTE } from '@/theme/palette.mjs'
import type { ChartConfiguration, ChartDataset } from 'chart.js'

import { parseLocalIsoDate } from '@/utils/localDate'


export const HALVING_DATES = [
  { date: '2012-11-28', label: 'H1' },
  { date: '2016-07-09', label: 'H2' },
  { date: '2020-05-11', label: 'H3' },
  { date: '2024-04-20', label: 'H4' },
  { date: '2028-04-17', label: 'H5 (Est)', future: true },
] as const

export const LAST_HALVING_DATE_TEXT = '2024-04-20'
export const NEXT_HALVING_DATE_TEXT = '2028-04-17'
export const LAST_HALVING_DATE = parseLocalIsoDate(LAST_HALVING_DATE_TEXT) ?? new Date(2024, 3, 20)
export const NEXT_HALVING_ESTIMATE = parseLocalIsoDate(NEXT_HALVING_DATE_TEXT) ?? new Date(2028, 3, 17)
export const ONE_DAY_MS = 24 * 60 * 60 * 1000

type Translate = (key: string, params?: Record<string, unknown>) => string
type AnnotationMap = Record<string, Record<string, unknown>>

const buildPhaseAnnotations = (t: Translate, isDark: boolean, compact: boolean): AnnotationMap => Object.fromEntries(
  HALVING_DATES.flatMap((halving, index) => {
    const halvingTime = new Date(halving.date).getTime()
    return [
      [`acc_${index}`, {
        type: 'box',
        xMin: halvingTime - (500 * ONE_DAY_MS),
        xMax: halvingTime,
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        borderWidth: 0,
        label: {
          display: !compact,
          content: t('halving.accumulation'),
          color: isDark ? 'rgba(34, 197, 94, 0.8)' : 'rgba(21, 128, 61, 0.8)',
          font: { size: 10 },
          position: 'start',
          yAdjust: -20,
        },
      }],
      [`exp_${index}`, {
        type: 'box',
        xMin: halvingTime,
        xMax: halvingTime + (540 * ONE_DAY_MS),
        backgroundColor: 'rgba(249, 115, 22, 0.1)',
        borderWidth: 0,
        label: {
          display: !compact,
          content: t('halving.bullRun'),
          color: isDark ? 'rgba(249, 115, 22, 0.8)' : 'rgba(194, 65, 12, 0.8)',
          font: { size: 10 },
          position: 'start',
          yAdjust: -20,
        },
      }],
    ]
  }),
)

const buildAnnotations = (t: Translate, isDark: boolean, showPhases: boolean, compact: boolean): AnnotationMap => {
  const annotations: AnnotationMap = Object.fromEntries(HALVING_DATES.map((halving, index) => [
    `halving_${index}`,
    {
      type: 'line',
      scaleID: 'x',
      value: new Date(halving.date).getTime(),
      borderColor: isDark ? 'rgba(255, 255, 255, 0.3)' : 'rgba(0,0,0,0.3)',
      borderWidth: 2,
      borderDash: [6, 6],
      label: {
        display: !compact || index >= 3,
        content: halving.label,
        position: 'start',
        backgroundColor: isDark ? DARK_PALETTE.elevated : 'rgba(255, 255, 255, 1)',
        color: isDark ? '#fff' : '#000',
        font: { size: 11, weight: 'bold' },
        yAdjust: 0,
      },
    },
  ]))
  if (showPhases) Object.assign(annotations, buildPhaseAnnotations(t, isDark, compact))

  const now = Date.now()
  const h4 = new Date(HALVING_DATES[3].date).getTime()
  const h5 = new Date(HALVING_DATES[4].date).getTime()
  const bullEnd = h4 + (540 * ONE_DAY_MS)
  const accStart = h5 - (500 * ONE_DAY_MS)
  const [nextPhaseLabel, nextPhaseDays] = now < bullEnd
    ? [t('halving.bullRunEnds'), Math.ceil((bullEnd - now) / ONE_DAY_MS)]
    : now < accStart
      ? [t('halving.accStarts'), Math.ceil((accStart - now) / ONE_DAY_MS)]
      : [t('halving.nextHalvingPhase'), Math.ceil((h5 - now) / ONE_DAY_MS)]
  if (now > h4) {
    annotations.current_countdown = {
      type: 'line',
      scaleID: 'x',
      value: now,
      borderColor: isDark ? '#3B82F6' : '#2563EB',
      borderWidth: 2,
      borderDash: [2, 4],
      label: {
        display: true,
        content: compact ? t('halving.today') : [t('halving.today'), t('halving.daysTo', { days: nextPhaseDays, phase: nextPhaseLabel })],
        position: 'center',
        backgroundColor: isDark ? 'rgba(59, 130, 246, 0.9)' : 'rgba(37, 99, 235, 0.9)',
        color: '#fff',
        font: { size: 12, weight: 'bold' },
        yAdjust: compact ? 40 : 100,
      },
    }
  }
  return annotations
}

export const buildHalvingChartConfig = (options: {
  t: Translate
  isDark: boolean
  showPhases: boolean
  scaleType: 'logarithmic' | 'linear'
  seriesData: Array<{ x: number; y: number }>
  formatTick: (value: number) => string
  compact?: boolean
}): ChartConfiguration<'line'> => {
  const gridColor = options.isDark ? DARK_PALETTE.grid : 'rgba(0, 0, 0, 0.05)'
  const textColor = options.isDark ? DARK_PALETTE.muted : '#6B7280'
  const datasets: ChartDataset<'line'>[] = [{
    label: options.t('halving.btcPrice'),
    data: options.seriesData,
    borderColor: options.isDark ? '#FCD34D' : '#F59E0B',
    borderWidth: 1.5,
    pointRadius: 0,
    pointHitRadius: 10,
    tension: 0,
    parsing: false,
    normalized: true,
  }]
  return {
    type: 'line',
    data: { datasets },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      scales: {
        x: { type: 'time', time: { unit: 'year' }, grid: { color: gridColor }, border: { color: gridColor }, ticks: { color: textColor, maxTicksLimit: options.compact ? 5 : 12 } },
        y: {
          type: options.scaleType,
          position: 'right',
          grid: { color: gridColor },
          border: { color: gridColor },
          ticks: { color: textColor, maxTicksLimit: options.compact ? 6 : 11, callback: (value) => options.formatTick(Number(value)) },
        },
      },
      plugins: {
        annotation: { annotations: buildAnnotations(options.t, options.isDark, options.showPhases, Boolean(options.compact)) },
        decimation: { enabled: true, algorithm: 'lttb', samples: 600 },
        legend: { display: false },
        tooltip: {
          enabled: true,
          backgroundColor: options.isDark ? DARK_PALETTE.elevated : 'rgba(255, 255, 255, 0.9)',
          titleColor: options.isDark ? '#fff' : '#000',
          bodyColor: options.isDark ? '#fff' : '#000',
          borderColor: options.isDark ? DARK_PALETTE.grid : '#E5E7EB',
          borderWidth: 1,
        },
      },
    },
  }
}
