<template>
  <div class="app-shell flex h-screen flex-col overflow-hidden transition-colors duration-300 md:flex-row">
    <a href="#main-content" class="app-skip-link">{{ t('app.skipToContent') }}</a>

    <header class="app-mobile-header flex h-14 flex-shrink-0 items-center justify-between border-b px-4 md:hidden">
      <span class="app-brand text-lg font-semibold tracking-tight">Heimdall</span>
      <button type="button" class="app-icon-button inline-flex" :aria-label="t('app.openMenu')" :aria-expanded="sidebarOpen" @click="sidebarOpen = true">
        <Bars3Icon class="h-6 w-6" />
      </button>
    </header>

    <button
      v-if="sidebarOpen"
      type="button"
      class="fixed inset-0 z-40 bg-slate-950/45 md:hidden"
      :aria-label="t('app.closeMenu')"
      @click="closeSidebar"
    />

    <aside
      ref="sidebarRef"
      class="app-sidebar fixed inset-y-0 left-0 z-50 w-72 flex-shrink-0 overflow-y-auto transition-transform duration-200 md:static md:z-auto md:w-60 md:translate-x-0"
      :class="sidebarOpen ? 'translate-x-0' : '-translate-x-full'"
      :inert="!desktopNavigation && !sidebarOpen"
      :aria-hidden="!desktopNavigation && !sidebarOpen ? 'true' : undefined"
      :role="navigationModalOpen ? 'dialog' : undefined"
      :aria-modal="navigationModalOpen ? 'true' : undefined"
      :aria-label="navigationModalOpen ? t('app.primaryNavigation') : undefined"
      tabindex="-1"
    >
      <div class="app-sidebar-header flex items-start justify-between p-5">
        <div>
          <h1 class="app-brand text-xl font-semibold tracking-tight">Heimdall</h1>
          <p class="app-sidebar-subtitle mt-1 text-xs">{{ t('app.subtitle') }}</p>
        </div>
        <button type="button" class="app-icon-button inline-flex md:hidden" :aria-label="t('app.closeMenu')" @click="closeSidebar">
          <XMarkIcon class="h-5 w-5" />
        </button>
      </div>

      <nav class="mt-4 space-y-1 px-3" :aria-label="t('app.primaryNavigation')">
        <template v-for="section in navSections" :key="section.key">
          <div v-if="section.titleKey" class="app-nav-section mt-4 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em]">
            {{ $t(section.titleKey) }}
          </div>

          <router-link
            v-for="item in section.items"
            :key="item.path"
            :to="item.path"
            class="app-nav-link flex items-center px-3 py-2 text-sm transition"
            active-class="app-nav-link--active"
            @click="closeSidebar"
          >
            <component :is="iconMap[item.nav.icon]" class="mr-2.5 h-5 w-5" />
            {{ $t(item.nav.labelKey) }}
          </router-link>
        </template>

        <div class="app-sidebar-controls mt-6 space-y-2 px-3 pt-4">
          <button
             @click="toggleTheme"
             class="app-sidebar-button flex w-full items-center justify-between px-3 py-2 text-sm transition"
          >
             <span class="flex items-center">
                 <MoonIcon v-if="theme === 'dark'" class="mr-2 h-5 w-5 text-yellow-500" />
                 <SunIcon v-else class="mr-2 h-5 w-5 text-[#0f6b4f]" />
                 {{ theme === 'dark' ? $t('theme.dark') : $t('theme.light') }}
             </span>
          </button>
          <button
             @click="toggleLocale"
             class="app-sidebar-button flex w-full items-center justify-center px-3 py-2 text-sm font-semibold transition"
          >
             <LanguageIcon class="mr-2 h-5 w-5" />
             {{ $t('lang.switch') }}
          </button>
        </div>
      </nav>
    </aside>

    <main ref="mainContentRef" id="main-content" class="app-main min-h-0 min-w-0 flex-1 overflow-auto transition-colors duration-300" tabindex="-1">
      <div v-if="bootstrapError" role="alert" class="m-4 flex items-center justify-between gap-4 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-200">
        <span>{{ t('app.bootstrapLoadFailed') }}</span>
        <button type="button" class="font-semibold underline disabled:opacity-60" :disabled="bootstrapLoading" @click="loadBootstrapResources">
          {{ t('app.retry') }}
        </button>
      </div>
      <router-view v-slot="{ Component }">
        <keep-alive :include="keepAliveRoutes">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, watchEffect, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import {
  ChartBarSquareIcon,
  ScaleIcon,
  BanknotesIcon,
  ArrowsRightLeftIcon,
  CogIcon,
  ClockIcon,
  MoonIcon,
  SunIcon,
  CubeTransparentIcon,
  LanguageIcon,
  Bars3Icon,
  XMarkIcon,
  BookmarkSquareIcon,
  PresentationChartLineIcon,
  FunnelIcon,
  DocumentTextIcon,
  CircleStackIcon,
} from '@heroicons/vue/24/outline'
import {
  APP_KEEP_ALIVE_ROUTE_NAMES,
  APP_NAV_ITEMS,
  APP_NAV_SECTIONS,
  type AppNavIconName,
} from '@/app/navigation'
import { useTheme } from '@/composables/useTheme'
import { useMoney } from '@/composables/useMoney'
import { useSymbolCatalog } from '@/modules/market'
import { setAppLocale, toggleAppLocale } from '@/i18n/config'
import { useModalDialog } from '@/composables/useModalDialog'
import { useDesktopAlertNotifications } from '@/modules/research/useDesktopAlertNotifications'

