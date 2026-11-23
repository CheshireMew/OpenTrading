import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import * as vue from 'vue'

function delivery() {
  const exports = {}, events = []
  global.window = { isSecureContext: true, dispatchEvent: event => events.push(event.type), focus() {} }
  const code = ts.transpileModule(fs.readFileSync(new URL('../src/modules/research/alertDelivery.ts', import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  new Function('require', 'exports', code)(id => id === 'vue' ? vue : {}, exports)
  return { ...exports, events }
}
const event = (channels) => ({ id: 'price-event', title: 'BTC price alert', body: 'Price reached 100', payload: { notificationChannels: channels } })

test('in-page alerts work without a system notification API', async () => {
  const alerts = delivery()
  await alerts.deliverAlertEvent(event(['in_app', 'windows']))
  assert.equal(alerts.alertNotices.value.length, 1)
  assert.ok(alerts.events.includes('opentrading:alert-triggered'))
  alerts.dismissAlertNotice('price-event')
  assert.equal(alerts.alertNotices.value.length, 0)
})

test('system notification and three-tone audio are delivered independently', async () => {
  const alerts = delivery(), notifications = [], tones = []
  global.Notification = class {
    static permission = 'granted'
    constructor(title, options) { notifications.push({ title, ...options }) }
  }
  window.Notification = Notification
  global.AudioContext = class {
    state = 'running'; currentTime = 0; destination = {}
    createOscillator() { return { frequency: { value: 0 }, connect() {}, start() { tones.push(true) }, stop() {}, disconnect() {} } }
    createGain() { return { gain: { setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, disconnect() {} } }
  }
  await alerts.enableAlertDelivery(true, true)
  await alerts.deliverAlertEvent(event(['in_app', 'windows', 'sound']))
  assert.equal(notifications.length, 1)
  assert.equal(notifications[0].tag, 'price-event')
  assert.equal(tones.length, 3)
  Notification.permission = 'denied'
  await alerts.deliverAlertEvent({ ...event(['in_app', 'windows', 'sound']), id: 'next' })
  assert.equal(notifications.length, 1)
  assert.equal(tones.length, 6)
  assert.equal(alerts.alertNotices.value.length, 2)
})

test('blocked autoplay cannot hold system or in-page notifications', async () => {
  const alerts = delivery(), notifications = []
  global.Notification = class {
    static permission = 'granted'
    constructor(title) { notifications.push(title) }
  }
  window.Notification = Notification
  global.AudioContext = class {
    state = 'suspended'
    resume() { return new Promise(() => {}) }
  }
  await alerts.deliverAlertEvent({ id: 'blocked', title: 'Blocked audio', payload: { notificationChannels: ['in_app', 'sound', 'windows'] } })
  assert.equal(alerts.alertNotices.value.length, 1)
  assert.equal(notifications.length, 1)
  assert.equal(alerts.alertDeliveryStatus.value, 'alertSoundBlocked')
})
