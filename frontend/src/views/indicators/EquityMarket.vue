<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <section class="app-page-header">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 class="app-title">{{ t('equities.title') }}</h1>
            <p v-if="catalog" class="app-muted mt-2 text-xs">{{ t('equities.updated', { time: formatDateTime(catalog.updated_at) }) }}</p>
          </div>
          <button type="button" class="app-button-primary inline-flex items-center gap-2" :disabled="loading" @click="load(true)">
            <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': loading }" />
            {{ loading ? t('equities.loading') : t('equities.refresh') }}
          </button>
        </div>
        <div class="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div v-for="stat in stats" :key="stat.label">
            <p class="app-muted text-xs">{{ stat.label }}</p>
            <p class="mt-1 text-2xl font-semibold tabular-nums">{{ catalog ? stat.value.toLocaleString() : '—' }}</p>
          </div>
        </div>
      </section>

      <div v-if="error" role="alert" class="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">{{ error }}</div>
      <div v-if="unavailableLabels" role="status" class="space-y-1 border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
        <p>{{ t('equities.partial') }} {{ unavailableLabels }}</p>
      </div>

      <section class="app-panel">
        <div class="app-panel-header space-y-4">
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(240px,2fr)_1fr_1fr_1fr]">
            <div>
              <label class="label" for="equity-search">{{ t('equities.search') }}</label>
              <input id="equity-search" v-model="search" type="search" class="app-control w-full" :placeholder="t('equities.searchPlaceholder')" />
            </div>
            <div>
              <label class="label" for="equity-platform">{{ t('equities.platform') }}</label>
              <select id="equity-platform" v-model="platform" class="app-control w-full">
                <option value="all">{{ t('equities.allPlatforms') }}</option>
                <option v-for="p in platforms" :key="p" :value="p">{{ platformName(p) }}</option>
              </select>
            </div>
            <div>
              <label class="label" for="equity-trading-type">{{ t('equities.tradingType') }}</label>
              <select id="equity-trading-type" v-model="tradingType" class="app-control w-full">
                <option value="all">{{ t('equities.allTradingTypes') }}</option>
                <option value="spot">{{ t('equities.spot') }}</option>
                <option value="perpetual">{{ t('equities.perpetual') }}</option>
                <option value="both">{{ t('equities.both') }}</option>
              </select>
            </div>
            <div>
              <label class="label" for="equity-asset-type">{{ t('equities.assetType') }}</label>
              <select id="equity-asset-type" v-model="assetType" class="app-control w-full">
                <option value="all">{{ t('equities.allAssets') }}</option>
                <option value="stock">{{ t('equities.stock') }}</option>
                <option value="etf">ETF</option>
                <option value="index">{{ t('equities.index') }}</option>
                <option value="unknown">{{ t('equities.unknown') }}</option>
              </select>
            </div>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-3 text-xs">
            <p class="app-muted" aria-live="polite">{{ t('equities.results', { count: filtered.length, total: catalog?.items.length ?? 0 }) }}</p>
            <div class="flex flex-wrap items-center gap-3">
              <label class="flex items-center gap-2"><input v-model="sharedOnly" type="checkbox" class="accent-emerald-700" />{{ t('equities.sharedOnly') }}</label>
              <label class="app-muted" for="equity-sort">{{ t('equities.sort') }}</label>
              <select id="equity-sort" v-model="sort" class="app-control py-1 text-xs">
                <option value="coverage">{{ t('equities.sortCoverage') }}</option>
                <option value="ticker">{{ t('equities.sortTicker') }}</option>
                <option value="name">{{ t('equities.sortName') }}</option>
              </select>
              <button v-if="hasFilters" type="button" class="font-semibold text-emerald-700 underline dark:text-emerald-300" @click="resetFilters">{{ t('equities.reset') }}</button>
            </div>
          </div>
        </div>
        <div class="app-table-scroll" tabindex="0" :aria-label="t('equities.title')" :aria-busy="loading">
          <table class="w-full min-w-[800px] text-left text-sm">
            <thead class="app-table-head text-xs">
              <tr>
                <th scope="col" class="px-5 py-3">{{ t('equities.security') }}</th>
                <th scope="col" class="px-4 py-3">{{ t('equities.assetType') }}</th>
                <th scope="col" class="px-4 py-3">{{ t('equities.supportedPlatforms') }}</th>
                <th scope="col" class="px-4 py-3">{{ t('equities.tradingType') }}</th>
                <th scope="col" class="px-5 py-3 text-right">{{ t('equities.products') }}</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="item in paged" :key="item.ticker">
                <tr class="app-table-row">
                  <td class="max-w-[310px] px-5 py-4">
                    <div class="flex items-center gap-3">
                      <EquityCompanyLogo :src="item.logo_url" :ticker="item.ticker" />
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                          <span class="font-mono text-base font-bold text-stone-950 dark:text-white">{{ item.ticker }}</span>
                          <span v-if="item.name_zh" class="text-xs">{{ item.name_zh }}</span>
                          <span v-if="item.market !== 'US'" class="app-muted text-[10px]">{{ item.market }}</span>
                        </div>
                        <p class="app-muted mt-1 truncate text-xs" :title="item.name">{{ item.name }}</p>
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-4 text-xs">{{ assetName(item.asset_type) }}</td>
                  <td class="px-4 py-4"><div class="flex flex-wrap gap-2"><span v-for="p in item.platforms" :key="p" class="equity-platform-tag" :class="`equity-platform-tag--${p}`" :title="platformDescription(item, p)">{{ platformName(p) }}</span></div></td>
                  <td class="px-4 py-4"><div class="flex flex-wrap gap-2">
                    <span v-if="item.trading_types.includes('spot')" class="equity-type-tag equity-type-tag--spot">{{ t('equities.spot') }}</span>
                    <span v-if="item.trading_types.includes('perpetual')" class="equity-type-tag equity-type-tag--perpetual">{{ t('equities.perpetual') }}</span>
                  </div></td>
                  <td class="px-5 py-4 text-right">
                    <button type="button" class="app-touch-target inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300" :aria-label="t('equities.expand', { ticker: item.ticker })" :aria-expanded="expanded === item.ticker" :aria-controls="`equity-detail-${item.ticker}`" @click="expanded = expanded === item.ticker ? '' : item.ticker">
                      {{ t('equities.productCount', { count: item.offerings.length }) }}<ChevronDownIcon class="h-4 w-4" :class="{ 'rotate-180': expanded === item.ticker }" />
                    </button>
                  </td>
                </tr>
                <tr v-if="expanded === item.ticker" :id="`equity-detail-${item.ticker}`" class="border-t border-stone-100 bg-stone-50/70 dark:border-slate-700 dark:bg-slate-900/40">
                  <td colspan="5" class="px-5 py-4"><div class="grid gap-3 lg:grid-cols-3">
                    <div v-for="p in item.platforms" :key="p" class="border border-stone-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
                      <h3 class="mb-2 text-xs font-semibold">{{ platformName(p) }}</h3>
                      <ul class="space-y-2"><li v-for="offering in item.offerings.filter(o => o.platform === p)" :key="`${offering.source_id}:${offering.symbol}`" class="flex flex-wrap items-center gap-2 text-xs">
                        <span class="equity-type-tag" :class="offering.trading_type === 'spot' ? 'equity-type-tag--spot' : 'equity-type-tag--perpetual'">{{ t(`equities.${offering.trading_type}`) }}</span>
                        <a :href="offering.url" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 font-mono font-semibold underline decoration-stone-300 underline-offset-4">{{ offering.symbol }}<ArrowTopRightOnSquareIcon class="h-3 w-3" /></a>
                        <span class="app-muted">{{ offering.product }}</span>
                        <span v-if="isRestricted(offering.status)" class="text-amber-700 dark:text-amber-300">{{ t('equities.restricted') }}</span>
                        <span v-if="isSourceStale(offering.source_id)" class="text-amber-700 dark:text-amber-300">{{ t('equities.cached') }}</span>
                      </li></ul>
                    </div>
                  </div></td>
                </tr>
              </template>
              <tr v-if="!paged.length"><td colspan="5" class="app-muted px-5 py-16 text-center">{{ loading ? t('equities.loading') : t('equities.empty') }}</td></tr>
            </tbody>
          </table>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-3 border-t border-stone-200 px-5 py-4 text-xs dark:border-slate-700">
          <label class="app-muted flex items-center gap-2">{{ t('equities.pageSize') }}<select v-model.number="pageSize" class="app-control py-1 text-xs"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option></select></label>
          <div class="flex items-center gap-3">
            <button type="button" class="app-button-secondary px-3 py-1 text-xs" :disabled="page <= 1" @click="page--">{{ t('equities.previous') }}</button>
            <span class="tabular-nums">{{ page }} / {{ pageCount }}</span>
            <button type="button" class="app-button-secondary px-3 py-1 text-xs" :disabled="page >= pageCount" @click="page++">{{ t('equities.next') }}</button>
          </div>
        </div>
      </section>

      <details v-if="catalog" class="app-panel">
        <summary class="cursor-pointer px-5 py-4 text-sm font-semibold">{{ t('equities.sources') }} · {{ catalog.sources.filter(s => s.status === 'ok').length }} / {{ catalog.sources.length }}</summary>
        <div class="space-y-3 border-t border-stone-200 px-5 py-4 dark:border-slate-700">
          <p class="app-muted text-xs leading-6">{{ t('equities.scope') }}</p>
          <div v-for="source in catalog.sources" :key="source.id" class="flex flex-wrap items-center justify-between gap-2 border-b border-stone-100 pb-3 text-xs last:border-0 dark:border-slate-700">
            <a :href="source.url" target="_blank" rel="noopener noreferrer" class="font-semibold underline underline-offset-4">{{ source.label }}</a>
            <span class="app-muted">{{ source.count.toLocaleString() }} · {{ source.updated_at ? formatDateTime(source.updated_at) : '—' }} · <span :class="source.status !== 'ok' ? 'text-amber-700 dark:text-amber-300' : ''">{{ source.error === 'catalog_not_verified' ? t('equities.sourceNotVerified') : t(`equities.sourceStatus.${source.status}`) }}</span></span>
          </div>
          <p class="app-muted text-xs leading-6">{{ t('equities.availability') }}</p>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowPathIcon, ArrowTopRightOnSquareIcon, ChevronDownIcon } from '@heroicons/vue/24/outline'
