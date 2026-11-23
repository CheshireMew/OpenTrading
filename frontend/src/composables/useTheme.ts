import { ref, watchEffect, type Ref } from 'vue'
import { getLocalStorage } from '@/utils/storage'
import { DARK_PALETTE, LIGHT_PALETTE, DARK_NEUTRALS, LIGHT_NEUTRALS, hexRgb } from '@/theme/palette.mjs'

type Theme = 'light' | 'dark'

const readStoredTheme = (): Theme => {
    const storage = getLocalStorage()
    if (storage === null) return 'dark'
    const stored = storage.getItem('theme')
    return stored === 'light' ? 'light' : 'dark'
}

const theme: Ref<Theme> = ref(readStoredTheme())

watchEffect(() => {
    if (typeof window === 'undefined') return
    const root = window.document.documentElement
    root.classList.remove('light', 'dark')
    root.classList.add(theme.value)
    // Keep live theme changes and canvas colors in sync without depending on
    // Tailwind's build-time config cache (including during desktop hot reloads).
    const palette = theme.value === 'dark' ? DARK_PALETTE : LIGHT_PALETTE
    const neutrals = theme.value === 'dark' ? DARK_NEUTRALS : LIGHT_NEUTRALS
    for (const [key, value] of Object.entries(palette)) root.style.setProperty(`--ui-${key}`, value)
    for (const [shade, value] of Object.entries(neutrals)) root.style.setProperty(`--ui-neutral-${shade}`, hexRgb(value))
    getLocalStorage()?.setItem('theme', theme.value)
})

export function useTheme() {
    const toggleTheme = () => {
        theme.value = theme.value === 'dark' ? 'light' : 'dark'
    }

    return {
        theme,
        toggleTheme
    }
}
