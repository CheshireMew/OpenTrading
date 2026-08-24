export const buildMainPriceFormat = (data) => {
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

const markerPosition = (kind) => (kind.includes('entry') ? 'belowBar' : 'aboveBar')

const markerShape = (kind) => {
  if (kind === 'long_entry') return 'arrowUp'
  if (kind === 'short_entry') return 'arrowDown'
  return 'circle'
}

const markerColor = (kind) => {
  if (kind === 'long_entry') return '#059669'
  if (kind === 'short_entry') return '#dc2626'
  if (kind === 'long_exit') return '#0f766e'
  return '#be123c'
}

export const buildStrategyMarkers = (items) => items
  .map((item) => ({
    time: Math.floor(Number(item.time) / 1000),
    position: item.position || markerPosition(String(item.kind || '')),
    color: item.color || markerColor(String(item.kind || '')),
    shape: item.shape || markerShape(String(item.kind || '')),
    text: item.label || item.kind || '',
  }))
  .filter((item) => Number.isFinite(item.time))
  .sort((left, right) => left.time - right.time)
