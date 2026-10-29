<template>
  <div class="app-page equities-page">
    <div class="eq-page-inner">
      <header class="eq-page-header">
        <div class="eq-title-block">
          <h1>{{ t('equities.title') }}</h1>
          <p v-if="catalog"><strong>{{ catalog.items.length.toLocaleString() }}</strong> {{ t('equities.securities') }}<span class="eq-meta-separator">·</span>{{ t('equities.updated', { time: formatDateTime(catalog.updated_at) }) }}</p>
        </div>
        <div class="eq-header-actions">
          <div class="eq-layout-picker" role="group" :aria-label="t('equities.layout')">
            <button v-for="option in layouts" :key="option.id" type="button" :aria-pressed="layout === option.id" :title="option.description" @click="layout = option.id">
              <component :is="option.icon" aria-hidden="true" /><span>{{ option.label }}</span>
            </button>
          </div>
          <button type="button" class="eq-refresh" :aria-label="loading ? t('equities.refreshing') : t('equities.refresh')" :disabled="loading" @click="load(true)">
            <ArrowPathIcon aria-hidden="true" :class="{ 'animate-spin': loading }" /><span>{{ loading ? t('equities.refreshing') : t('equities.refresh') }}</span>
          </button>
        </div>
      </header>

      <div class="eq-search-row">
        <div class="eq-search">
          <MagnifyingGlassIcon aria-hidden="true" />
          <label class="sr-only" for="eq-search-input">{{ t('equities.search') }}</label>
          <input id="eq-search-input" ref="searchInput" v-model="search" type="search" :placeholder="t('equities.searchPlaceholder')" />
          <button v-if="search" type="button" :aria-label="t('equities.clearSearch')" @click="search = ''; searchInput?.focus()"><XMarkIcon aria-hidden="true" /></button>
          <kbd v-else aria-hidden="true">/</kbd>
        </div>
        <button v-if="layout === 'directory'" type="button" class="eq-mobile-filter-toggle eq-control" :aria-expanded="filtersOpen" aria-controls="eq-filter-sidebar" @click="filtersOpen = !filtersOpen">
          <AdjustmentsHorizontalIcon aria-hidden="true" />{{ t('ui.filters') }}<span v-if="filterCount">{{ filterCount }}</span>
        </button>
      </div>

      <div v-if="error && catalog" role="alert" class="eq-notice eq-notice--error"><span>{{ error }}</span><button type="button" :disabled="loading" @click="load()">{{ t('common.retry') }}</button></div>
      <div v-if="unavailableLabels" role="status" class="eq-notice eq-notice--warning">{{ t('equities.partial') }} {{ unavailableLabels }}</div>

      <EquityCatalogFilters v-if="layout !== 'directory'" id="eq-bar" variant="bar" v-model:platform="platform" v-model:asset-type="assetType" v-model:trading-type="tradingType" v-model:shared-only="sharedOnly" :spot-count="spotCount" :perpetual-count="perpetualCount" />

      <div class="eq-workbench" :class="`eq-workbench--${layout}`">
        <aside v-if="layout === 'directory'" id="eq-filter-sidebar" class="eq-facets" :class="{ 'is-open': filtersOpen }" :aria-label="t('ui.filters')">
          <EquityCatalogFilters id="eq-sidebar" variant="sidebar" v-model:platform="platform" v-model:asset-type="assetType" v-model:trading-type="tradingType" v-model:shared-only="sharedOnly" :spot-count="spotCount" :perpetual-count="perpetualCount" />
          <button v-if="hasFilters" type="button" class="eq-text-button eq-sidebar-reset" @click="resetFilters">{{ t('equities.reset') }}</button>
        </aside>

        <section class="eq-results" :aria-label="t('equities.security')" :aria-busy="loading">
          <div class="eq-results-toolbar">
            <p aria-live="polite">{{ t('equities.results', { count: filtered.length.toLocaleString(), total: catalog?.items.length.toLocaleString() ?? '—' }) }}</p>
            <div class="eq-result-actions">
              <button v-if="hasFilters" type="button" class="eq-text-button" @click="resetFilters">{{ t('equities.reset') }}</button>
              <label class="eq-sort"><span class="sr-only">{{ t('equities.sort') }}</span><select v-model="sort" :aria-label="t('equities.sort')"><option value="coverage">{{ t('equities.sortCoverage') }}</option><option value="ticker">{{ t('equities.sortTicker') }}</option><option value="name">{{ t('equities.sortName') }}</option></select></label>
            </div>
          </div>

          <AppLoadingState v-if="loading && !catalog" :label="t('equities.loading')" :rows="7" />
          <div v-else-if="error && !catalog" role="alert" class="eq-load-error"><p>{{ error }}</p><button type="button" class="eq-control" @click="load()">{{ t('common.retry') }}</button></div>
          <AppEmptyState v-else-if="!paged.length" :title="t('equities.empty')" :description="t('equities.emptyHint')" :icon="MagnifyingGlassIcon"><button v-if="hasFilters" type="button" class="eq-control" @click="resetFilters">{{ t('equities.reset') }}</button></AppEmptyState>

          <div v-else-if="layout === 'split'" class="eq-split">
            <div class="eq-security-list" :aria-label="t('equities.security')">
              <button v-for="item in paged" :key="item.ticker" type="button" class="eq-list-item" :class="{ 'is-selected': selectedTicker === item.ticker }" :aria-pressed="selectedTicker === item.ticker" aria-controls="eq-selected-products" @click="selectStock(item)">
                <EquityCompanyLogo :src="item.logo_url" :ticker="item.ticker" class="eq-logo" />
                <span class="eq-identity"><strong>{{ item.ticker }}<span v-if="item.market !== 'US'" class="eq-market">{{ item.market }}</span></strong><span :title="item.name">{{ item.name_zh || item.name }}</span></span>
                <span class="eq-list-count">{{ item.offerings.length }}</span><ChevronRightIcon class="eq-row-chevron" aria-hidden="true" />
              </button>
            </div>
            <section v-if="selectedStock" id="eq-selected-products" class="eq-selection" :aria-label="`${selectedStock.ticker} ${t('equities.products')}`">
              <header class="eq-selection-header">
                <EquityCompanyLogo :src="selectedStock.logo_url" :ticker="selectedStock.ticker" />
                <div class="eq-selected-identity"><h2>{{ selectedStock.ticker }}<span>{{ selectedStock.name_zh }}</span></h2><p>{{ selectedStock.name }}</p></div>
                <span class="eq-selected-meta">{{ assetName(selectedStock.asset_type) }} · {{ selectedStock.market }}<br>{{ t('equities.productCount', { count: selectedStock.offerings.length }) }}</span>
              </header>
              <EquityProductDetails :item="selectedStock" :sources="catalog?.sources ?? []" arrangement="stack" />
            </section>
          </div>

          <table v-else class="eq-catalog-table" :class="{ 'eq-matrix-table': layout === 'matrix', 'eq-directory-table': layout === 'directory' }">
            <colgroup v-if="layout === 'matrix'"><col class="eq-security-col" /><col v-for="p in platforms" :key="p" /></colgroup>
            <colgroup v-else><col class="eq-security-col" /><col class="eq-type-col" /><col class="eq-platform-col" /><col class="eq-trading-col" /><col class="eq-product-col" /></colgroup>
            <thead><tr>
              <th scope="col">{{ t('equities.security') }}</th>
              <template v-if="layout === 'matrix'"><th v-for="p in platforms" :key="p" scope="col" :class="{ 'is-filtered': platform === p }">{{ platformName(p) }}</th></template>
              <template v-else><th scope="col">{{ t('equities.assetType') }}</th><th scope="col">{{ t('equities.supportedPlatforms') }}</th><th scope="col">{{ t('equities.tradingType') }}</th><th scope="col" class="eq-align-end">{{ t('equities.products') }}</th></template>
            </tr></thead>
            <tbody>
              <template v-for="item in paged" :key="item.ticker">
                <tr class="eq-stock-row" :class="{ 'is-selected': selectedTicker === item.ticker && detailOpen }">
                  <td class="eq-security-cell">
                    <button type="button" class="eq-stock-trigger" :aria-label="t('equities.expand', { ticker: item.ticker })" :aria-expanded="selectedTicker === item.ticker && detailOpen" :aria-controls="`eq-products-${item.ticker}`" @click="toggleStock(item)">
                      <EquityCompanyLogo :src="item.logo_url" :ticker="item.ticker" class="eq-logo" />
                      <span class="eq-identity"><strong>{{ item.ticker }}<span v-if="item.market !== 'US'" class="eq-market">{{ item.market }}</span></strong><span :title="item.name">{{ item.name_zh || item.name }}</span></span>
                      <ChevronDownIcon class="eq-row-chevron" :class="{ 'is-open': selectedTicker === item.ticker && detailOpen }" aria-hidden="true" />
                    </button>
                  </td>
                  <template v-if="layout === 'matrix'">
                    <td v-for="p in platforms" :key="p" class="eq-platform-cell" :data-label="platformName(p)">
                      <button type="button" class="eq-platform-coverage" :aria-label="t('equities.expand', { ticker: `${item.ticker} · ${platformName(p)}` })" :aria-expanded="selectedTicker === item.ticker && detailOpen" :aria-controls="`eq-products-${item.ticker}`" @click="toggleStock(item)">
                        <template v-if="platformOfferings(item, p).length">
                          <span v-for="kind in ['spot', 'perpetual']" v-show="offeringCount(item, p, kind)" :key="kind">{{ t(`equities.${kind}`) }}<strong>{{ offeringCount(item, p, kind) }}</strong></span>
                        </template>
                        <span v-else class="eq-not-listed" :title="t('equities.notListed')">—</span>
                      </button>
                    </td>
                  </template>
                  <template v-else>
                    <td :data-label="t('equities.assetType')">{{ assetName(item.asset_type) }}</td>
                    <td :data-label="t('equities.supportedPlatforms')"><span class="eq-platform-names">{{ item.platforms.map(platformName).join(' / ') }}</span></td>
                    <td :data-label="t('equities.tradingType')">{{ item.trading_types.map(kind => t(`equities.${kind}`)).join(' / ') }}</td>
                    <td class="eq-align-end" :data-label="t('equities.products')"><button type="button" class="eq-text-button" :aria-label="t('equities.expand', { ticker: item.ticker })" :aria-expanded="selectedTicker === item.ticker && detailOpen" @click="toggleStock(item)">{{ item.offerings.length }}</button></td>
                  </template>
                </tr>
                <tr v-if="selectedTicker === item.ticker && detailOpen" :id="`eq-products-${item.ticker}`" class="eq-expanded-row"><td :colspan="layout === 'matrix' ? 4 : 5">
                  <div :class="{ 'eq-matrix-expansion': layout === 'matrix' }">
                    <div v-if="layout === 'matrix'" class="eq-expansion-label"><strong>{{ item.ticker }}</strong><p>{{ t('equities.productCount', { count: item.offerings.length }) }}</p></div>
                    <EquityProductDetails :item="item" :sources="catalog?.sources ?? []" :arrangement="layout === 'matrix' ? 'columns' : 'rows'" />
                  </div>
                </td></tr>
              </template>
            </tbody>
          </table>

          <footer v-if="catalog && filtered.length" class="eq-pagination">
            <label>{{ t('equities.pageSize') }}<select v-model.number="pageSize" class="eq-control" :aria-label="t('equities.pageSize')"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select></label>
            <div><button type="button" class="eq-control eq-page-arrow" :aria-label="t('equities.previous')" :disabled="page <= 1" @click="page--"><ChevronLeftIcon aria-hidden="true" /></button><span>{{ page }} / {{ pageCount }}</span><button type="button" class="eq-control eq-page-arrow" :aria-label="t('equities.next')" :disabled="page >= pageCount" @click="page++"><ChevronRightIcon aria-hidden="true" /></button></div>
          </footer>
        </section>
      </div>

      <details v-if="catalog" class="eq-source-details">
        <summary><CircleStackIcon aria-hidden="true" /><span>{{ t('equities.sources') }}</span><span class="eq-source-count">{{ catalog.sources.filter(source => source.status === 'ok').length }} / {{ catalog.sources.length }}</span><ChevronDownIcon class="eq-source-chevron" aria-hidden="true" /></summary>
        <div class="eq-source-body">
          <p>{{ t('equities.scope') }}</p>
          <p>{{ t('equities.notListed') }}</p>
          <ul><li v-for="source in catalog.sources" :key="source.id"><a :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.label }}<ArrowUpRightIcon aria-hidden="true" /></a><span>{{ source.count.toLocaleString() }} · {{ source.updated_at ? formatDateTime(source.updated_at) : '—' }}</span><span :class="{ 'eq-source-warning': source.status !== 'ok' }">{{ source.error === 'catalog_not_verified' ? t('equities.sourceNotVerified') : t(`equities.sourceStatus.${source.status}`) }}</span></li></ul>
          <p>{{ t('equities.availability') }}</p>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AdjustmentsHorizontalIcon, ArrowPathIcon, ArrowUpRightIcon, ChevronDownIcon, ChevronLeftIcon, ChevronRightIcon, CircleStackIcon, MagnifyingGlassIcon, TableCellsIcon, ViewColumnsIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { apiErrorMessage } from '@/api/request'
