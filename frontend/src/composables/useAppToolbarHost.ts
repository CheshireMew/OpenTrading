import { inject, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, type InjectionKey, type ShallowRef } from 'vue'

export const APP_TOOLBAR_HOST: InjectionKey<ShallowRef<HTMLElement | undefined>> = Symbol('appToolbarHost')

/** Let a page integrate the app's shared controls into its existing header. */
export function useAppToolbarHost() {
  const target = inject(APP_TOOLBAR_HOST, undefined), host = ref<HTMLElement>()
  const register = () => { if (target) target.value = host.value }
  const release = () => { if (target && target.value === host.value) target.value = undefined }
  onMounted(register); onActivated(register)
  onDeactivated(release); onBeforeUnmount(release)
  return host
}
