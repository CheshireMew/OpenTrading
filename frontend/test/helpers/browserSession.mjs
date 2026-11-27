import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { existsSync, readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { mkdir, mkdtemp } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = fileURLToPath(new URL('../../', import.meta.url))
const velaPatchRevision = createHash('sha256').update(readFileSync(new URL('../../scripts/patch-vela.mjs', import.meta.url))).digest('hex')

class Protocol {
  constructor(socket) {
    this.socket = socket
    this.sequence = 0
    this.pending = new Map()
    this.events = new Map()
    socket.addEventListener('message', ({ data }) => {
      const message = JSON.parse(String(data))
      if (message.id) {
        const pending = this.pending.get(message.id)
        if (!pending) return
        clearTimeout(pending.timer)
        this.pending.delete(message.id)
        if (message.error) pending.reject(new Error(JSON.stringify(message.error)))
        else pending.resolve(message.result)
      } else {
        const key = `${message.sessionId ?? ''}:${message.method}`
        this.events.get(key)?.(message.params)
      }
    })
    socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timer)
        pending.reject(new Error('Test browser protocol closed'))
      }
      this.pending.clear()
    })
  }
  send(method, params = {}, sessionId) {
    const id = ++this.sequence
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`Browser command timed out: ${method}`)) }, 15_000)
      this.pending.set(id, { resolve, reject, timer })
      this.socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }))
    })
  }
  wait(method, sessionId) {
    const key = `${sessionId}:${method}`
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.events.delete(key); reject(new Error(`Browser event timed out: ${method}`)) }, 15_000)
      this.events.set(key, value => { clearTimeout(timer); this.events.delete(key); resolve(value) })
    })
  }
}