import { useDateTime } from '@/composables/useDateTime'
import AppEmptyState from '@/components/AppEmptyState.vue'
import AppLoadingState from '@/components/AppLoadingState.vue'
import EquityCompanyLogo from '@/components/market/EquityCompanyLogo.vue'
import EquityCatalogFilters from '@/components/market/EquityCatalogFilters.vue'
import EquityProductDetails from '@/components/market/EquityProductDetails.vue'
import { equityCatalogApi } from '@/modules/market/equityCatalog'
import type { EquityCatalogItemResponse, EquityCatalogResponse } from '@/modules/market/contracts'
import './equityMarket.css'

type CatalogLayout = 'split' | 'matrix' | 'directory'
const layoutStorageKey = 'opentrading:equity-catalog-layout'
function readLayout(): CatalogLayout {
  try { const value = localStorage.getItem(layoutStorageKey); if (value === 'matrix' || value === 'directory') return value } catch {}
  return 'split'
}
const { t } = useI18n()
const { formatDateTime } = useDateTime()
const layout = ref<CatalogLayout>(readLayout())
const layouts = computed(() => [
  { id: 'split' as const, label: t('equities.layoutSplit'), description: t('equities.layoutSplitHint'), icon: ViewColumnsIcon },
  { id: 'matrix' as const, label: t('equities.layoutMatrix'), description: t('equities.layoutMatrixHint'), icon: TableCellsIcon },
  { id: 'directory' as const, label: t('equities.layoutDirectory'), description: t('equities.layoutDirectoryHint'), icon: AdjustmentsHorizontalIcon },
])
watch(layout, value => { try { localStorage.setItem(layoutStorageKey, value) } catch {} })
const catalog = ref<EquityCatalogResponse | null>(null)
const loading = ref(false)
const error = ref('')
const search = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
const filtersOpen = ref(false)
const platform = ref('all')
const tradingType = ref('all')
const assetType = ref('all')
const sharedOnly = ref(false)
const sort = ref('coverage')
const page = ref(1)
const pageSize = ref(50)
const selectedTicker = ref('AAPL')
const detailOpen = ref(true)
const platforms = ['binance', 'okx', 'bitget'] as const
let active = true

