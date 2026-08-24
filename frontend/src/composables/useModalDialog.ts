import { nextTick, onBeforeUnmount, ref, watch, type Ref } from 'vue'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export const useModalDialog = (open: Readonly<Ref<boolean>>, close: () => void) => {
  const dialogRef = ref<HTMLElement | null>(null)
  let previouslyFocused: HTMLElement | null = null
  let previousBodyOverflow = ''

  const focusableElements = () => (
    Array.from(dialogRef.value?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? [])
      .filter((element) => !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true')
  )

  const handleKeydown = (event: KeyboardEvent) => {
    if (!open.value) return
    if (event.key === 'Escape') {
      event.preventDefault()
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
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const deactivate = () => {
    window.removeEventListener('keydown', handleKeydown, true)
    document.body.style.overflow = previousBodyOverflow
    previouslyFocused?.focus()
    previouslyFocused = null
  }

  watch(open, async (isOpen) => {
    if (!isOpen) {
      deactivate()
      return
    }
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeydown, true)
    await nextTick()
    const firstFocusable = focusableElements()[0]
    if (firstFocusable) firstFocusable.focus()
    else dialogRef.value?.focus()
  })

  onBeforeUnmount(() => {
    if (open.value) deactivate()
  })

  return { dialogRef }
}
