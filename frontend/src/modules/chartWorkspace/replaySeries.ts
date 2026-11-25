import { chartApi, type ChartSymbol, type ChartBar } from './api'
import { fromVela, timeframes } from './provider'

// PineTS request.security expects a venue:ticker identity with a single colon.
export function pineReplaySymbol(info: ChartSymbol) {
  return `${info.exchange.toUpperCase()}:${info.symbol}${info.market === 'usdm' ? '.P' : ''}`
}
export function resolveReplaySymbol(value: string, catalog: ChartSymbol[], primary: ChartSymbol) {
  const plain = fromVela(value.split(';')[0]!)
  return catalog.find(info => info.id === plain || pineReplaySymbol(info) === plain) ??
    catalog.find(info => info.symbol === plain.replace(/\.P$/, '') && info.exchange === primary.exchange &&
      info.market === (plain.endsWith('.P') ? 'usdm' : primary.market))
}

/** Bypass the live chart cache: it may already contain bars after the replay cutoff. */
export async function loadReplaySeries(info: ChartSymbol, timeframe: string,
  range: { from?: number; to?: number; limit?: number }, cutoff: number, signal?: AbortSignal): Promise<ChartBar[]> {
  const tf = timeframes[timeframe] ?? timeframe, end = Math.min(range.to ?? cutoff, cutoff)
  let cursor = range.from
  const count = range.limit ?? (cursor === undefined ? 1000 : Infinity), rows: ChartBar[] = []
  while (rows.length < count && (cursor === undefined || cursor < end)) {
    const query: Record<string, string | number> = { symbol: info.id, timeframe: tf, end, limit: Math.min(1000, count - rows.length) }
    if (cursor !== undefined) query.start = cursor
    const result = await chartApi.replayBars(query, signal)
    const batch = result.bars.filter(bar => bar.closed && bar.closeTime <= end && (cursor === undefined || bar.time >= cursor))
    if (!batch.length) break
    rows.push(...batch)
    if (cursor === undefined) break
    const next = batch[batch.length - 1]!.closeTime
    if (next <= cursor) break
    cursor = next
  }
  return rows
}
