import assert from 'node:assert/strict'
import test from 'node:test'

import { createPortfolioSaveState } from '../src/modules/tools/portfolioBalance/saveState.ts'

test('an older save response cannot acknowledge edits made while it was in flight', () => {
  const state = createPortfolioSaveState()
  state.markDirty()
  const inFlightVersion = state.captureVersion()

  state.markDirty()
  state.acknowledge(inFlightVersion)

  assert.equal(state.isDirty(), true)
  state.acknowledge(state.captureVersion())
  assert.equal(state.isDirty(), false)
})
