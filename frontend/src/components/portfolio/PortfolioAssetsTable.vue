<template>
  <section class="app-panel p-6">
    <div class="mb-5 flex flex-wrap items-center justify-between gap-4"><div>
      <h2 class="app-section-title">{{ $t('portfolioBalance.allocationTitle') }}</h2>
      <p class="app-subtitle mt-2">{{ $t('portfolioBalance.allocationSubtitle') }}</p>
      <p v-if="holdingsSource === 'virtual'" class="mt-3 border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">{{ $t('portfolioBalance.legacyVirtualHoldings') }}</p>
    </div><div class="flex flex-wrap gap-2"><AppLayoutSwitch v-model="assetLayout" :options="layoutOptions" /><button type="button" class="app-button-secondary" :disabled="marketLoading" @click="$emit('refresh')">{{ marketLoading ? $t('portfolioBalance.refreshing') : $t('portfolioBalance.refreshPrices') }}</button><button type="button" class="app-button-primary" @click="$emit('add')"><PlusIcon class="h-4 w-4" />{{ $t('portfolioBalance.addAsset') }}</button></div></div>
    <div v-if="assetLayout === 'split'" class="portfolio-asset-workspace">
      <aside class="market-quick-list">
        <button v-for="asset in assets" :key="asset.id" type="button" :aria-pressed="selectedAsset?.id === asset.id" @click="selectedId = asset.id"><span><strong>{{ asset.symbol || $t('portfolioBalance.emptySymbol') }}</strong><small>{{ $t('workspaceViews.targetWeight') }} {{ asset.targetWeight }}%</small></span><span class="market-list-value">{{ asset.currentPrice && asset.units ? formatAssetMoney(asset, holdingValue(asset)) : '—' }}</span></button>
      </aside>
      <section v-if="selectedAsset" class="portfolio-asset-detail">
        <header class="mb-5 flex flex-wrap items-center justify-between gap-3"><h3 class="text-xl font-semibold">{{ selectedAsset.symbol || $t('portfolioBalance.emptySymbol') }}</h3><button type="button" class="app-button-secondary" :disabled="!canRemoveAsset || selectedAsset.units > 0" @click="$emit('remove', selectedAsset.id)">{{ $t('portfolioBalance.remove') }}</button></header>
        <dl class="app-metric-strip mb-5"><div><dt>{{ $t('workspaceViews.currentWeight') }}</dt><dd>{{ ((readPlanAsset(selectedAsset.id)?.currentWeight || 0) * 100).toFixed(2) }}%</dd></div><div><dt>{{ $t('workspaceViews.drift') }}</dt><dd>{{ ((readPlanAsset(selectedAsset.id)?.driftWeight || 0) * 100).toFixed(2) }} pp</dd></div></dl>
        <div class="grid gap-5 sm:grid-cols-2">
          <label><span class="label">{{ $t('portfolioBalance.symbol') }}</span><SymbolSearchBox :model-value="selectedAsset.symbol" :aria-label="$t('portfolioBalance.symbol')" output-mode="base" :allowed-classes="['crypto', 'index', 'cash']" :disabled="holdingsSource === 'ledger' && selectedAsset.units > 0" :disabled-label="$t('portfolioBalance.ledgerSymbolLocked')" @update:model-value="$emit('update-symbol', selectedAsset.id, String($event))" /></label>
          <label><span class="label">{{ $t('portfolioBalance.targetWeight') }}</span><input :value="selectedAsset.targetWeight" type="number" min="0" step="0.5" class="app-control w-full" @input="$emit('update-weight', selectedAsset.id, $event.target.value || '')" /></label>
        </div>
        <dl class="mt-6 grid grid-cols-2 gap-5 text-sm"><div><dt class="app-muted">{{ $t('portfolioBalance.price', { currency: displayCurrency }) }}</dt><dd class="mt-2">{{ selectedAsset.currentPrice ? formatAssetPrice(selectedAsset) : '—' }}</dd></div><div><dt class="app-muted">{{ $t('portfolioBalance.unitsHeld') }}</dt><dd class="mt-2">{{ selectedAsset.units ? selectedAsset.units.toFixed(8) : '—' }}</dd></div><div><dt class="app-muted">{{ $t('portfolioBalance.currentValue', { currency: displayCurrency }) }}</dt><dd class="mt-2">{{ selectedAsset.currentPrice && selectedAsset.units ? formatAssetMoney(selectedAsset, holdingValue(selectedAsset)) : '—' }}</dd></div><div><dt class="app-muted">{{ $t('portfolioBalance.trackingDiffValue', { currency: displayCurrency }) }}</dt><dd class="mt-2" :class="returnClass(readPlanAsset(selectedAsset.id)?.trackingDiffValue || 0)">{{ selectedAsset.currentPrice && selectedAsset.units ? signedAssetMoney(selectedAsset, readPlanAsset(selectedAsset.id)?.trackingDiffValue || 0) : '—' }}</dd></div></dl>
      </section>
    </div>
    <div v-show="assetLayout === 'table'" class="overflow-hidden border border-[#e4ded3] dark:border-slate-700"><div class="overflow-x-auto"><table class="min-w-full divide-y divide-slate-200 dark:divide-slate-700">
      <thead class="app-table-head dark:bg-slate-900/60"><tr class="text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        <th class="px-4 py-3">{{ $t('portfolioBalance.symbol') }}</th><th class="px-4 py-3"><span :class="hasExactTargetWeightSum ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'">{{ $t('portfolioBalance.targetWeight') }} ({{ formatWeightSum(plan.targetWeightInputSum) }})</span></th><th class="px-4 py-3">{{ $t('portfolioBalance.price', { currency: displayCurrency }) }}</th><th class="px-4 py-3">{{ $t('portfolioBalance.unitsHeld') }}</th><th class="px-4 py-3">{{ $t('portfolioBalance.currentValue', { currency: displayCurrency }) }}</th><th class="px-4 py-3">{{ $t('portfolioBalance.trackingDiffValue', { currency: displayCurrency }) }}</th><th class="px-4 py-3">{{ $t('portfolioBalance.remove') }}</th>
      </tr></thead>
      <tbody class="divide-y divide-slate-200 bg-white dark:divide-slate-700 dark:bg-slate-800"><tr v-for="asset in assets" :key="asset.id">
        <td class="px-4 py-3"><SymbolSearchBox :model-value="asset.symbol" :aria-label="$t('portfolioBalance.symbol')" output-mode="base" :allowed-classes="['crypto', 'index', 'cash']" :placeholder="$t('portfolioBalance.emptySymbol')" trigger-class="!w-32 !bg-white dark:!bg-slate-900" :disabled="holdingsSource === 'ledger' && asset.units > 0" :disabled-label="$t('portfolioBalance.ledgerSymbolLocked')" @update:model-value="$emit('update-symbol', asset.id, String($event))" /></td>
        <td class="px-4 py-3"><input :aria-label="$t('portfolioBalance.targetWeight') + ': ' + (asset.symbol || $t('portfolioBalance.emptySymbol'))" :value="asset.targetWeight" type="number" min="0" step="0.5" class="app-control w-28 px-3 py-2" @input="$emit('update-weight', asset.id, $event.target.value || '')" /></td>
        <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ asset.currentPrice ? formatAssetPrice(asset) : '--' }}</td>
        <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ asset.units ? asset.units.toFixed(8) : '--' }}</td>
        <td class="px-4 py-3 text-slate-600 dark:text-slate-300">{{ asset.currentPrice && asset.units ? formatAssetMoney(asset, holdingValue(asset)) : '--' }}</td>
        <td class="px-4 py-3" :class="returnClass(readPlanAsset(asset.id)?.trackingDiffValue || 0)">{{ asset.currentPrice && asset.units ? signedAssetMoney(asset, readPlanAsset(asset.id)?.trackingDiffValue || 0) : '--' }}</td>
        <td class="px-4 py-3"><button type="button" class="app-touch-target inline-flex items-center border border-slate-300 px-3 py-2 text-sm text-slate-500 transition hover:border-rose-300 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-600 dark:text-slate-300 dark:hover:border-rose-500 dark:hover:text-rose-300" :aria-label="$t('portfolioBalance.removeAsset', { symbol: asset.symbol || $t('portfolioBalance.emptySymbol') })" :title="asset.units > 0 ? $t('portfolioBalance.ledgerSymbolLocked') : $t('portfolioBalance.removeAsset', { symbol: asset.symbol || $t('portfolioBalance.emptySymbol') })" :disabled="!canRemoveAsset || asset.units > 0" @click="$emit('remove', asset.id)"><TrashIcon class="h-4 w-4" /></button></td>
      </tr></tbody>
    </table></div></div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { PlusIcon, TrashIcon } from '@heroicons/vue/24/outline'