const { locale, t } = useI18n()
const route = useRoute()
const sidebarOpen = ref(false)
const mainContentRef = ref<HTMLElement | null>(null)
const bootstrapError = ref(false)
const bootstrapLoading = ref(false)
const desktopNavigation = ref(false)
const navigationModalOpen = computed(() => sidebarOpen.value && !desktopNavigation.value)
const { theme, toggleTheme } = useTheme()
const { loadCurrencyRates } = useMoney()
const { loadSymbols } = useSymbolCatalog()
useDesktopAlertNotifications()
const keepAliveRoutes = APP_KEEP_ALIVE_ROUTE_NAMES
const iconMap: Record<AppNavIconName, Component> = {
  ChartBarSquareIcon,
  ScaleIcon,
  BanknotesIcon,
  ArrowsRightLeftIcon,
  CogIcon,
  ClockIcon,
  CubeTransparentIcon,
  BookmarkSquareIcon,
  PresentationChartLineIcon,
  FunnelIcon,
  DocumentTextIcon,
  CircleStackIcon,
}
const navSections = APP_NAV_SECTIONS.map((section) => ({
  ...section,
  items: APP_NAV_ITEMS.filter((item) => item.nav.section === section.key),
})).filter((section) => section.items.length > 0)

const closeSidebar = () => {
  sidebarOpen.value = false
}
const { dialogRef: sidebarRef } = useModalDialog(navigationModalOpen, closeSidebar)
let desktopMediaQuery: MediaQueryList | null = null
const syncDesktopNavigation = (event: MediaQueryList | MediaQueryListEvent) => {
  desktopNavigation.value = event.matches
  if (event.matches) closeSidebar()
}

const toggleLocale = () => {
  setAppLocale(locale, toggleAppLocale(locale.value))
}

const loadBootstrapResources = async () => {
  if (bootstrapLoading.value) return
  bootstrapLoading.value = true
  bootstrapError.value = false
  try {
    const [symbolsResult, ratesResult] = await Promise.allSettled([
      loadSymbols(),
      loadCurrencyRates(),
    ])
    bootstrapError.value = (
      symbolsResult.status === 'rejected'
      || (ratesResult.status === 'fulfilled' && ratesResult.value === false)
      || ratesResult.status === 'rejected'
    )
  } finally {
    bootstrapLoading.value = false
  }
}

watch(() => route.fullPath, closeSidebar)
watch(() => route.path, async (_next, previous) => {
  if (!previous) return
  await nextTick()
  mainContentRef.value?.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  mainContentRef.value?.focus({ preventScroll: true })
})

watchEffect(() => {
  document.documentElement.lang = locale.value
  const titleKey = typeof route.meta.titleKey === 'string' ? route.meta.titleKey : 'app.title'
  const pageTitle = t(titleKey)
  const appTitle = t('app.title')
  document.title = pageTitle === appTitle ? appTitle : `${pageTitle} · ${appTitle}`
})

