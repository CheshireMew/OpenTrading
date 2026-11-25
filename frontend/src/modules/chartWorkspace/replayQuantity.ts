/** Plain decimal text keeps small contract sizes readable in inputs and labels. */
export function formatQuantity(value: number | undefined): string {
  if (value === undefined || !Number.isFinite(value)) return ''
  const text = String(value)
  if (!/[eE]/.test(text)) return text
  const [coefficient, exponent] = text.toLowerCase().split('e')
  const negative = coefficient!.startsWith('-'), unsigned = coefficient!.replace('-', '')
  const [integer, fraction = ''] = unsigned.split('.')
  const digits = integer! + fraction, point = integer!.length + Number(exponent)
  const decimal = point <= 0 ? '0.' + '0'.repeat(-point) + digits
    : point >= digits.length ? digits + '0'.repeat(point - digits.length)
      : digits.slice(0, point) + '.' + digits.slice(point)
  return (negative ? '-' : '') + decimal
}

/** Round down to whole contract steps without binary floating point dust. */
export function quantityAtPercent(available: number, percent: number, step: number): number {
  if (!Number.isFinite(available) || available <= 0 || !Number.isFinite(percent) || percent <= 0) return 0
  if (percent >= 100) return available
  if (!Number.isFinite(step) || step <= 0) step = 0.00000001
  const total = formatQuantity(available), increment = formatQuantity(step)
  const decimals = (text: string) => text.split('.')[1]?.length ?? 0
  const scale = Math.max(decimals(total), decimals(increment))
  const units = (text: string) => BigInt(text.replace('.', '')) * 10n ** BigInt(scale - decimals(text))
  const lot = units(increment), amount = units(total) * BigInt(Math.round(percent * 100)) / 10_000n / lot * lot
  const digits = amount.toString().padStart(scale + 1, '0')
  return Number(scale ? digits.slice(0, -scale) + '.' + digits.slice(-scale) : digits)
}

export function quantityPercent(quantity: number, available: number): number {
  return Number.isFinite(quantity) && available > 0
    ? Math.round(Math.max(0, Math.min(100, quantity / available * 100)) * 100) / 100 : 0
}

/** Convert a quote-currency budget into base units without exceeding the budget. */
export function quantityForAmount(amount: number, price: number, step = 0.00000001): number {
  if (![amount, price].every(value => Number.isFinite(value) && value > 0)) return 0
  if (!Number.isFinite(step) || step <= 0) step = 0.00000001
  const decimal = (value: number) => {
    const [whole, fraction = ''] = formatQuantity(value).split('.')
    return { units: BigInt(whole! + fraction), scale: fraction.length }
  }
  const budget = decimal(amount), rate = decimal(price), lot = decimal(step)
  const count = budget.units * 10n ** BigInt(rate.scale + lot.scale)
    / (rate.units * lot.units * 10n ** BigInt(budget.scale))
  const digits = (count * lot.units).toString().padStart(lot.scale + 1, '0')
  const quantity = Number(lot.scale ? digits.slice(0, -lot.scale) + '.' + digits.slice(-lot.scale) : digits)
  return Number.isFinite(quantity) ? quantity : 0
}
