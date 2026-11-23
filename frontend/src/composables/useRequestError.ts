import { computed, shallowRef } from 'vue'
import { apiErrorMessage } from '@/api/request'

export class LocalizedRequestError extends Error {
  constructor(readonly key: string, readonly params: () => Record<string, unknown> = () => ({})) {
    super(key)
  }
}

/** Keep the cause and translation key so an existing error follows locale changes. */
export function useRequestError(t: (key: string, params?: Record<string, unknown>) => string) {
  const failure = shallowRef<{ cause: unknown; key: string } | null>(null)
  return {
    error: computed(() => {
      const current = failure.value
      if (!current) return ''
      return current.cause instanceof LocalizedRequestError
        ? t(current.cause.key, current.cause.params())
        : apiErrorMessage(current.cause, t(current.key))
    }),
    setError: (cause: unknown, key: string) => { failure.value = { cause, key } },
    clearError: () => { failure.value = null },
  }
}
