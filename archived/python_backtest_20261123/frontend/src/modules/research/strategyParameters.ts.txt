import type { LocalBacktestParameter } from './generatedContracts'

export function parameterEnabled(spec: LocalBacktestParameter, values: Record<string, unknown>) {
  return (spec.enabled_when ?? []).every(c => {
    const value = values[c.parameter]
    if (c.operator === 'in') return Array.isArray(c.value) && c.value.includes(value)
    if (c.operator === 'ne') return value !== c.value
    if (c.operator === 'gt') return Number(value) > Number(c.value)
    return value === c.value
  })
}
export function parameterValue(spec: LocalBacktestParameter | undefined, value: unknown) {
  return spec?.options?.find(o => o.value === value)?.label ?? (typeof value === 'boolean' ? value ? '开启' : '关闭' : String(value ?? '—'))
}