import AppLayoutSwitch from '@/components/AppLayoutSwitch.vue'
import { usePageLayout } from '@/composables/usePageLayout'
import { useI18n } from 'vue-i18n'
import SymbolSearchBox from '@/components/SymbolSearchBox.vue'
import { computePortfolioAssetHoldingValue } from '@/modules/tools/portfolioBalance'
import { findSymbolCatalogItem } from '@/modules/market'
import { useMoney } from '@/composables/useMoney'

const props = defineProps({ assets: { type: Array, required: true }, plan: { type: Object, required: true }, canRemoveAsset: Boolean, marketLoading: Boolean, holdingsSource: { type: String, default: null } })
defineEmits(['update-symbol', 'update-weight', 'remove', 'add', 'refresh'])
const { displayCurrency, formatMoney, formatSignedMoney } = useMoney()
const assetMeta = (asset) => findSymbolCatalogItem(asset?.symbol || '')
const assetCurrency = (asset) => assetMeta(asset)?.pricing_currency || assetMeta(asset)?.currency || 'USDT'
const formatAssetPrice = (asset) => formatMoney(asset.currentPrice, assetCurrency(asset))
const formatAssetMoney = (asset, value) => formatMoney(value, assetCurrency(asset))
const signedAssetMoney = (asset, value) => formatSignedMoney(value, assetCurrency(asset))
const holdingValue = (asset) => computePortfolioAssetHoldingValue(asset)
const formatWeightSum = (value) => `${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}%`
const hasExactTargetWeightSum = computed(() => Math.abs(Number(props.plan?.targetWeightInputSum || 0) - 100) < 0.005)
const readPlanAsset = (assetId) => props.plan.assets.find((item) => item.id === assetId) || null
const returnClass = (value) => value > 0 ? 'text-emerald-600 dark:text-emerald-300' : value < 0 ? 'text-rose-600 dark:text-rose-300' : 'text-slate-600 dark:text-slate-300'

const { t } = useI18n()
const assetLayout = usePageLayout('portfolio-assets', ['table', 'split'], 'table')
const layoutOptions = computed(() => ['table', 'split'].map(value => ({ value, label:t(`workspaceViews.${value}`) })))
const selectedId = ref('')
const selectedAsset = computed(() => props.assets.find(asset => asset.id === selectedId.value) || props.assets[0])
watch(selectedAsset, asset => { if (asset) selectedId.value = asset.id }, { immediate:true })
</script>
<style scoped>
.portfolio-asset-workspace { display:grid; grid-template-columns:260px minmax(0,1fr); gap:24px; align-items:start; }
.portfolio-asset-detail { min-width:0; padding:4px; }
@container app-content (max-width:56rem) { .portfolio-asset-workspace { grid-template-columns:minmax(0,1fr); } .portfolio-asset-workspace .market-quick-list { max-height:260px; } }
</style>