const platformName = (value: string) => value === 'binance' ? t('equities.binance') : value === 'okx' ? 'OKX' : 'Bitget'
const assetName = (kind: string) => t(`equities.${kind}`)
const platformOfferings = (item: EquityCatalogItemResponse, value: string) => item.offerings.filter(offering => offering.platform === value)
const offeringCount = (item: EquityCatalogItemResponse, value: string, kind: string) => item.offerings.filter(offering => offering.platform === value && offering.trading_type === kind).length
const spotCount = computed(() => catalog.value ? catalog.value.items.filter(item => item.trading_types.includes('spot')).length : null)
const perpetualCount = computed(() => catalog.value ? catalog.value.items.filter(item => item.trading_types.includes('perpetual')).length : null)
const unavailableLabels = computed(() => catalog.value?.sources.filter(source => source.status !== 'ok' && source.error !== 'catalog_not_verified').map(source => source.label).join(' / '))
const hasFilters = computed(() => Boolean(search.value || platform.value !== 'all' || tradingType.value !== 'all' || assetType.value !== 'all' || sharedOnly.value))
const filterCount = computed(() => [platform.value !== 'all', tradingType.value !== 'all', assetType.value !== 'all', sharedOnly.value].filter(Boolean).length)
const filtered = computed(() => {
  const query = search.value.trim().toLowerCase()
  return (catalog.value?.items ?? []).filter(item => {
    if (assetType.value !== 'all' && item.asset_type !== assetType.value) return false
    if (sharedOnly.value && item.platforms.length < 2) return false
    const offerings = item.offerings.filter(offering => platform.value === 'all' || offering.platform === platform.value)
    if (!offerings.length) return false
    if (tradingType.value === 'both') {
      if (!offerings.some(offering => offering.trading_type === 'spot') || !offerings.some(offering => offering.trading_type === 'perpetual')) return false
    } else if (tradingType.value !== 'all' && !offerings.some(offering => offering.trading_type === tradingType.value)) return false
    return !query || [item.ticker, item.name, item.name_zh, ...item.offerings.map(offering => offering.symbol)].some(value => value.toLowerCase().includes(query))
  }).sort((a, b) => sort.value === 'name' ? a.name.localeCompare(b.name) : (sort.value === 'coverage' ? b.platforms.length - a.platforms.length : 0) || a.ticker.localeCompare(b.ticker))
})
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const selectedStock = computed(() => paged.value.find(item => item.ticker === selectedTicker.value) ?? null)
watch([search, platform, tradingType, assetType, sharedOnly, sort, pageSize], () => { page.value = 1 })
watch(pageCount, value => { page.value = Math.min(page.value, value) })
watch(paged, items => { if (items.length && !items.some(item => item.ticker === selectedTicker.value)) selectedTicker.value = items[0].ticker })
function selectStock(item: EquityCatalogItemResponse) { selectedTicker.value = item.ticker; detailOpen.value = true }
function toggleStock(item: EquityCatalogItemResponse) {
  if (selectedTicker.value === item.ticker) detailOpen.value = !detailOpen.value
  else selectStock(item)
}
function resetFilters() { search.value = ''; platform.value = 'all'; tradingType.value = 'all'; assetType.value = 'all'; sharedOnly.value = false }
function searchShortcut(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || target?.closest('input, textarea, select, [contenteditable=true]')) return
  event.preventDefault(); searchInput.value?.focus()
}
async function load(refresh = false) {
  if (loading.value) return
  loading.value = true; error.value = ''
  try { const result = await equityCatalogApi.getCatalog(refresh); if (active) catalog.value = result }
  catch (cause) { if (active) error.value = apiErrorMessage(cause, t('equities.loadFailed')) }
  finally { if (active) loading.value = false }
}
onMounted(() => { load(); window.addEventListener('keydown', searchShortcut) })
onBeforeUnmount(() => { active = false; window.removeEventListener('keydown', searchShortcut) })
</script>
