import { computed, onBeforeUnmount, shallowRef, type Ref } from 'vue'
import { isRequestCanceled } from '@/api/request'
import { useRequestError } from '@/composables/useRequestError'
import i18n from '@/i18n'

export function useSignalResource<T>() {
  const data = shallowRef<T | null>(null) as Ref<T | null>
  const active = shallowRef<AbortController>()
  const { error, setError, clearError } = useRequestError(key => i18n.global.t(key))
  const loading = computed(() => !!active.value)

  function reset() {
    active.value?.abort()
    active.value = undefined
    data.value = null
    clearError()
  }

  async function load(task: (signal: AbortSignal) => Promise<T>) {
    active.value?.abort()
    const controller = new AbortController()
    active.value = controller
    clearError()
    try {
      const result = await task(controller.signal)
      if (active.value === controller) data.value = result
    } catch (cause) {
      if (active.value === controller && !isRequestCanceled(cause)) {
        setError(cause, 'signalLab.readFailed')
      }
    } finally {
      if (active.value === controller) active.value = undefined
    }
  }

  onBeforeUnmount(reset)
  return { data, error, loading, load, reset }
}
