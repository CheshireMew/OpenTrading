export const APP_ROUTE_DEFINITIONS = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { titleKey: 'nav.realtime' },
    keepAlive: true,
    nav: {
      section: 'primary',
      labelKey: 'nav.realtime',
      icon: 'ChartBarSquareIcon',
    },
  },
  {
    path: '/indicators/market-signals',
    name: 'IndicatorsMarketSignals',
    component: () => import('@/views/indicators/MarketSignals.vue'),
    meta: { titleKey: 'nav.marketSignals' },
    nav: { section: 'indicators', labelKey: 'nav.marketSignals', icon: 'CubeTransparentIcon' },
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
    path: '/tools/portfolio-balance',
    name: 'PortfolioBalance',
    component: () => import('@/views/tools/PortfolioBalance.vue'),
    meta: { titleKey: 'nav.portfolioBalance' },
    nav: {
      section: 'tools',
      labelKey: 'nav.portfolioBalance',
      icon: 'ArrowsRightLeftIcon',
    },
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
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue'),
    meta: { titleKey: 'pages.notFound' },
  },
] as const

export const APP_NAV_SECTIONS = [
  { key: 'primary', titleKey: null },
  { key: 'indicators', titleKey: 'nav.indicators' },
  { key: 'tools', titleKey: 'nav.tools' },
  { key: 'system', titleKey: 'nav.system' },
] as const

const hasNav = (
  route: (typeof APP_ROUTE_DEFINITIONS)[number],
): route is Extract<(typeof APP_ROUTE_DEFINITIONS)[number], { nav: object }> => (
  'nav' in route
)

const hasKeepAlive = (
  route: (typeof APP_ROUTE_DEFINITIONS)[number],
): route is Extract<(typeof APP_ROUTE_DEFINITIONS)[number], { keepAlive: true }> => (
  'keepAlive' in route && route.keepAlive === true
)

export const APP_NAV_ITEMS = APP_ROUTE_DEFINITIONS.filter(hasNav)
export const APP_KEEP_ALIVE_ROUTE_NAMES = APP_ROUTE_DEFINITIONS
  .filter(hasKeepAlive)
  .map((route) => route.name)

export type AppNavItem = (typeof APP_NAV_ITEMS)[number]
export type AppNavSectionKey = (typeof APP_NAV_SECTIONS)[number]['key']
export type AppNavIconName = AppNavItem['nav']['icon']
