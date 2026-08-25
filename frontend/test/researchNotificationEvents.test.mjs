import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isWindowsNotificationEvent,
  loadDeliveredNotificationIds,
} from '../src/modules/research/notificationEvents.ts'

const event = (overrides = {}) => ({
  id: 'event-1',
  entityType: 'alert',
  kind: 'alert_triggered',
  title: 'Alert',
  body: '',
  payload: { notificationChannels: ['windows'] },
  occurredAt: '2026-08-25T00:00:00Z',
  createdAt: '2026-08-25T00:00:00Z',
  ...overrides,
})

test('only undelivered alert events configured for Windows become desktop notifications', () => {
  assert.equal(isWindowsNotificationEvent(event(), new Set()), true)
  assert.equal(isWindowsNotificationEvent(event({ payload: { notificationChannels: ['in_app'] } }), new Set()), false)
  assert.equal(isWindowsNotificationEvent(event({ acknowledgedAt: '2026-08-25T00:01:00Z' }), new Set()), false)
  assert.equal(isWindowsNotificationEvent(event(), new Set(['event-1'])), false)
})

test('persisted notification ids are validated and bounded', () => {
  const values = Array.from({ length: 510 }, (_, index) => `event-${index}`)
  assert.equal(loadDeliveredNotificationIds(JSON.stringify(values)).length, 500)
  assert.deepEqual(loadDeliveredNotificationIds('{broken'), [])
})
