import assert from 'node:assert/strict'
import test from 'node:test'
import { fillMarkers, signalMarkers, tradeColors } from '../src/modules/research/tradePresentation.ts'

test('both reversal directions use distinct saved label conventions', () => {
  const fills = [
    { timestamp: 1, action: 'long', trade_id: 1, phase: 'open' },
    { timestamp: 2, action: 'close', trade_id: 1, phase: 'open', reason: 'signal' },
    { timestamp: 2, action: 'short', trade_id: 2, phase: 'intrabar' },
    { timestamp: 3, action: 'close', trade_id: 2, phase: 'open', reason: 'reversal' },
    { timestamp: 3, action: 'long', trade_id: 3, phase: 'open' },
  ]
  assert.deepEqual(fillMarkers(fills, []).map(m => [m.label,m.color]), [
    ['做多',tradeColors.long], ['平仓做空',tradeColors.short], ['平仓做多',tradeColors.long],
  ])
  assert.equal(fillMarkers(fills, [], 1).at(-1).label, '平多')
})

test('stops and ambiguous entry-bar losses remain separate; unknown side is never guessed', () => {
  const fills = [
    { timestamp: 1, action: 'long', trade_id: 1, phase: 'intrabar' },
    { timestamp: 1, action: 'close', trade_id: 1, phase: 'intrabar', reason: 'stop_loss' },
    { timestamp: 1, action: 'short', trade_id: 2, phase: 'intrabar' },
    { timestamp: 2, action: 'close', trade_id: 2, phase: 'intrabar', reason: 'profit_protection' },
  ]
  assert.deepEqual(fillMarkers(fills, []).map(m => m.label), ['做多','止损','做空','止损'])
  assert.equal(fillMarkers([{timestamp: 1,action:'close',trade_id:99,reason:'signal'}],[])[0].label,'平仓')
  assert.deepEqual(signalMarkers([{timestamp:1,action:'long'},{timestamp:2,action:'short'}]).map(m=>m.color), [tradeColors.long,tradeColors.short])
})
