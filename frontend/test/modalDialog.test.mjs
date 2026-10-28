import assert from 'node:assert/strict'
import test from 'node:test'
import { createRenderer, h, markRaw, nextTick, ref } from 'vue'
import { useModalDialog } from '../src/composables/useModalDialog.ts'

// Exercise Vue's real watchers and unmount hooks without adding a DOM runtime.
// Layout, native focus and pointer behavior are also checked in the browser.
class Element {
  constructor({ visible = true, disabled = false } = {}) {
    this.visible = visible
    this.disabled = disabled
    this.isConnected = true
    this.children = []
    this.tabIndex = 0
    markRaw(this)
  }
  querySelectorAll() { return this.children }
  hasAttribute(name) { return name === 'disabled' && this.disabled }
  closest() { return null }
  getClientRects() { return this.visible ? [{}] : [] }
  contains(element) { return this === element || this.children.includes(element) }
  focus() { document.activeElement = this }
}

const listeners = new Set()
globalThis.HTMLElement = Element
globalThis.document = { body: { style: { overflow: '' } }, activeElement: null }
globalThis.window = {
  addEventListener(_name, fn) { listeners.add(fn) },
  removeEventListener(_name, fn) { listeners.delete(fn) },
}
globalThis.getComputedStyle = () => ({ visibility: 'visible' })

const { render } = createRenderer({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  insert() {}, remove() {}, patchProp() {}, setText() {}, setElementText() {},
  parentNode: () => null, nextSibling: () => null,
})
const settle = async () => { await nextTick(); await nextTick() }
function mount(initialFocus, initiallyOpen = false) {
  const open = ref(initiallyOpen)
  let dialog
  const host = {}
  render(h({ setup() {
    dialog = useModalDialog(open, () => { open.value = false }, initialFocus)
    return () => null
  } }), host)
  const element = new Element()
  dialog.dialogRef.value = element
  return { open, element, unmount: () => render(null, host) }
}
function key(key, shiftKey = false) {
  const event = { key, shiftKey, prevented: false, stopped: false,
    preventDefault() { this.prevented = true },
    stopImmediatePropagation() { this.stopped = true },
  }
  for (const fn of listeners) { fn(event); if (event.stopped) break }
  return event
}

test('Tab ignores hidden and disabled controls and recovers focus from outside the dialog', async () => {
  const modal = mount()
  const hidden = new Element({ visible: false })
  const disabled = new Element({ disabled: true })
  const first = new Element(), last = new Element()
  modal.element.children = [hidden, disabled, first, last]
  modal.open.value = true
  await settle()
  assert.equal(document.activeElement, first)
  assert.equal(key('Tab', true).prevented, true)
  assert.equal(document.activeElement, last)
  key('Tab')
  assert.equal(document.activeElement, first)
  new Element().focus()
  key('Tab')
  assert.equal(document.activeElement, first)
  modal.unmount()
})

test('Escape closes only the top dialog and keeps the parent scroll lock and focus', async () => {
  const opener = new Element()
  opener.focus()
  document.body.style.overflow = 'clip'
  const parent = mount(), child = mount()
  const parentButton = new Element(), childButton = new Element()
  parent.element.children = [parentButton]
  child.element.children = [childButton]
  parent.open.value = true
  await settle()
  child.open.value = true
  await settle()
  key('Escape')
  await settle()
  assert.equal(parent.open.value, true)
  assert.equal(child.open.value, false)
  assert.equal(document.body.style.overflow, 'hidden')
  assert.equal(document.activeElement, parentButton)
  parent.unmount()
  child.unmount()
  await settle()
  assert.equal(document.body.style.overflow, 'clip')
  assert.equal(document.activeElement, opener)
  assert.equal(listeners.size, 0)
  document.body.style.overflow = ''
})

test('an explicit input receives initial focus and a closed dialog cannot reclaim it', async () => {
  const opener = new Element(), input = new Element(), close = new Element()
  opener.focus()
  const modal = mount(ref(input))
  modal.element.children = [close, input]
  modal.open.value = true
  await settle()
  assert.equal(document.activeElement, input)
  modal.open.value = false
  await settle()
  assert.equal(document.activeElement, opener)
  modal.open.value = true
  await nextTick()
  modal.open.value = false
  await settle()
  assert.equal(document.activeElement, opener)
  assert.equal(document.body.style.overflow, '')
  modal.unmount()
})

test('a dialog mounted open acquires focus and releases its lock on unmount', async () => {
  const opener = new Element(), button = new Element()
  opener.focus()
  const modal = mount(undefined, true)
  modal.element.children = [button]
  await settle()
  assert.equal(document.activeElement, button)
  assert.equal(document.body.style.overflow, 'hidden')
  modal.unmount()
  await settle()
  assert.equal(document.activeElement, opener)
  assert.equal(document.body.style.overflow, '')
  assert.equal(listeners.size, 0)
})
