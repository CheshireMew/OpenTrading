import { runPineComputation } from './pineComputation.mjs'

self.onmessage = async ({ data }) => {
  try {
    const result = await runPineComputation(data, {
      reportOnly: true,
      write: (name: string, value: unknown) => { if (name === 'progress.json') postMessage({ type: 'progress', value }) },
      hash: async (value: unknown) => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(value))))).map(byte => byte.toString(16).padStart(2, '0')).join(''),
    })
    postMessage({ type: 'completed', result })
  } catch (error) { postMessage({ type: 'error', message: error instanceof Error ? error.message : String(error) }) }
}
