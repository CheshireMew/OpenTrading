import { ApiRequestError } from '@/api/request'

export async function browserJson<T>(url: string, init: RequestInit = {}, timeout = 15000, signal?: AbortSignal): Promise<T> {
  signal ??= init.signal ?? undefined
  const controller = new AbortController()
  const stop = () => controller.abort(signal?.reason)
  if (signal?.aborted) stop(); else signal?.addEventListener('abort', stop, { once: true })
  const timer = setTimeout(() => controller.abort(new Error('Market data request timed out')), timeout)
  const aborted = new Promise<never>((_resolve, reject) => {
    const fail = () => reject(controller.signal.reason ?? new DOMException('Request aborted', 'AbortError'))
    if (controller.signal.aborted) fail(); else controller.signal.addEventListener('abort', fail, { once: true })
  })
  try {
    return await Promise.race([aborted, (async () => {
      const response = await fetch(url, { ...init, signal: controller.signal })
      const payload = await response.json()
      if (!response.ok) throw new ApiRequestError(typeof payload?.detail === 'string' ? payload.detail : `Market data unavailable (${response.status})`, { status: response.status })
      return payload as T
    })()])
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', stop) }
}
