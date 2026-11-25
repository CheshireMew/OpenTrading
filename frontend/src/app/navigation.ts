import { MACRO_SECTIONS, preferredMacroSection } from '@/modules/market/macroSections'
import { PUBLIC_SITE } from './publicSite'

export const APP_ROUTE_DEFINITIONS = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/ChartWorkspace.vue'),
    meta: { titleKey: 'nav.realtime' },
    nav: {
      section: 'primary',
      labelKey: 'nav.realtime',
      icon: 'ChartBarSquareIcon',
    },
  },
  {
    path: '/indicators/asset-observation',
    name: 'AssetObservation',
    component: () => import('@/views/indicators/AssetObservation.vue'),
    meta: { titleKey: 'observation.title' },
    nav: { section: 'primary', labelKey: 'observation.title', icon: 'PresentationChartLineIcon' },
  },
  {
    path: '/indicators/macro-signals',
    name: 'MacroSignals',
    component: () => import('@/views/indicators/MacroSignals.vue'),
    meta: { titleKey: 'nav.macroSignals' },
    nav: { section: 'indicators', labelKey: 'nav.macroSignals', icon: 'PresentationChartLineIcon' },
    children: [
      { path: '', redirect: () => ({ name: preferredMacroSection().name }) },
      ...MACRO_SECTIONS.map(section => ({ path: section.id, name: section.name, component: section.component, meta: { titleKey: section.label } })),
    ],
  },
  {
    path: '/indicators/market-signals',
    name: 'IndicatorsMarketSignals',
    redirect: { name: 'MacroBitcoin' },
  },
  {
    path: '/indicators/binance-market',
    name: 'BinanceMarket',
    component: () => import('@/views/indicators/BinanceMarket.vue'),
    meta: { titleKey: 'nav.binanceMarket' },
    nav: { section: 'indicators', labelKey: 'nav.binanceMarket', icon: 'ChartBarSquareIcon' },
  },
  {
    path: '/indicators/web3-rank',
    name: 'Web3MarketRank',
    component: () => import('@/views/indicators/Web3MarketRank.vue'),
    meta: { titleKey: 'nav.web3Rank' },
    nav: { section: 'indicators', labelKey: 'nav.web3Rank', icon: 'CubeTransparentIcon' },
  },
  {
    path: '/indicators/equities',
    name: 'EquityMarket',
    component: () => import('@/views/indicators/EquityMarket.vue'),
    meta: { titleKey: 'nav.equities' },
    nav: { section: 'indicators', labelKey: 'nav.equities', icon: 'ChartBarSquareIcon' },
  },
  {
    path: '/indicators/market-data',
    name: 'SignalLab',
    redirect: { name: 'MacroDollarLiquidity' },
  },
  {
    path: '/research',
    name: 'ResearchWorkbench',
    component: () => import('@/views/research/ResearchWorkbench.vue'),
    meta: { titleKey: 'nav.research' },
    nav: { section: 'research', labelKey: 'nav.research', icon: 'BookmarkSquareIcon' },
  },
  {
    path: '/research/signals',
    name: 'TradeSignalReview',
    component: () => import('@/views/research/TradeSignalReview.vue'),
    meta: { titleKey: 'nav.signalReview' },
    nav: { section: 'research', labelKey: 'nav.signalReview', icon: 'PresentationChartLineIcon' },
  },
  {
    path: '/research/screeners',
    name: 'MarketScreeners',
    component: () => import('@/views/research/MarketScreeners.vue'),
    meta: { titleKey: 'nav.screeners' },
    nav: { section: 'research', labelKey: 'nav.screeners', icon: 'FunnelIcon' },
  },
  {
    path: '/research/assets/:symbol(.*)',
    name: 'AssetResearch',
    component: () => import('@/views/research/AssetResearch.vue'),
    meta: { titleKey: 'nav.tokenResearch' },
  },
  {
    path: '/tools/compare',
    name: 'Compare',
    component: () => import('@/views/tools/Compare.vue'),
    meta: { titleKey: 'nav.compare' },
    nav: { section: 'tools', labelKey: 'nav.compare', icon: 'ScaleIcon' },
  },
  {
    path: '/tools/dca',
    name: 'DCA',
    component: () => import('@/views/tools/DCA.vue'),
    meta: { titleKey: 'nav.dca' },
    nav: { section: 'tools', labelKey: 'nav.dca', icon: 'BanknotesIcon' },
  },
  {
    path: '/tools/halving',
    name: 'Halving',
    component: () => import('@/views/tools/Halving.vue'),
    meta: { titleKey: 'nav.halving' },
    nav: { section: 'tools', labelKey: 'nav.halving', icon: 'ClockIcon' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/settings/Settings.vue'),
    meta: { titleKey: 'nav.settings' },
    nav: { section: 'system', labelKey: 'nav.settings', icon: 'CogIcon' },
  },
  {
    path: '/referrals',
    name: 'ReferralLinks',
    component: () => import('@/views/ReferralLinks.vue'),
    meta: { titleKey: 'referrals.title' },
    nav: { section: 'system', labelKey: 'referrals.title', icon: 'LinkIcon' },
  },
  {
    path: '/system/data-health',
    name: 'DataHealth',
    component: () => import('@/views/system/DataHealth.vue'),
    meta: { titleKey: 'nav.dataHealth' },
    nav: { section: 'system', labelKey: 'nav.dataHealth', icon: 'CircleStackIcon' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: { titleKey: 'pages.notFound' },
  },
] as const

export const APP_NAV_SECTIONS = [
  { key: 'primary', titleKey: null },
  { key: 'indicators', titleKey: 'nav.indicators' },
  { key: 'research', titleKey: 'nav.researchSection' },
  { key: 'tools', titleKey: 'nav.tools' },
  { key: 'system', titleKey: 'nav.system' },
] as const

const hasNav = (
  route: (typeof APP_ROUTE_DEFINITIONS)[number],
): route is Extract<(typeof APP_ROUTE_DEFINITIONS)[number], { nav: object }> => (
  'nav' in route
)

// Keep saved research pages and direct URLs available while their menu is hidden.
export const APP_NAV_ITEMS = APP_ROUTE_DEFINITIONS.filter(hasNav)
  .filter((route) => route.nav.section !== 'research')
  .filter((route) => !PUBLIC_SITE || route.name !== 'DataHealth')
// Reserve a browser-side instance for every page, including local-only pages.
// Nested macro tabs have their own cache inside MacroSignals.
export const APP_PAGE_CACHE_LIMIT = APP_ROUTE_DEFINITIONS.filter(route => 'component' in route).length

export type AppNavItem = (typeof APP_NAV_ITEMS)[number]
export type AppNavSectionKey = (typeof APP_NAV_SECTIONS)[number]['key']
export type AppNavIconName = AppNavItem['nav']['icon']
