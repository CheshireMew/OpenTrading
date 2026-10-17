// Derive this from the persisted closed-trade totals so historical runs work too.
// Missing or one-sided samples have no observed win/loss ratio.
export function payoffRatio(summary) {
  const { grossprofit, grossloss, wintrades, losstrades } = summary ?? {}
  if (![grossprofit, grossloss, wintrades, losstrades].every(Number.isFinite)) return null
  if (wintrades <= 0 || losstrades <= 0 || grossprofit <= 0 || grossloss === 0) return null
  const ratio = (grossprofit / wintrades) / (Math.abs(grossloss) / losstrades)
  return Number.isFinite(ratio) ? ratio : null
}
