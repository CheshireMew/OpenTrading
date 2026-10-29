import { ref, watch, type Ref } from 'vue'

/** Keep each page's presentation preference independent of its data and filters. */
export function usePageLayout<T extends string>(page: string, choices: readonly T[], fallback: T): Ref<T> {
  const key = `opentrading:layout:${page}`
  let initial = fallback
  try {
    const saved = localStorage.getItem(key)
    if (choices.includes(saved as T)) initial = saved as T
  } catch { /* A blocked storage area must not prevent using the page. */ }
  const layout = ref(initial) as Ref<T>
  watch(layout, (value) => {
    try { localStorage.setItem(key, value) } catch { /* Session preference still works. */ }
  })
  return layout
}
