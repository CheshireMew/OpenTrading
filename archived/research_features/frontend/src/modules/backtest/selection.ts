import { asNumber } from '@/utils/number'
import type { StrategyVersionResponse } from './contracts'

export type BacktestStrategySelection = {
  strategy_version: number
}

export const profitColorClass = (value: unknown) => {
  const numeric = asNumber(value)
  if (numeric === null) return 'text-gray-500'
  if (numeric > 0) return 'text-green-600 dark:text-green-400'
  if (numeric < 0) return 'text-red-600 dark:text-red-400'
  return 'text-gray-500'
}

export const defaultStrategyVersion = (versions: StrategyVersionResponse[]) => (
  versions.find((item) => item.is_default) || versions[0] || null
)

export const syncStrategyVersionSelection = (
  config: BacktestStrategySelection,
  versions: StrategyVersionResponse[],
) => {
  if (!versions.length) return false
  if (versions.find((item) => item.version === config.strategy_version)) return false
  const fallback = defaultStrategyVersion(versions)
  if (!fallback) return false
  config.strategy_version = fallback.version
  return true
}


