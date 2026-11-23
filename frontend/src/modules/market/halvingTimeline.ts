import { DARK_PALETTE } from '@/theme/palette.mjs'
import type { ChartConfiguration, ChartDataset } from 'chart.js'

import type { BitcoinHalvingResponse } from './contracts'

const KNOWN_HALVING_TIMESTAMPS = ['2012-11-28', '2016-07-09', '2020-05-11', '2024-04-20']
  .map((date) => Date.parse(date))
const ONE_DAY_MS = 24 * 60 * 60 * 1000
const HALVING_WINDOW_MS = 500 * ONE_DAY_MS

type HalvingEvent = { timestamp: number; label: string }

export const buildHalvingTimeline = (estimate: BitcoinHalvingResponse | null) => {
  const dates = [...KNOWN_HALVING_TIMESTAMPS, ...(estimate?.confirmed_halvings_after_2024 ?? [])]
  const history = dates.map((timestamp, index) => ({ timestamp, label: `H${index + 1}` }))
  return {
    history,
    last: history[history.length - 1],
    next: estimate ? { timestamp: estimate.estimated_at, label: `H${history.length + 1} (Est)` } : null,
  }
}

type HalvingTimeline = ReturnType<typeof buildHalvingTimeline>

export const daysUntil = (timestamp: number, now: number) => Math.max(0, Math.ceil((timestamp - now) / ONE_DAY_MS))

type Translate = (key: string, params?: Record<string, unknown>) => string
type AnnotationMap = Record<string, Record<string, unknown>>

const buildPhaseAnnotations = (halvings: HalvingEvent[], t: Translate, isDark: boolean, compact: boolean): AnnotationMap => Object.fromEntries(
  halvings.flatMap(({ timestamp: halvingTime }, index) => [
    [`acc_${index}`, {
      type: 'box',
      xMin: halvingTime - HALVING_WINDOW_MS,
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
      xMax: halvingTime + HALVING_WINDOW_MS,
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
  ]),
)

const buildAnnotations = (
  timeline: HalvingTimeline, now: number, t: Translate, isDark: boolean, showPhases: boolean, compact: boolean,
): AnnotationMap => {
  const { history, last, next } = timeline
  const halvings = next ? [...history, next] : history
  const annotations: AnnotationMap = Object.fromEntries(halvings.map((halving, index) => [
    `halving_${index}`,
    {
      type: 'line',
      scaleID: 'x',
      value: halving.timestamp,
      borderColor: isDark ? 'rgba(255, 255, 255, 0.3)' : 'rgba(0,0,0,0.3)',
      borderWidth: 2,
      borderDash: [6, 6],
      label: {
        display: !compact || index >= history.length - 1,
        content: halving.label,
        position: 'start',
        backgroundColor: isDark ? DARK_PALETTE.elevated : 'rgba(255, 255, 255, 1)',
        color: isDark ? '#fff' : '#000',
        font: { size: 11, weight: 'bold' },
        yAdjust: 0,
      },
    },
  ]))
  if (showPhases) Object.assign(annotations, buildPhaseAnnotations(halvings, t, isDark, compact))

  const bullEnd = last.timestamp + HALVING_WINDOW_MS
  let nextPhase = now < bullEnd ? { label: 'halving.bullRunEnds', timestamp: bullEnd } : null
  if (!nextPhase && next) {
    const accStart = next.timestamp - HALVING_WINDOW_MS
    nextPhase = now < accStart
      ? { label: 'halving.accStarts', timestamp: accStart }
      : { label: 'halving.nextHalvingPhase', timestamp: next.timestamp }
  }
  if (now > last.timestamp) {
    annotations.current_countdown = {
      type: 'line',
      scaleID: 'x',
      value: now,
      borderColor: isDark ? '#3B82F6' : '#2563EB',
      borderWidth: 2,
      borderDash: [2, 4],
      label: {
        display: true,
        content: compact || !nextPhase ? t('halving.today') : [t('halving.today'), t('halving.daysTo', {
          days: daysUntil(nextPhase.timestamp, now),
          phase: t(nextPhase.label),
        })],
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
  timeline: HalvingTimeline
  now: number
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
        annotation: {
          annotations: buildAnnotations(options.timeline, options.now, options.t, options.isDark, options.showPhases, Boolean(options.compact)),
        },
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
