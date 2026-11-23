import { zigLibV1 } from './pineLibraries/ziglibV1.mjs'

export const pineLibraries = Object.freeze([zigLibV1])

function exportedFunction(library) {
  const original = library.source.slice(library.source.indexOf('export zigzag'), library.source.indexOf('\n[direction, z1, z2] = request.security')).trim()
  // PineTS 0.9.34 does not lower a history reference on an inline expression,
  // and highestbars/lowestbars require their implicit high/low source explicitly.
  // Name those same series before applying [1]; retain the original formulas.
  return original.replace(
    '    hr = ta.barssince(not (_high[-ta.highestbars(depth)] - _high > deviation*syminfo.mintick)[1])\n    lr = ta.barssince(not (_low - _low[-ta.lowestbars(depth)] > deviation*syminfo.mintick)[1])',
    '    highOffset = -ta.highestbars(high, depth)\n    lowOffset = -ta.lowestbars(low, depth)\n    highDeviation = _high[highOffset] - _high > deviation*syminfo.mintick\n    lowDeviation = _low - _low[lowOffset] > deviation*syminfo.mintick\n    hr = ta.barssince(not highDeviation[1])\n    lr = ta.barssince(not lowDeviation[1])')
}

// Resolve only exact, bundled library versions. User documents and exports keep
// the TradingView import; the compiler receives the original exported function.
export function linkPineLibraries(source, code) {
  if (!/\bimport\b/.test(code)) return { source, lineMap: [], imports: [] }
  const lines = source.split('\n'), masked = code.split('\n'), bindings = new Map()
  const lineMap = [], output = []
  const fail = (message, line) => { throw Object.assign(new Error(message), { line, column: 1 }) }
  for (let index = 0; index < masked.length; index++) {
    if (!/^\s*import\b/.test(masked[index])) continue
    const match = masked[index].match(/^\s*import\s+([A-Za-z_][\w]*\/[A-Za-z_][\w]*\/\d+)\s+as\s+([A-Za-z_]\w*)\s*$/)
    if (!match) fail('Pine 库导入格式应为 import 作者/库名/版本 as 别名', index + 1)
    const library = pineLibraries.find(item => item.id === match[1])
    if (!library) fail(`尚未接入 Pine 库 ${match[1]}，请提供该版本的完整源码`, index + 1)
    if (bindings.has(match[2])) fail(`重复的 Pine 库别名 ${match[2]}`, index + 1)
    const exported = exportedFunction(library)
    const name = '__opentrading_library_' + match[2] + '_zigzag'
    bindings.set(match[2], { line: index, name, functionSource: exported.replace(/^export zigzag\b/, name) })
  }
  for (let index = 0; index < lines.length; index++) {
    const imported = [...bindings.values()].find(binding => binding.line === index)
    if (imported) {
      const expanded = imported.functionSource.split('\n')
      output.push(...expanded); lineMap.push(...expanded.map(() => index + 1))
      continue
    }
    const edits = []
    for (const [alias, binding] of bindings) {
      const pattern = new RegExp('\\b' + alias + '\\s*\\.\\s*([A-Za-z_]\\w*)', 'g')
      for (const match of masked[index].matchAll(pattern)) {
        if (match[1] !== 'zigzag') fail(`Pine 库 ${alias} 没有导出 ${match[1]}`, index + 1)
        edits.push({ start: match.index, end: match.index + match[0].length, value: binding.name })
      }
    }
    let line = lines[index]
    for (const edit of edits.sort((a, b) => b.start - a.start)) line = line.slice(0, edit.start) + edit.value + line.slice(edit.end)
    output.push(line); lineMap.push(index + 1)
  }
  return { source: output.join('\n'), lineMap, imports: [...bindings.keys()] }
}
