import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
import * as vue from 'vue'

function delivery(t) {
  const exports = {}, events = []
  global.window = { isSecureContext: true, dispatchEvent: event => events.push(event.type), focus() {} }
  const code = ts.transpileModule(fs.readFileSync(new URL('../src/modules/research/alertDelivery.ts', import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  new Function('require', 'exports', code)(id => id === 'vue' ? vue : {}, exports)
  t.after(() => { for (const notice of exports.alertNotices.value) exports.dismissAlertNotice(notice.id) })
  return { ...exports, events }
}
const event = (channels) => ({ id: 'price-event', title: 'BTC price alert', body: 'Price reached 100', payload: { notificationChannels: channels } })

test('in-page alerts work without a system notification API', async t => {
  const alerts = delivery(t)
  await alerts.deliverAlertEvent(event(['in_app', 'windows']))
  assert.equal(alerts.alertNotices.value.length, 1)
  assert.ok(alerts.events.includes('opentrading:alert-triggered'))
  alerts.dismissAlertNotice('price-event')
  assert.equal(alerts.alertNotices.value.length, 0)
})

test('system notification and three-tone audio are delivered independently', async t => {
  const alerts = delivery(t), notifications = [], tones = []
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

test('blocked autoplay cannot hold system or in-page notifications', async t => {
  const alerts = delivery(t), notifications = []
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

test('each in-page alert disappears eight seconds after its own arrival', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const alerts = delivery(t)
  await alerts.deliverAlertEvent({ ...event(['in_app']), id: 'first' })
  t.mock.timers.tick(4000)
  await alerts.deliverAlertEvent({ ...event(['in_app']), id: 'second' })
  t.mock.timers.tick(3999)
  assert.deepEqual(alerts.alertNotices.value.map(item => item.id), ['first', 'second'])
  t.mock.timers.tick(1)
  assert.deepEqual(alerts.alertNotices.value.map(item => item.id), ['second'])
  t.mock.timers.tick(4000)
  assert.deepEqual(alerts.alertNotices.value, [])
})

test('a replaced notice gets a fresh timeout and manual dismissal cancels expiry', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const alerts = delivery(t)
  await alerts.deliverAlertEvent(event(['in_app']))
  t.mock.timers.tick(4000)
  await alerts.deliverAlertEvent(event(['in_app']))
  t.mock.timers.tick(4000)
  assert.equal(alerts.alertNotices.value.length, 1)
  alerts.dismissAlertNotice('price-event')
  assert.deepEqual(alerts.alertNotices.value, [])
  t.mock.timers.tick(8000)
  assert.deepEqual(alerts.alertNotices.value, [])
})
