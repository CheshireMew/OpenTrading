import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { transpileModule, ModuleKind } from 'typescript'

async function loadTypescript(file) {
  const source = fs.readFileSync(new URL(file, import.meta.url), 'utf8')
  const { outputText } = transpileModule(source, { compilerOptions: { module: ModuleKind.ESNext } })
  return import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'))
}

test('saved chart markets and plugin state migrate without changing Pine sources', async () => {
  const { migrateWorkspaceState } = await loadTypescript('../src/modules/chartWorkspace/legacyState.ts')
  const source = 'indicator("Heimdall original")'
  const old = { symbol: 'heimdall:binance:spot:BTCUSDT', plugins: {
    'heimdall.pine': [{ scriptId: 'heimdall-v7-2', script: source }],
    'heimdall.marketDrawings': { markets: { 'heimdall:binance:spot:BTCUSDT': { lines: [1] } } },
  } }
  const migrated = migrateWorkspaceState(old)
  assert.equal(migrated.symbol, 'opentrading:binance:spot:BTCUSDT')
  assert.deepEqual(migrated.plugins['opentrading.pine'], [{ scriptId: 'opentrading-v7-2', script: source }])
  assert.deepEqual(migrated.plugins['opentrading.marketDrawings'].markets['opentrading:binance:spot:BTCUSDT'], { lines: [1] })
  assert.equal(old.plugins['heimdall.pine'][0].scriptId, 'heimdall-v7-2')
  assert.deepEqual(migrateWorkspaceState(migrated), migrated)
})

test('renamed preferences preserve current values and can read old keys without writing', async () => {
  const { readStorageValue } = await loadTypescript('../src/utils/storage.ts')
  const values = new Map([['heimdall_user_preferences', 'previous preferences']])
  const storage = { getItem: key => values.get(key) ?? null }
  assert.equal(readStorageValue(storage, 'opentrading_user_preferences'), 'previous preferences')
  values.set('opentrading_user_preferences', 'current preferences')
  assert.equal(readStorageValue(storage, 'opentrading_user_preferences'), 'current preferences')
  assert.equal(readStorageValue(storage, 'unrelated'), null)
})
