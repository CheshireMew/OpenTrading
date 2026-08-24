import type {
  PriceFormatBuiltIn,
  SeriesMarker,
  SeriesMarkerBarPosition,
  SeriesMarkerShape,
  Time,
  UTCTimestamp,
} from 'lightweight-charts'

export interface TradingViewDataPoint {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export interface TradingViewVolumePoint {
  time: number
  value: number
  color?: string
}

export interface TradingViewStrategyMarker {
  time: number
  kind?: string
  position?: SeriesMarkerBarPosition
  color?: string
  shape?: SeriesMarkerShape
  label?: string
}

export const buildMainPriceFormat = (data: TradingViewDataPoint[]): PriceFormatBuiltIn => {
  const prices = data
    .flatMap((item) => [item.open, item.high, item.low, item.close])
    .map(Number)
    .filter((value) => Number.isFinite(value) && Math.abs(value) > 0)
  if (!prices.length) return { type: 'price', precision: 2, minMove: 0.01 }

  const minPrice = Math.min(...prices.map((value) => Math.abs(value)))
  const precision = minPrice >= 100
    ? 2
    : minPrice >= 1
      ? 4
      : Math.min(10, Math.max(2, Math.ceil(Math.abs(Math.log10(minPrice))) + 3))
  return { type: 'price', precision, minMove: 10 ** -precision }
}

const markerPosition = (kind: string): SeriesMarkerBarPosition => (
  kind.includes('entry') ? 'belowBar' : 'aboveBar'
)

const markerShape = (kind: string): SeriesMarkerShape => {
  if (kind === 'long_entry') return 'arrowUp'
  if (kind === 'short_entry') return 'arrowDown'
  return 'circle'
}

const markerColor = (kind: string) => {
  if (kind === 'long_entry') return '#059669'
  if (kind === 'short_entry') return '#dc2626'
  if (kind === 'long_exit') return '#0f766e'
  return '#be123c'
}

export const buildStrategyMarkers = (
  items: TradingViewStrategyMarker[],
): SeriesMarker<Time>[] => items
  .map((item): SeriesMarker<Time> => {
    const kind = String(item.kind || '')
    return {
      time: Math.floor(Number(item.time) / 1000) as UTCTimestamp,
      position: item.position || markerPosition(kind),
      color: item.color || markerColor(kind),
      shape: item.shape || markerShape(kind),
      text: item.label || kind,
    }
  })
  .filter((item) => Number.isFinite(item.time))
  .sort((left, right) => Number(left.time) - Number(right.time))