export async function browserSession({ publicSite = true } = {}) {
  const executable = process.env.OPENTRADING_TEST_BROWSER ?? (process.platform === 'win32'
    ? path.join(process.env['ProgramFiles(x86)'] ?? process.env.ProgramFiles, 'Microsoft/Edge/Application/msedge.exe') : '')
  if (!executable || !existsSync(executable)) throw new Error('Set OPENTRADING_TEST_BROWSER to an installed Chromium browser; tests never install one')
  const evidence = process.env.OPENTRADING_TEST_ARTIFACTS ?? path.resolve(frontend, '../.runtime/tests/browser-persistence')
  await mkdir(evidence, { recursive: true })
  // A caller may reuse a closed, task-owned profile/cache between test runs.
  // Individual cases still receive fresh browser contexts for data isolation.
  const profile = process.env.OPENTRADING_TEST_PROFILE ?? await mkdtemp(path.join(evidence, 'browser-'))
  await mkdir(profile, { recursive: true })
  const { createServer } = await import('vite')
  const { default: vue } = await import('@vitejs/plugin-vue')
  const responses = new Map()
  const route = async (req, res, next) => {
    const handler = responses.get(new URL(req.url, 'http://127.0.0.1').pathname)
    if (handler) {
      try { const value = typeof handler === 'function' ? await handler(req) : handler; res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(value)) }
      catch (error) { res.statusCode = 500; res.end(String(error)) }
    } else if (req.url === '/__tests__/blank') {
      res.setHeader('Content-Type', 'text/html')
      res.end('<!doctype html><html><body><div id="app"></div></body></html>')
    } else if (/^\/api\/v1\/chart-workspace\/(defaults\/)?(layouts|watchlists|scripts)$/.test(req.url)) {
      res.setHeader('Content-Type', 'application/json')
      res.end('[]')
    } else if (req.url.startsWith('/api/')) {
      res.statusCode = 503
      res.end('Local test has no external market connection')
    } else next()
  }
  const server = await createServer({
    configFile: false, root: frontend, cacheDir: process.env.OPENTRADING_TEST_VITE_CACHE ?? path.join(profile, 'vite-cache'),
    plugins: [vue(), { name: 'offline-browser-test', configureServer: server => { server.middlewares.use(route) } }],
    resolve: { alias: { '@': path.join(frontend, 'src') } },
    define: { 'import.meta.env.VITE_PUBLIC_SITE': JSON.stringify(String(publicSite)), __INTLIFY_JIT_COMPILATION__: true },
    // Match the app config: a cached runtime from before a Vela patch cannot
    // exercise the current indicator dialog or drawing integration.
    optimizeDeps: { include: ['vue', 'vue-router', 'vue-i18n', 'axios', 'pinia', 'pinets'],
      esbuildOptions: { define: { __OPENTRADING_VELA_PATCH_REVISION__: JSON.stringify(velaPatchRevision) } },
    },
    server: { host: '127.0.0.1', port: 0, strictPort: false, proxy: {} },
    logLevel: 'error',
  })
  await server.listen()
  const origin = `http://127.0.0.1:${server.httpServer.address().port}`
  let child, protocol
  async function start() {
    child = spawn(executable, [
      ...(process.platform === 'win32' ? ['--edge-skip-compat-layer-relaunch'] : []),
      '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
      '--disable-background-networking', '--disable-component-update', '--disable-sync',
      '--disable-extensions', '--disable-background-timer-throttling', '--remote-debugging-port=0',
      '--disk-cache-size=5242880', `--user-data-dir=${profile}`, 'about:blank',
    ], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
    const endpoint = await new Promise((resolve, reject) => {
      let stderr = ''
      const timer = setTimeout(() => reject(new Error('No test browser debugging endpoint')), 15_000)
      child.once('error', error => { clearTimeout(timer); reject(error) })
      child.once('exit', code => { clearTimeout(timer); reject(new Error(`Test browser exited ${code}: ${stderr.slice(-1000)}`)) })
      child.stderr.on('data', chunk => {
        stderr = (stderr + String(chunk)).slice(-32_000)
        const address = /DevTools listening on (ws:\/\/[^\s]+)/.exec(stderr)?.[1]
        if (address) { clearTimeout(timer); resolve(address) }
      })
    })
    const socket = new WebSocket(endpoint)
    await once(socket, 'open')
    protocol = new Protocol(socket)
  }
  async function stop() {
    if (!child || child.exitCode !== null) return
    const finished = once(child, 'exit')
    await protocol?.send('Browser.close').catch(() => {})
    const timer = setTimeout(() => child.kill(), 10_000)
    try { await finished } finally { clearTimeout(timer) }
  }
  try { await start() } catch (error) { await stop(); await server.close(); throw error }
  return {
    profile, origin,
    respond: (pathname, value) => responses.set(pathname, value),
    context: async () => (await protocol.send('Target.createBrowserContext')).browserContextId,
    async page(context) {
      const { targetId } = await protocol.send('Target.createTarget', { url: 'about:blank', ...(context ? { browserContextId: context } : {}) })
      const { sessionId } = await protocol.send('Target.attachToTarget', { targetId, flatten: true })
      await protocol.send('Page.enable', {}, sessionId)
      const loaded = protocol.wait('Page.loadEventFired', sessionId)
      await protocol.send('Page.navigate', { url: origin + '/__tests__/blank' }, sessionId)
      await loaded
      return {
        viewport: (width, height) => protocol.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false }, sessionId),
        screenshot: async () => Buffer.from((await protocol.send('Page.captureScreenshot', { format: 'png' }, sessionId)).data, 'base64'),
        async evaluate(body, value) {
          const result = await protocol.send('Runtime.evaluate', {
            expression: `(async (input) => { ${body}\n})(${JSON.stringify(value) ?? 'undefined'})`, awaitPromise: true, returnByValue: true,
          }, sessionId)
          if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text)
          return result.result.value
        },
        close: () => protocol.send('Target.closeTarget', { targetId }),
      }
    },
    async restart() { await stop(); await start() },
    async close() { await stop(); await server.close() },
  }
}
