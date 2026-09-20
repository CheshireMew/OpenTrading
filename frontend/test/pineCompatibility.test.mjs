import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { checkPine, pineError } from '../src/modules/chartWorkspace/pineCompatibility.mjs'
test('original v7.2 passes supported Pine capability gate',()=>{
  checkPine(fs.readFileSync(new URL('../../strategies/pine/eth_ema55_manual_chart_v7_2.pine',import.meta.url),'utf8'))
})
test('rejects unsupported operations with source line, ignores strings and comments',()=>{
  checkPine('//@version=6\nindicator("request.financial()")\n// strategy.oca.cancel\nplot(close)')
  assert.throws(()=>checkPine('//@version=6\nindicator("I")\nx = request.financial("x", "x", "x")'),e=>e.line===3&&e.message.includes('外部数据'))
  assert.throws(()=>checkPine('//@version=4\nstudy("I")'),/version/)
  checkPine('//@version=6\nindicator("I")\nvarip   int ticks = 0\nplot(ticks)')
  assert.throws(()=>checkPine('//@version=6\nindicator("I")\nvarip MyType state = na'),/自定义类型/)
})

test('preserves compiler source position across worker messages',()=>{
  const error=pineError({message:"Failed to transpile Pine Script version 6: Unexpected token RPAREN ')' at 3:6"})
  assert.equal(error.line,3)
  assert.equal(error.column,6)
  assert.equal(pineError({message:'Runtime failure'}).line,undefined)
})
