export const asNumber = (value: unknown) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

export const percentChange = (current: unknown, previous: unknown, absoluteBaseline = false) => {
  const currentNumber = asNumber(current)
  const previousNumber = asNumber(previous)
  if (currentNumber === null || previousNumber === null || previousNumber === 0) return null
  const baseline = absoluteBaseline ? Math.abs(previousNumber) : previousNumber
  return ((currentNumber - previousNumber) / baseline) * 100
}
