import { computed, onBeforeUnmount, ref, shallowRef, type Ref } from 'vue'

export function useSignalResource<T>() {
  const data = shallowRef<T | null>(null) as Ref<T | null>
  const active = shallowRef<AbortController>()
  const error = ref('')
  const loading = computed(() => !!active.value)

  function reset() {
    active.value?.abort()
    active.value = undefined
    data.value = null
    error.value = ''
  }

  async function load(task: (signal: AbortSignal) => Promise<T>) {
    active.value?.abort()
    const controller = new AbortController()
    active.value = controller
    error.value = ''
    try {
      const result = await task(controller.signal)
      if (active.value === controller) data.value = result
    } catch (cause) {
      if (active.value === controller) error.value = cause instanceof Error ? cause.message : String(cause)
    } finally {
      if (active.value === controller) active.value = undefined
    }
  }

  onBeforeUnmount(reset)
  return { data, error, loading, load, reset }
}