import { apiErrorMessage } from '@/api/request'
import { useDateTime } from '@/composables/useDateTime'
import EquityCompanyLogo from '@/components/market/EquityCompanyLogo.vue'
import { equityCatalogApi } from '@/modules/market/equityCatalog'
import type { EquityCatalogItemResponse, EquityCatalogResponse } from '@/modules/market/contracts'

const { t } = useI18n()
const { formatDateTime } = useDateTime()
const catalog = ref<EquityCatalogResponse | null>(null)
const loading = ref(false)
const error = ref('')
const search = ref('')
const platform = ref('all')
const tradingType = ref('all')
const assetType = ref('all')
const sharedOnly = ref(false)
const sort = ref('coverage')
const page = ref(1)
const pageSize = ref(50)
const expanded = ref('')
const platforms = ['binance', 'okx', 'bitget'] as const
let active = true

const platformName = (p: string) => p === 'binance' ? t('equities.binance') : p === 'okx' ? 'OKX' : 'Bitget'
const assetName = (kind: string) => kind === 'etf' ? 'ETF' : t(`equities.${kind}`)
const platformDescription = (item: EquityCatalogItemResponse, p: string) => `${platformName(p)}: ${[...new Set(item.offerings.filter(o => o.platform === p).map(o => t(`equities.${o.trading_type}`)))].join(' / ')}`
const isRestricted = (status: string) => !['trading', 'TRADING', 'BUY_SELL', 'live', 'online'].includes(status)
const isSourceStale = (id: string) => catalog.value?.sources.find(s => s.id === id)?.status === 'stale'
const unavailableLabels = computed(() => catalog.value?.sources.filter(s => s.status !== 'ok' && s.error !== 'catalog_not_verified').map(s => s.label).join(' / '))
const stats = computed(() => {
  const items = catalog.value?.items ?? []
  return [
    { label: t('equities.total'), value: items.length },
    { label: t('equities.withSpot'), value: items.filter(i => i.trading_types.includes('spot')).length },
    { label: t('equities.withPerpetual'), value: items.filter(i => i.trading_types.includes('perpetual')).length },
    { label: t('equities.shared'), value: items.filter(i => i.platforms.length > 1).length },
  ]
})
const hasFilters = computed(() => Boolean(search.value || platform.value !== 'all' || tradingType.value !== 'all' || assetType.value !== 'all' || sharedOnly.value))
const filtered = computed(() => {
  const query = search.value.trim().toLowerCase()
  return (catalog.value?.items ?? []).filter(item => {
    if (assetType.value !== 'all' && item.asset_type !== assetType.value) return false
    if (sharedOnly.value && item.platforms.length < 2) return false
    const offerings = item.offerings.filter(o => platform.value === 'all' || o.platform === platform.value)
    if (!offerings.length) return false
    if (tradingType.value === 'both') {
      if (!offerings.some(o => o.trading_type === 'spot') || !offerings.some(o => o.trading_type === 'perpetual')) return false
    } else if (tradingType.value !== 'all' && !offerings.some(o => o.trading_type === tradingType.value)) return false
    return !query || [item.ticker, item.name, item.name_zh, ...item.offerings.map(o => o.symbol)].some(v => v.toLowerCase().includes(query))
  }).sort((a, b) => sort.value === 'name' ? a.name.localeCompare(b.name) : (sort.value === 'coverage' ? b.platforms.length - a.platforms.length : 0) || a.ticker.localeCompare(b.ticker))
})
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
watch([search, platform, tradingType, assetType, sharedOnly, sort, pageSize], () => { page.value = 1; expanded.value = '' })
watch(pageCount, value => { page.value = Math.min(page.value, value) })
function resetFilters() {
  search.value = ''; platform.value = 'all'; tradingType.value = 'all'; assetType.value = 'all'; sharedOnly.value = false
}
async function load(refresh = false) {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await equityCatalogApi.getCatalog(refresh)
    if (active) catalog.value = result
  } catch (cause) {
    if (active) error.value = apiErrorMessage(cause, t('equities.loadFailed'))
  } finally {
    if (active) loading.value = false
  }
}
onMounted(() => load())
onBeforeUnmount(() => { active = false })
</script>

<style scoped>
.equity-platform-tag { @apply inline-flex items-center border px-2 py-1 text-[11px] font-semibold; }
.equity-platform-tag--binance { @apply border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200; }
.equity-platform-tag--okx { @apply border-stone-300 bg-stone-100 text-stone-800 dark:border-slate-500 dark:bg-slate-700 dark:text-slate-100; }
.equity-platform-tag--bitget { @apply border-cyan-200 bg-cyan-50 text-cyan-800 dark:border-cyan-500/30 dark:bg-cyan-500/10 dark:text-cyan-200; }
.equity-type-tag { @apply inline-flex whitespace-nowrap px-2 py-1 text-[10px] font-semibold; }
.equity-type-tag--spot { @apply bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300; }
.equity-type-tag--perpetual { @apply bg-indigo-50 text-indigo-800 dark:bg-indigo-500/15 dark:text-indigo-300; }
</style>
