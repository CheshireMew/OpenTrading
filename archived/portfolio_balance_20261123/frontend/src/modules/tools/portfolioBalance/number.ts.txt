export const PERCENT_BASE = 100

export const round = (value: number, digits = 2) => {
  const base = 10 ** digits
  return Math.round((value + Number.EPSILON) * base) / base
}

export const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

export const sanitizeNumber = (value: unknown, fallback = 0) => {
  const candidate = typeof value === 'number' && Number.isFinite(value) ? value : fallback
  return candidate >= 0 ? candidate : fallback
}

