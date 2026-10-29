import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import { effectScope, nextTick } from 'vue'

const source = fs.readFileSync(new URL('../src/composables/usePageLayout.ts', import.meta.url), 'utf8')
const code = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 })
  .replace("from 'vue'", `from '${import.meta.resolve('vue')}'`)
const { usePageLayout } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

test('page preferences restore independently without persisting search or computed results', async () => {
  const values = new Map([['opentrading:layout:market', 'split']])
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) } })
  const scope = effectScope()
  try {
    const [market, dca] = scope.run(() => [usePageLayout('market', ['table', 'split'], 'table'), usePageLayout('dca', ['split', 'results'], 'split')])
    assert.equal(market.value, 'split')
    assert.equal(dca.value, 'split')
    dca.value = 'results'
    await nextTick()
    assert.deepEqual([...values], [['opentrading:layout:market', 'split'], ['opentrading:layout:dca', 'results']])
  } finally { scope.stop(); if (previous) Object.defineProperty(globalThis, 'localStorage', previous); else Reflect.deleteProperty(globalThis, 'localStorage') }
})

test('obsolete preferences and unavailable storage leave a usable session layout', async () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  const scope = effectScope()
  try {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => 'removed-layout', setItem: () => { throw Error('blocked') } } })
    const layout = scope.run(() => usePageLayout('market', ['table', 'split'], 'table'))
    assert.equal(layout.value, 'table')
    layout.value = 'split'
    await nextTick()
    assert.equal(layout.value, 'split')
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get: () => { throw Error('blocked') } })
    assert.equal(scope.run(() => usePageLayout('market', ['table', 'split'], 'table')).value, 'table')
  } finally { scope.stop(); if (previous) Object.defineProperty(globalThis, 'localStorage', previous); else Reflect.deleteProperty(globalThis, 'localStorage') }
})
