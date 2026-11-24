import { getLocalStorage } from '@/utils/storage'

// Add future market sections here; routes and page navigation share this list.
export const MACRO_SECTIONS = [
  { id: 'bitcoin', name: 'MacroBitcoin', label: 'macroSignals.bitcoin', component: () => import('@/views/indicators/MarketSignals.vue') },
  { id: 'dollar-liquidity', name: 'MacroDollarLiquidity', label: 'nav.signalLab', component: () => import('@/views/indicators/SignalLab.vue') },
] as const
const STORAGE_KEY = 'opentrading:macro-signals:section'
const DEFAULT_SECTION = MACRO_SECTIONS[1]

export function preferredMacroSection() {
  try {
    const saved = getLocalStorage()?.getItem(STORAGE_KEY)
    return MACRO_SECTIONS.find(section => section.id === saved) ?? DEFAULT_SECTION
  } catch { return DEFAULT_SECTION }
}

export function rememberMacroSection(name: unknown) {
  const section = MACRO_SECTIONS.find(section => section.name === name)
  if (!section) return
  try { getLocalStorage()?.setItem(STORAGE_KEY, section.id) } catch { /* The active route still works without storage. */ }
}
