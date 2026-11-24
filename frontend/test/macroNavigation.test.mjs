import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

function load(storage) {
  const source = fs.readFileSync(new URL('../src/modules/market/macroSections.ts', import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(() => ({ getLocalStorage: () => storage }), exports)
  return exports
}

test('macro signals start with dollar liquidity and remember a valid browser selection', () => {
  const values = new Map()
  const section = load({ getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) })
  assert.equal(section.preferredMacroSection().id, 'dollar-liquidity')
  section.rememberMacroSection('MacroBitcoin')
  assert.equal(section.preferredMacroSection().id, 'bitcoin')
  section.rememberMacroSection('Settings')
  assert.equal(section.preferredMacroSection().id, 'bitcoin')
  section.rememberMacroSection('MacroDollarLiquidity')
  assert.equal(section.preferredMacroSection().id, 'dollar-liquidity')
})

test('unavailable or obsolete browser preferences fall back to dollar liquidity', () => {
  for (const storage of [null, { getItem: () => 'removed-section' }, { getItem() { throw new Error('Blocked storage') } }]) {
    assert.equal(load(storage).preferredMacroSection().id, 'dollar-liquidity')
  }
  assert.doesNotThrow(() => load(null).rememberMacroSection('MacroBitcoin'))
})
