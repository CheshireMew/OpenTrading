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
      class="app-sidebar fixed inset-y-0 left-0 z-50 flex w-64 flex-shrink-0 flex-col overflow-hidden transition-transform duration-200 md:static md:z-auto md:translate-x-0"
      :class="sidebarOpen ? 'translate-x-0' : '-translate-x-full'"
      :inert="!desktopNavigation && !sidebarOpen"
      :aria-hidden="!desktopNavigation && !sidebarOpen ? 'true' : undefined"
      :role="navigationModalOpen ? 'dialog' : undefined"
      :aria-modal="navigationModalOpen ? 'true' : undefined"
      :aria-label="navigationModalOpen ? t('app.primaryNavigation') : undefined"
      tabindex="-1"
    >
      <div class="app-sidebar-header flex items-start justify-between">
        <div>
          <span class="app-brand">OpenTrading</span>
        </div>
        <button type="button" class="app-icon-button inline-flex md:hidden" :aria-label="t('app.closeMenu')" @click="closeSidebar">
          <XMarkIcon class="h-5 w-5" />
        </button>
      </div>

      <nav class="app-sidebar-navigation min-h-0 flex-1 overflow-y-auto" :aria-label="t('app.primaryNavigation')">
        <template v-for="section in navSections" :key="section.key">
          <div v-if="section.titleKey" class="app-nav-section shrink-0 font-semibold">
            {{ $t(section.titleKey) }}
          </div>

          <router-link
            v-for="item in section.items"
            :key="item.path"
            :to="item.path"
            class="app-nav-link flex shrink-0 items-center transition"
            :class="{ 'app-nav-link--perks': item.name === 'ReferralLinks' }"
            active-class="app-nav-link--active"
            :title="t(item.nav.labelKey)"
            @click="closeSidebar"
          >
            <component :is="iconMap[item.nav.icon]" class="mr-2 h-[18px] w-[18px] shrink-0" />
            <span class="truncate">{{ $t(item.nav.labelKey) }}</span>
          </router-link>
        </template>

      </nav>
      <footer class="app-sidebar-footer">
        <nav class="app-project-links" :aria-label="t('app.projectLinks')">
          <a href="https://t.me/CheshireBTC" target="_blank" rel="noopener noreferrer" :aria-label="t('app.feedback')" :title="t('app.feedback')">
            <img src="/brand-icons/telegram.svg" width="20" height="20" alt="" aria-hidden="true" />
          </a>
          <a href="https://x.com/0xCheshire" target="_blank" rel="noopener noreferrer" :aria-label="t('app.xAccount')" :title="t('app.xAccount')">
            <IconBrandXFilled aria-hidden="true" />
          </a>
          <a href="https://github.com/CheshireMew/OpenTrading" target="_blank" rel="noopener noreferrer" :aria-label="t('app.sourceCode')" :title="t('app.sourceCode')">
            <IconBrandGithubFilled aria-hidden="true" />
          </a>
        </nav>
        <AppAppearanceControls />
      </footer>
    </aside>

    <main ref="mainContentRef" id="main-content" class="app-main min-h-0 min-w-0 flex-1 overflow-auto" :inert="navigationModalOpen" tabindex="-1">
      <div v-if="bootstrapError" role="alert" class="m-4 flex items-center justify-between gap-4 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-950/30 dark:text-rose-200">
        <span>{{ t('app.bootstrapLoadFailed') }}</span>
        <button type="button" class="font-semibold underline disabled:opacity-60" :disabled="bootstrapLoading" @click="loadBootstrapResources">
          {{ t('app.retry') }}
        </button>
      </div>
      <ResearchNavigation v-if="route.path === '/research' || route.path.startsWith('/research/')" />
      <router-view v-slot="{ Component, route: viewRoute }">
        <keep-alive :max="APP_PAGE_CACHE_LIMIT">
          <component :is="Component" :key="viewRoute.matched[0]?.name ?? viewRoute.name ?? viewRoute.path" />
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
  CubeTransparentIcon,
  Bars3Icon,
  XMarkIcon,
  BookmarkSquareIcon,
  PresentationChartLineIcon,
  FunnelIcon,
  CircleStackIcon,
  GiftIcon,
} from '@heroicons/vue/24/outline'
import {
  APP_PAGE_CACHE_LIMIT,
  APP_NAV_ITEMS,
  APP_NAV_SECTIONS,
  type AppNavIconName,
} from '@/app/navigation'
import AppAppearanceControls from '@/components/AppAppearanceControls.vue'
import { IconBrandGithubFilled, IconBrandXFilled } from '@tabler/icons-vue'
import ResearchNavigation from '@/components/research/ResearchNavigation.vue'
import { useMoney } from '@/composables/useMoney'
import { useSymbolCatalog } from '@/modules/market'
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
const { loadCurrencyRates } = useMoney()
const { loadSymbols } = useSymbolCatalog()
useDesktopAlertNotifications()
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
  GiftIcon,
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
const pageScrollPositions = new Map<string, { top: number; left: number }>()
watch(() => route.path, async (next, previous) => {
  if (!previous) return
  const main = mainContentRef.value
  if (main) pageScrollPositions.set(previous, { top: main.scrollTop, left: main.scrollLeft })
  await nextTick()
  mainContentRef.value?.scrollTo({ ...(pageScrollPositions.get(next) ?? { top: 0, left: 0 }), behavior: 'auto' })
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
  --app-main-bg: var(--ui-canvas);
  background: var(--app-shell-bg);
  color: var(--app-shell-text);
}
.app-sidebar {
  border-right: 1px solid var(--app-sidebar-border);
  background: var(--app-sidebar-bg);
}

.app-sidebar-header { padding: 12px 10px; }
.app-sidebar-navigation { display: flex; flex-direction: column; gap: 2px; padding: 8px 8px 12px; }
.app-nav-link { min-height: 36px; border-radius: 3px; padding: 6px; font-size: 13px; line-height: 20px; font-weight: 500; }
.app-nav-link--active { font-weight: 600; }
.app-nav-section { margin-top: 10px; padding: 4px 6px; font-size: 11px; letter-spacing: 0.02em; }
@media(min-width:768px){.app-sidebar{width:max-content;max-width:220px}}
.app-sidebar-footer{display:flex;flex:none;flex-direction:column;align-items:center;gap:6px;padding:10px 8px max(10px,env(safe-area-inset-bottom));border-top:1px solid var(--app-sidebar-border)}
.app-project-links{display:flex;align-items:center;justify-content:center;gap:12px}
.app-project-links>a{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:4px;color:var(--app-nav)}
.app-project-links>a:hover{background:var(--app-nav-hover-bg);color:var(--app-nav-hover)}
.app-project-links>a:focus-visible{outline:2px solid var(--ui-accent);outline-offset:1px}
.app-project-links :is(svg,img){width:20px;height:20px;flex:none}
@media(pointer:coarse){.app-project-links>a{width:44px;height:44px}}

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
  font-size: 18px;
  line-height: 24px;
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

.app-nav-link--perks {
  color: var(--ui-favorite);
  background: color-mix(in srgb, var(--ui-favorite) 6%, var(--app-sidebar-bg));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ui-favorite) 22%, transparent);
}

.app-nav-link--perks:hover,
.app-nav-link--perks.app-nav-link--active {
  color: var(--ui-favorite);
  background: color-mix(in srgb, var(--ui-favorite) 12%, var(--app-sidebar-bg));
}

.app-main {
  overscroll-behavior: contain;
  background: var(--app-main-bg);
  container-name: app-content;
  container-type: inline-size;
}

.app-main:focus { outline: none; }
@media (pointer: coarse) {
  .app-nav-link { min-height: 44px; }
}
</style>
