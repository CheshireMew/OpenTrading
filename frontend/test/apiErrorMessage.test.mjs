import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { buildSync } from 'esbuild'
import { AxiosError } from 'axios'

// Bundle the actual client so its TypeScript route imports run in Node too.
const bundled = buildSync({
  entryPoints: [fileURLToPath(new URL('../src/api/request.ts', import.meta.url))],
  bundle: true, platform: 'node', format: 'cjs', write: false,
}).outputFiles[0].text
const module = { exports: {} }
new Function('require', 'module', 'exports', bundled)(createRequire(import.meta.url), module, module.exports)
const { ApiRequestError, apiErrorMessage, normalizeApiError } = module.exports
const fallback = '无法读取数据状态，请重试。'

test('network and generic HTTP failures use the localized task recovery message', () => {
  const network = normalizeApiError(new AxiosError('Network Error', 'ERR_NETWORK'))
  assert.equal(apiErrorMessage(network, fallback), fallback)
  assert.equal(apiErrorMessage(new ApiRequestError('Request failed with status code 500', { status: 500 }), fallback), fallback)
  assert.equal(apiErrorMessage(new ApiRequestError('timeout of 15000ms exceeded'), fallback), fallback)
})

test('a specific backend error remains visible with its context', () => {
  const error = new ApiRequestError('BTC/USDT 在所选区间没有完整历史数据', {
    status: 503, payload: { detail: 'BTC/USDT 在所选区间没有完整历史数据' },
  })
  assert.equal(apiErrorMessage(error, fallback), error.detail)
})

test('validation responses keep the caller guidance instead of raw validation details', () => {
  const error = new ApiRequestError('validation failed', { status: 422, payload: { detail: 'validation failed' } })
  assert.equal(apiErrorMessage(error, fallback), fallback)
})

test('useful local errors are retained and empty errors use the fallback', () => {
  assert.equal(apiErrorMessage(new Error('文件中没有交易记录'), fallback), '文件中没有交易记录')
  assert.equal(apiErrorMessage(new Error(''), fallback), fallback)
})
