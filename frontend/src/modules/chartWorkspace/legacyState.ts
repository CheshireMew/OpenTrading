// Upgrade identifiers in saved layouts without rewriting Pine sources or runs.
export function migrateWorkspaceState<T>(value: T): T {
  if (typeof value === 'string') {
    if (value === 'heimdall-v7-2') return 'opentrading-v7-2' as T
    if (value.startsWith('heimdall:')) return ('opentrading:' + value.slice(9)) as T
    return value
  }
  if (Array.isArray(value)) return value.map(migrateWorkspaceState) as T
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key.startsWith('heimdall.') ? 'opentrading.' + key.slice(9)
        : key.startsWith('heimdall:') ? 'opentrading:' + key.slice(9) : key,
      migrateWorkspaceState(item),
    ])) as T
  }
  return value
}
