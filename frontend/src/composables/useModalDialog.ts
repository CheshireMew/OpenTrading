import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

const modalStack: symbol[] = []
let unlockedBodyOverflow = ''

export const useModalDialog = (
  open: Readonly<Ref<boolean>>,
  close: () => void,
  initialFocus?: Readonly<Ref<HTMLElement | null | undefined>>,
) => {
  const dialogRef = ref<HTMLElement | null>(null)
  const modalId = Symbol('modal')
  let previouslyFocused: HTMLElement | null = null
  let active = false

  const isTopmost = () => modalStack[modalStack.length - 1] === modalId

  const focusableElements = () => (
    Array.from(dialogRef.value?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? [])
      .filter((element) => !element.hasAttribute('disabled')
        && element.tabIndex >= 0
        && !element.closest('[inert], [aria-hidden="true"]')
        && element.getClientRects().length > 0
        && getComputedStyle(element).visibility !== 'hidden')
  )

  const handleKeydown = (event: KeyboardEvent) => {
    if (!active || !isTopmost()) return
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopImmediatePropagation()
      close()
      return
    }
    if (event.key !== 'Tab') return

    const focusable = focusableElements()
    if (!focusable.length) {
      event.preventDefault()
      dialogRef.value?.focus()
      return
    }
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (!dialogRef.value?.contains(document.activeElement)) {
      event.preventDefault()
      ;(event.shiftKey ? last : first).focus()
    } else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.value)) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const deactivate = () => {
    if (!active) return
    const restoreFocus = isTopmost()
    active = false
    window.removeEventListener('keydown', handleKeydown, true)
    const index = modalStack.indexOf(modalId)
    if (index >= 0) modalStack.splice(index, 1)
    if (!modalStack.length) document.body.style.overflow = unlockedBodyOverflow
    const returnTarget = previouslyFocused
    const remainingTop = modalStack[modalStack.length - 1]
    // Vue must first remove the background's inert attribute. Focusing while
    // it is still inert silently sends keyboard users back to the body.
    if (restoreFocus) void nextTick(() => {
      if (!active && remainingTop === modalStack[modalStack.length - 1] && returnTarget?.isConnected) {
        returnTarget.focus({ preventScroll: true })
      }
    })
    previouslyFocused = null
  }

  watch(open, async (isOpen) => {
    if (!isOpen) {
      deactivate()
      return
    }
    if (active) return
    active = true
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (!modalStack.length) unlockedBodyOverflow = document.body.style.overflow
    modalStack.push(modalId)
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeydown, true)
    await nextTick()
    if (!open.value || !active || !isTopmost()) return
    const firstFocusable = initialFocus?.value ?? focusableElements()[0]
    if (firstFocusable) firstFocusable.focus()
    else dialogRef.value?.focus()
  }, { immediate: true })

  onBeforeUnmount(() => {
    deactivate()
  })

  return { dialogRef }
}
