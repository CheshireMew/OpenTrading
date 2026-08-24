import assert from 'node:assert/strict'
import test from 'node:test'

import { createPromiseLruCache } from '../src/modules/tools/portfolioBalance/promiseCache.ts'

test('promise cache deduplicates active loads and expires fulfilled entries', async () => {
  let now = 100
  let calls = 0
  const cache = createPromiseLruCache({
    maxEntries: 2,
    ttlMs: 50,
    now: () => now,
    clone: (value) => ({ ...value }),
  })
  const loader = async () => ({ call: ++calls })

  const [first, second] = await Promise.all([cache.load('btc', loader), cache.load('btc', loader)])
  assert.equal(calls, 1)
  assert.deepEqual(first, second)
  assert.notEqual(first, second)

  now = 151
  assert.deepEqual(await cache.load('btc', loader), { call: 2 })
})

test('promise cache evicts rejected loads so retries can recover', async () => {
  let calls = 0
  const cache = createPromiseLruCache({
    maxEntries: 2,
    ttlMs: 50,
    clone: (value) => value,
  })

  await assert.rejects(cache.load('btc', async () => {
    calls += 1
    throw new Error('temporary failure')
  }))
  assert.equal(await cache.load('btc', async () => ++calls), 2)
})
