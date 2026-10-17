const escapeRegex = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const literal = value => value.replace(/\{'@'\}/g, '@')

// Saved errors and frozen workers predate localization. Translate only known
// application messages at presentation time; retain unknown engine diagnostics.
export function createMessageTranslator(catalogs, translate) {
  const exact = new Map(), patterns = []
  for (const catalog of catalogs) for (const [key, text] of Object.entries(catalog)) {
    const source = literal(text), names = [], parts = []
    let offset = 0
    for (const match of source.matchAll(/\{(\w+)\}/g)) {
      parts.push(escapeRegex(source.slice(offset, match.index)), '([\\s\\S]*?)')
      names.push(match[1]); offset = match.index + match[0].length
    }
    if (!names.length) exact.set(source, key)
    else {
      parts.push(escapeRegex(source.slice(offset)))
      patterns.push({ key, names, specificity: source.replace(/\{\w+\}/g, '').length,
        regex: new RegExp('^' + parts.join('') + '$') })
    }
  }
  patterns.sort((a, b) => b.specificity - a.specificity)
  function render(value, depth = 0) {
    const text = value == null ? '' : String(value)
    if (depth > 5) return text
    if (exact.has(text)) return translate(exact.get(text), {})
    if (text.startsWith('Error: ')) return render(text.slice(7), depth + 1)
    for (const { key, names, regex } of patterns) {
      const match = regex.exec(text)
      if (!match) continue
      const params = Object.fromEntries(names.map((name, i) => [name,
        name === 'detail' ? render(match[i + 1], depth + 1) : match[i + 1]]))
      return translate(key, params)
    }
    return text
  }
  return render
}
