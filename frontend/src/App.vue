<template>
  <div class="app-shell flex h-dvh flex-col overflow-hidden md:flex-row" :class="{'app-chart-mode': route.path === '/'}">
    <a href="#main-content" class="app-skip-link">{{ t('app.skipToContent') }}</a>

    <header class="app-mobile-header flex h-14 flex-shrink-0 items-center justify-between border-b px-4 md:hidden">
      <span class="app-brand text-lg font-semibold tracking-tight">OpenTrading</span>
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
      class="app-sidebar fixed inset-y-0 left-0 z-50 flex w-72 flex-shrink-0 flex-col overflow-hidden transition-transform duration-200 md:static md:z-auto md:w-[184px] md:translate-x-0"
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
          <span class="app-brand text-xl font-semibold tracking-tight">OpenTrading</span>
        </div>
        <button type="button" class="app-icon-button inline-flex md:hidden" :aria-label="t('app.closeMenu')" @click="closeSidebar">
          <XMarkIcon class="h-5 w-5" />
        </button>
      </div>

      <nav class="app-sidebar-navigation min-h-0 flex-1 space-y-1 overflow-y-auto px-3 pb-4 pt-3" :aria-label="t('app.primaryNavigation')">
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
            :title="t(item.nav.labelKey)"
            @click="closeSidebar"
          >
            <component :is="iconMap[item.nav.icon]" class="mr-2.5 h-[18px] w-[18px] shrink-0" />
            <span class="truncate">{{ $t(item.nav.labelKey) }}</span>
          </router-link>
        </template>

      </nav>
        <div class="app-sidebar-controls mx-3 mb-3 grid shrink-0 grid-cols-[1fr_auto] gap-2 pt-3">
          <button
             type="button"
             @click="toggleTheme"
             :aria-label="theme === 'dark' ? t('theme.light') : t('theme.dark')"
             class="app-sidebar-button flex w-full items-center justify-between px-3 py-2 text-sm transition"
          >
             <span class="flex items-center">
                 <SunIcon v-if="theme === 'dark'" class="mr-2 h-4 w-4" />
                 <MoonIcon v-else class="mr-2 h-4 w-4" />
                 {{ theme === 'dark' ? $t('theme.light') : $t('theme.dark') }}
             </span>
          </button>
          <button
             type="button"
             @click="toggleLocale"
             class="app-sidebar-button flex w-full items-center justify-center px-3 py-2 text-sm font-semibold transition"
          >
             <LanguageIcon class="mr-1.5 h-4 w-4" />
             {{ $t('lang.switch') }}
          </button>
        </div>
    </aside>

    <main ref="mainContentRef" id="main-content" class="app-main min-h-0 min-w-0 flex-1 overflow-auto" :inert="navigationModalOpen" tabindex="-1">
      <div v-if="bootstrapError" role="alert" class="m-4 flex items-center justify-between gap-4 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-200">
        <span>{{ t('app.bootstrapLoadFailed') }}</span>
        <button type="button" class="font-semibold underline disabled:opacity-60" :disabled="bootstrapLoading" @click="loadBootstrapResources">
          {{ t('app.retry') }}
        </button>
      </div>
      <ResearchNavigation v-if="route.path === '/research' || route.path.startsWith('/research/')" />
      <router-view v-slot="{ Component }">
        <keep-alive :include="keepAliveRoutes">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <PriceAlertNotices />
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
  CircleStackIcon,
} from '@heroicons/vue/24/outline'
import {
  APP_KEEP_ALIVE_ROUTE_NAMES,
  APP_NAV_ITEMS,
  APP_NAV_SECTIONS,
  type AppNavIconName,
} from '@/app/navigation'
import { useTheme } from '@/composables/useTheme'
import ResearchNavigation from '@/components/research/ResearchNavigation.vue'
import { useMoney } from '@/composables/useMoney'
import { useSymbolCatalog } from '@/modules/market'
import { setAppLocale, toggleAppLocale } from '@/i18n/config'
import { useModalDialog } from '@/composables/useModalDialog'
import { useDesktopAlertNotifications } from '@/modules/research/useDesktopAlertNotifications'
import PriceAlertNotices from '@/components/chartWorkspace/PriceAlertNotices.vue'

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
  CogIcon,
  ClockIcon,
  CubeTransparentIcon,
  BookmarkSquareIcon,
  PresentationChartLineIcon,
  FunnelIcon,
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
.app-chart-mode .app-main{overflow:hidden!important}

.app-shell {
  --app-shell-bg: var(--ui-canvas);
  --app-shell-text: var(--ui-text);
  --app-sidebar-bg: var(--ui-toolbar);
  --app-sidebar-border: var(--ui-border);
  --app-brand: var(--ui-title);
  --app-muted: var(--ui-muted);
  --app-section: var(--ui-muted);
  --app-nav: var(--ui-text);
  --app-nav-hover-bg: var(--ui-elevated);
  --app-nav-hover: var(--ui-title);
  --app-nav-active-border: var(--ui-accent);
  --app-nav-active-bg: color-mix(in srgb, var(--ui-accent) 10%, var(--ui-toolbar));
  --app-nav-active: var(--ui-accent);
  --app-button-bg: var(--ui-toolbar);
  --app-button-border: var(--ui-border);
  --app-button-hover-bg: var(--ui-elevated);
  --app-button-hover-border: var(--ui-borderStrong);
  --app-main-bg: var(--ui-canvas);
  background: var(--app-shell-bg);
  color: var(--app-shell-text);
}
.app-sidebar {
  border-right: 1px solid var(--app-sidebar-border);
  background: var(--app-sidebar-bg);
}

.app-sidebar-header { padding: 18px 14px; }
.app-nav-link { min-height: 40px; border-radius: 3px; padding-inline: 9px; font-size: 14px; font-weight: 500; }
.app-nav-link--active { font-weight: 600; }
.app-nav-section { margin-top: 16px; padding: 6px 9px; font-size: 11px; letter-spacing: 0.02em; }
.app-sidebar-button { min-height: 36px; border-radius: 4px; padding: 7px 6px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.app-sidebar-controls { border-top-color: var(--ui-border); }

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
  color: var(--ui-onAccent);
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
  font-family: inherit;
  font-size: 19px;
  font-weight: 750;
  letter-spacing: -0.6px;
}

.app-nav-section {
  color: var(--app-section);
}

.app-nav-link {
  color: var(--app-nav);
}

.app-nav-link:hover {
  background: var(--app-nav-hover-bg);
  color: var(--app-nav-hover);
}

.app-nav-link--active {
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
  overscroll-behavior: contain;
  background: var(--app-main-bg);
  container-name: app-content;
  container-type: inline-size;
}

.app-main:focus { outline: none; }
@media (pointer: coarse) {
  .app-nav-link, .app-sidebar-button { min-height: 44px; }
}
</style>
