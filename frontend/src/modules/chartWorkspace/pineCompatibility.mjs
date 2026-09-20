export const PINE_ENGINE_VERSION = '0.9.34'
export const unsupported = [
  ['(?:^|\\n)[ \\t]+varip\\b|\\bvarip\\s+(?:array|matrix|map)\\b', 'varip 当前支持全局标量，暂不支持局部变量或集合'],
  ['^varip[ \\t]+(?=\\S)(?!(?:(?:int|float|bool|string|color)[ \\t]+)?[A-Za-z_]\\w*[ \\t]*=)', 'varip 当前不支持自定义类型或解构声明'],
  ['request\\.(financial|earnings|dividends|economic|currency_rate|seed|splits)\\s*\\(', '该外部数据源尚未接入'],
  ['\\bimport\\s+', '暂不支持外部 Pine 库，请提供完整源码'],
  ['\\boca_(name|type)\\s*=|strategy\\.oca\\.', '暂不支持 OCA 订单联动'],
  ['strategy\\.(margin_liquidation_price|convert_to_account|convert_to_symbol)', '暂不支持强平价格或跨币种换算'],
  ['\\buse_bar_magnifier\\s*=\\s*true', '暂不支持 Bar Magnifier 成交模拟'],
  ['barmerge\\.lookahead_on', '暂不支持使用未来数据的 lookahead_on'],
]

// Preserve offsets and newlines for diagnostics, but ignore comments and literals.
export function codeOnly(source) {
  return source.replace(/\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g,
    value => value.replace(/[^\n]/g, ' '))
}
export function checkPine(source) {
  const version = source.match(/^\s*\/\/@version\s*=\s*(\d+)/m)
  if (!version || !['5', '6'].includes(version[1])) throw new Error('请使用带有 //@version=5 或 //@version=6 声明的 Pine 脚本')
  const code = codeOnly(source)
  for (const [pattern, explanation] of unsupported) {
    const match = new RegExp(pattern,'m').exec(code)
    if (match) {
      const before = source.slice(0, match.index)
      const line = before.split('\n').length
      const column = match.index - before.lastIndexOf('\n')
      const error = new Error(`${explanation}（第 ${line} 行，第 ${column} 列）`)
      Object.assign(error, {line, column})
      throw error
    }
  }
}

export function pineError(value) {
  const original = value instanceof Error ? value : new Error(typeof value === 'string' ? value : value?.message ?? String(value))
  const location = original.message.match(/\bat (\d+):(\d+)\b|\bline (\d+)(?:[:,] (?:column )?(\d+))?/i)
  const line = value?.line ?? (location ? Number(location[1] ?? location[3]) : undefined)
  const column = value?.column ?? (location ? Number(location[2] ?? location[4] ?? 1) : undefined)
  if (line) Object.assign(original, {line, column})
  if (/^Failed to transpile/.test(original.message))
    original.message = `脚本编译失败${line ? `（第 ${line} 行，第 ${column} 列）` : ''}：${original.message}`
  return original
}
