import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildPortfolioChangeCommand,
  clonePortfolioSnapshot,
} from '../src/modules/tools/portfolioBalance/changeSet.ts'

const portfolio = (id, name = id) => ({
  id,
  name,
  assets: [{ id: `${id}-asset`, symbol: 'BTC', targetWeight: 100, units: 1, currentPrice: 1, seedValue: 1 }],
  strategy: { rebalanceBand: 5, minTradeAmount: 10, reviewFrequency: 'monthly' },
  tracking: { virtualCapital: 1, inceptionDate: '2026-01-01' },
  simulation: { initialCapital: 1, simulationStartDate: '2026-01-01' },
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
})

test('portfolio change set sends only changed documents and the authoritative order', () => {
  const acknowledged = { activePortfolioId: 'core', portfolios: [portfolio('core'), portfolio('satellite')] }
  const current = clonePortfolioSnapshot(acknowledged)
  current.portfolios[0].name = 'Core updated'
  current.portfolios.reverse()

  const command = buildPortfolioChangeCommand(current, acknowledged, 7)

  assert.equal(command.expectedRevision, 7)
  assert.deepEqual(command.portfolioOrder, ['satellite', 'core'])
  assert.deepEqual(command.changedPortfolios.map((item) => item.id), ['core'])
})

test('portfolio change set is empty only when content, active id, and order match', () => {
  const acknowledged = { activePortfolioId: 'core', portfolios: [portfolio('core'), portfolio('satellite')] }

  assert.equal(buildPortfolioChangeCommand(clonePortfolioSnapshot(acknowledged), acknowledged, 2), null)
  assert.notEqual(
    buildPortfolioChangeCommand({ ...clonePortfolioSnapshot(acknowledged), activePortfolioId: 'satellite' }, acknowledged, 2),
    null,
  )
})
