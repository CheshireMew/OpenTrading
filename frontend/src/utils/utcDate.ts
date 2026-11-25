/** Legacy offset-free API timestamps are UTC. Date-only input stays ISO UTC. */
export function parseUtcDate(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null
  const input = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(value)
    && !/(Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value.replace(' ', 'T') + 'Z' : value
  const date = input instanceof Date ? input : new Date(input)
  return Number.isFinite(date.getTime()) ? date : null
}