onMounted(() => {
  desktopMediaQuery = window.matchMedia('(min-width: 768px)')
  syncDesktopNavigation(desktopMediaQuery)
  desktopMediaQuery.addEventListener('change', syncDesktopNavigation)
  void loadBootstrapResources()
})

onBeforeUnmount(() => {
  desktopMediaQuery?.removeEventListener('change', syncDesktopNavigation)
})
</script>

<style>
.app-shell {
  --app-shell-bg: #f7f4ed;
  --app-shell-text: #1c1917;
  --app-sidebar-bg: #fbfaf7;
  --app-sidebar-border: #e4ded3;
  --app-brand: #10261f;
  --app-muted: #78716c;
  --app-section: #78716c;
  --app-nav: #57534e;
  --app-nav-hover-bg: #f1eee7;
  --app-nav-hover: #10261f;
  --app-nav-active-border: #0f6b4f;
  --app-nav-active-bg: #edf3ee;
  --app-nav-active: #0f4f3c;
  --app-button-bg: #ffffff;
  --app-button-border: #e4ded3;
  --app-button-hover-bg: #f4f1ea;
  --app-button-hover-border: #cfc7ba;
  --app-main-bg: #f7f4ed;
  background: var(--app-shell-bg);
  color: var(--app-shell-text);
}

html.dark .app-shell {
  --app-shell-bg: #111827;
  --app-shell-text: #f9fafb;
  --app-sidebar-bg: #111827;
  --app-sidebar-border: #334155;
  --app-brand: #f9fafb;
  --app-muted: #94a3b8;
  --app-section: #64748b;
  --app-nav: #cbd5e1;
  --app-nav-hover-bg: #1e293b;
  --app-nav-hover: #f8fafc;
  --app-nav-active-border: #34d399;
  --app-nav-active-bg: rgba(6, 78, 59, 0.35);
  --app-nav-active: #a7f3d0;
  --app-button-bg: #0f172a;
  --app-button-border: #334155;
  --app-button-hover-bg: #1e293b;
  --app-button-hover-border: #475569;
  --app-main-bg: #111827;
}

.app-sidebar {
  border-right: 1px solid var(--app-sidebar-border);
  background: var(--app-sidebar-bg);
}

.app-mobile-header {
  border-color: var(--app-sidebar-border);
  background: var(--app-sidebar-bg);
}

.app-icon-button {
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  padding: 0.5rem;
  color: var(--app-nav);
}

.app-icon-button:hover {
  background: var(--app-nav-hover-bg);
  color: var(--app-nav-hover);
}

.app-skip-link {
  position: fixed;
  top: 0.5rem;
  left: 0.5rem;
  z-index: 100;
  transform: translateY(-150%);
  background: var(--app-nav-active-border);
  color: white;
  padding: 0.625rem 1rem;
  font-weight: 600;
  transition: transform 150ms ease;
}

.app-skip-link:focus {
  transform: translateY(0);
}

.app-sidebar-header {
  border-bottom: 1px solid var(--app-sidebar-border);
}

.app-brand {
  color: var(--app-brand);
  font-family: Georgia, "Times New Roman", serif;
}

.app-sidebar-subtitle {
  color: var(--app-muted);
}

.app-nav-section {
  color: var(--app-section);
}

.app-nav-link {
  border-left: 2px solid transparent;
  color: var(--app-nav);
}

.app-nav-link:hover {
  background: var(--app-nav-hover-bg);
  color: var(--app-nav-hover);
}

.app-nav-link--active {
  border-left-color: var(--app-nav-active-border);
  background: var(--app-nav-active-bg);
  color: var(--app-nav-active);
  font-weight: 700;
}

.app-sidebar-controls {
  border-top: 1px solid var(--app-sidebar-border);
}

.app-sidebar-button {
  border: 1px solid var(--app-button-border);
  background: var(--app-button-bg);
  color: var(--app-nav);
}

.app-sidebar-button:hover {
  border-color: var(--app-button-hover-border);
  background: var(--app-button-hover-bg);
  color: var(--app-nav-hover);
}

.app-main {
  background: var(--app-main-bg);
  container-name: app-content;
  container-type: inline-size;
}
</style>
