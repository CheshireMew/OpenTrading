type Document = Record<string, any>
export const sameLayout = (a: unknown, b: unknown): boolean => {
  if (a === b) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false
  if (Array.isArray(a) !== Array.isArray(b)) return false
  const left = Object.keys(a), right = Object.keys(b)
  return left.length === right.length && left.every(key => Object.prototype.hasOwnProperty.call(b, key) && sameLayout((a as Document)[key], (b as Document)[key]))
}
const object = (value: unknown): value is Document => !!value && typeof value === 'object' && !Array.isArray(value)
const keyed = (value: unknown): value is Document[] => Array.isArray(value) && value.every(item => object(item) && typeof item.id === 'string')

// Reapply this window's changes to the latest server version. Unchanged fields
// follow the server; simultaneous edits to one field follow the current action.
export function mergeLayout(base: any, local: any, remote: any): any {
  if (sameLayout(base, local)) return remote
  if (sameLayout(base, remote) || sameLayout(local, remote)) return local
  if (keyed(base) && keyed(local) && keyed(remote)) {
    const before = new Map(base.map(item => [item.id, item])), ours = new Map(local.map(item => [item.id, item]))
    const theirs = new Map(remote.map(item => [item.id, item]))
    return [...new Set([...local.map(item => item.id), ...remote.map(item => item.id)])]
      .map(id => mergeLayout(before.get(id), ours.get(id), theirs.get(id))).filter(item => item !== undefined)
  }
  if (object(base) && object(local) && object(remote)) {
    // A viewport is one range. Combining a from/to pair from different windows
    // can produce an invalid interval or an unintended zoom level.
    if (typeof local.from === 'number' && typeof local.to === 'number') return local
    const result: Document = {}
    for (const key of new Set([...Object.keys(base), ...Object.keys(local), ...Object.keys(remote)])) {
      const value = mergeLayout(base[key], local[key], remote[key])
      if (value !== undefined) result[key] = value
    }
    // Keep a cell's market and its time window together, while still merging
    // unrelated indicators, drawings and presentation settings in that cell.
    if (typeof local.id === 'string' && typeof local.symbol === 'string') {
      const market = (cell: Document) => [cell.symbol, cell.provider, cell.timeframe, cell.session, cell.priceStyle, cell.ext?.['opentrading.viewport']]
      const source = sameLayout(market(base), market(local)) ? remote : local
      for (const key of ['symbol', 'provider', 'timeframe', 'session', 'priceStyle']) {
        if (key in source) result[key] = source[key]
        else delete result[key]
      }
      if (source.ext?.['opentrading.viewport'] !== undefined) result.ext = { ...result.ext, 'opentrading.viewport': source.ext['opentrading.viewport'] }
    }
    return result
  }
  return local
}
