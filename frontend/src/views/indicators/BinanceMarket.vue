<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <header class="app-workspace-header">
        <h1 class="app-title">{{ t('nav.binanceMarket') }}</h1>
        <div class="flex flex-wrap items-center gap-3">
          <button type="button" class="app-button-secondary" :aria-pressed="autoRefresh" @click="autoRefresh = !autoRefresh">
            <span class="binance-live-dot" :class="{ 'is-active': autoRefresh }" aria-hidden="true" />
            {{ t('binanceMarket.autoRefresh') }} · {{ autoRefresh ? t('binanceMarket.autoRefreshOn') : t('binanceMarket.autoRefreshOff') }}
          </button>
          <button type="button" class="app-button-secondary" :disabled="loading" @click="fetchData">{{ loading ? t('binanceMarket.refreshing') : t('binanceMarket.refresh') }}</button>
        </div>
      </header>
      <dl class="app-metric-strip">
        <div v-for="card in summaryCards" :key="card.label"><dt :title="card.hint">{{ card.label }}</dt><dd>{{ card.value }}</dd></div>
      </dl>
      <div v-if="error" role="alert" class="app-inline-note text-rose-700 dark:text-rose-300">{{ error }}</div>
      <AppTabs id="binance" v-model="activeView" :label="t('nav.binanceMarket')" :tabs="viewTabs" />
      <section v-show="activeView === 'monitor'" id="binance-panel-monitor" role="tabpanel" aria-labelledby="binance-tab-monitor" tabindex="0" class="space-y-4">
        <div class="binance-monitor-toolbar flex flex-col gap-3">
              <div class="flex flex-col gap-4 px-2 xl:flex-row xl:items-center xl:justify-between">
                <div class="flex flex-wrap items-baseline gap-3">

                  <span class="bg-[#0f6b4f] px-2 py-0.5 text-xs font-semibold text-white dark:bg-emerald-500 dark:text-slate-950">{{ monitor.quote_asset }}</span>
                  <span class="text-xs text-slate-500 dark:text-slate-400">{{ t('binanceMarket.updatedAt', { time: formatTime(monitor.updated_at) }) }}</span>
                </div>

                <label class="app-control flex w-fit items-center gap-2 px-3 py-1.5 text-sm">
                  <span class="text-slate-500 dark:text-slate-400">{{ t('binanceMarket.minRisePct') }}</span>
                  <input v-model.number="minRisePct" type="number" min="1" max="30" step="0.5" class="w-14 bg-transparent text-center font-semibold text-slate-900 outline-none dark:text-white" />
                </label>
              </div>
              <div class="flex flex-wrap items-center gap-3">
                <div class="flex flex-wrap gap-2 border border-stone-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
                  <button
                    v-for="item in [
                      { key: 'focus', label: t('binanceMarket.filters.focus') },
                      { key: 'momentum', label: t('binanceMarket.filters.momentum') },
                      { key: 'natural', label: t('binanceMarket.filters.natural') },
                      { key: 'all', label: t('binanceMarket.filters.all') },
                    ]"
                    :key="item.key"
                    @click="mode = item.key"
                    class="app-segment-button"
                    :class="{ 'is-active': mode === item.key }"
                    :aria-pressed="mode === item.key"
                  >
                    {{ item.label }}
                  </button>
                </div>

                <div class="flex flex-wrap gap-2 border border-stone-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900">
                  <button
                    v-for="item in [
                      { key: 'all', label: t('binanceMarket.market.all') },
                      { key: 'spot', label: t('binanceMarket.market.spot') },
                      { key: 'usdm', label: t('binanceMarket.market.usdm') },
                    ]"
                    :key="item.key"
                    @click="marketFilter = item.key"
                    class="app-segment-button"
                    :class="{ 'is-active': marketFilter === item.key }"
                    :aria-pressed="marketFilter === item.key"
                  >
                    {{ item.label }}
                  </button>
                </div>
              </div>
            </div>

        <AppLoadingState v-if="loading && !filteredItems.length" :label="t('binanceMarket.refreshing')" />
        <article v-else class="app-responsive-table app-panel overflow-hidden">
                <div class="app-panel-header flex items-center justify-between">
                  <div>
                    <h2 class="text-lg font-semibold text-slate-900 dark:text-white">{{ t('binanceMarket.tables.monitorList') }}</h2>
                    <p class="text-sm text-slate-500 dark:text-slate-400">{{ t('binanceMarket.resultCount', { count: filteredItems.length }) }}</p>
                  </div>
                </div>

                <div class="app-table-scroll" tabindex="0" :aria-label="t('binanceMarket.tables.monitorList')">
                  <table class="app-data-table w-full min-w-[56rem] text-left text-sm">
                    <thead class="app-table-head">
                      <tr>
                        <th class="px-5 py-3 font-semibold">{{ t('binanceMarket.columns.asset') }}</th>
                        <th class="px-4 py-3 font-semibold">{{ t('binanceMarket.columns.today') }}</th>
                        <th class="px-4 py-3 font-semibold">15m</th>
                        <th class="px-4 py-3 font-semibold">1h</th>
                        <th class="px-4 py-3 font-semibold">{{ t('binanceMarket.columns.naturalScore') }}</th>
                        <th class="px-4 py-3 font-semibold">{{ t('binanceMarket.columns.momentumScore') }}</th>
                        <th class="px-5 py-3 font-semibold">{{ t('binanceMarket.columns.status') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="item in filteredItems"
                        :key="`${item.market}-${item.symbol}`"
                        class="app-table-row"
                        :class="chartDialog.open && detailKey === toItemKey(item) ? 'bg-[#edf3ee] dark:bg-emerald-500/10' : ''"
                      >
                        <td class="app-table-primary px-5 py-4" :data-label="t('binanceMarket.columns.asset')">
                          <div class="flex items-center gap-3">
                            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">{{ formatMarketLabel(item) }}</span>
                            <div>
                              <button
                                type="button"
                                class="app-touch-target font-semibold text-slate-900 transition hover:text-[#0f6b4f] dark:text-white dark:hover:text-emerald-300"
                                @click="openMonitorDetail(item)"
                              >
                                {{ displaySymbol(item.symbol) }}
                              </button>
                              <div class="text-xs text-slate-500 dark:text-slate-400">{{ formatPrice(item.mark_price ?? item.last_price) }}</div>
                            </div>
                          </div>
                        </td>
                        <td class="px-4 py-4 font-medium" :data-label="t('binanceMarket.columns.today')" :class="valueTone(item.price_change_pct)">{{ formatSigned(item.price_change_pct) }}</td>
                        <td class="px-4 py-4" data-label="15m" :class="valueTone(item.change_15m_pct)">{{ formatSigned(item.change_15m_pct) }}</td>
                        <td class="px-4 py-4" data-label="1h" :class="valueTone(item.change_1h_pct)">{{ formatSigned(item.change_1h_pct) }}</td>
                        <td class="px-4 py-4 text-slate-700 dark:text-slate-300" :data-label="t('binanceMarket.columns.naturalScore')">{{ formatScore(item.natural_score) }}</td>
                        <td class="px-4 py-4 text-slate-700 dark:text-slate-300" :data-label="t('binanceMarket.columns.momentumScore')">{{ formatScore(item.momentum_score) }}</td>
                        <td class="px-5 py-4" :data-label="t('binanceMarket.columns.status')">
                          <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1" :class="verdictTone(item.verdict)">
                            {{ formatVerdict(item.verdict) }}
                          </span>
                        </td>
                      </tr>
                      <tr v-if="!filteredItems.length" class="app-table-empty-row">
                        <td colspan="7" class="px-5 py-10 text-center text-sm text-slate-500 dark:text-slate-400">
                          {{ t('binanceMarket.tables.noMonitorRows') }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </article>
      </section>
      <section v-show="activeView === 'rankings'" id="binance-panel-rankings" role="tabpanel" aria-labelledby="binance-tab-rankings" tabindex="0" class="space-y-4">
        <AppTabs id="binance-rank" v-model="activeRank" :label="t('binanceMarket.rankTitle')" :tabs="rankTabs" />
        <section v-show="activeRank === 'contracts'" id="binance-rank-panel-contracts" role="tabpanel" aria-labelledby="binance-rank-tab-contracts" tabindex="0">
          <AppLoadingState v-if="loading && !contractRows.length" :label="t('binanceMarket.refreshing')" />
          <article v-else class="app-responsive-table app-panel overflow-hidden">
                <div class="app-panel-header flex items-center justify-between">
                  <div>
                    <h2 class="text-lg font-semibold text-slate-900 dark:text-white">{{ t('binanceMarket.tables.rankContract') }}</h2>
                  </div>
                </div>

                <div class="app-table-scroll" tabindex="0" :aria-label="t('binanceMarket.tables.rankContract')">
                  <table class="app-data-table w-full min-w-[58rem] text-left text-sm">
                    <thead class="app-table-head">
                      <tr>
                        <th class="px-5 py-3 font-semibold">{{ t('binanceMarket.columns.asset') }}</th>
                        <th class="px-5 py-3 font-semibold" :aria-sort="contractSort.field === 'price_change_pct' ? (contractSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'">
                          <button
                            type="button"
                            @click="toggleContractSort('price_change_pct')"
                            class="app-touch-target inline-flex items-center gap-2 transition"
                            :class="contractSort.field === 'price_change_pct' ? 'text-slate-900 dark:text-white' : 'hover:text-slate-700 dark:hover:text-slate-200'"
                          >
                            <span>{{ t('binanceMarket.columns.change24hShort') }}</span>
                            <span class="text-xs">{{ sortDirectionIcon(contractSort.field === 'price_change_pct', contractSort.direction) }}</span>
                          </button>
                        </th>
                        <th class="px-5 py-3 font-semibold">{{ t('binanceMarket.columns.price') }}</th>
                        <th class="px-5 py-3 font-semibold" :aria-sort="contractSort.field === 'oi_change_24h_pct' ? (contractSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'">
                          <button
                            type="button"
                            @click="toggleContractSort('oi_change_24h_pct')"
                            class="app-touch-target inline-flex items-center gap-2 transition"
                            :class="contractSort.field === 'oi_change_24h_pct' ? 'text-slate-900 dark:text-white' : 'hover:text-slate-700 dark:hover:text-slate-200'"
                          >
                            <span>{{ t('binanceMarket.columns.oi24h') }}</span>
                            <span class="text-xs">{{ sortDirectionIcon(contractSort.field === 'oi_change_24h_pct', contractSort.direction) }}</span>
                          </button>
                        </th>
                        <th class="px-5 py-3 font-semibold" :aria-sort="contractSort.field === 'funding_rate_pct' ? (contractSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'">
                          <button
                            type="button"
                            @click="toggleContractSort('funding_rate_pct')"
                            class="app-touch-target inline-flex items-center gap-2 transition"
                            :class="contractSort.field === 'funding_rate_pct' ? 'text-slate-900 dark:text-white' : 'hover:text-slate-700 dark:hover:text-slate-200'"
                          >
                            <span>{{ t('binanceMarket.columns.funding') }}</span>
                            <span class="text-xs">{{ sortDirectionIcon(contractSort.field === 'funding_rate_pct', contractSort.direction) }}</span>
                          </button>
                        </th>
                        <th class="px-5 py-3 font-semibold" :aria-sort="contractSort.field === 'quote_volume' ? (contractSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'">
                          <button
                            type="button"
                            @click="toggleContractSort('quote_volume')"
                            class="app-touch-target inline-flex items-center gap-2 transition"
                            :class="contractSort.field === 'quote_volume' ? 'text-slate-900 dark:text-white' : 'hover:text-slate-700 dark:hover:text-slate-200'"
                          >
                            <span>{{ t('binanceMarket.columns.quoteVolume') }}</span>
                            <span class="text-xs">{{ sortDirectionIcon(contractSort.field === 'quote_volume', contractSort.direction) }}</span>
                          </button>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="item in contractRows"
                        :key="`${item.market}-${item.symbol}`"
                        class="app-table-row"
                      >
                        <td class="app-table-primary px-5 py-4 font-medium text-slate-900 dark:text-white" :data-label="t('binanceMarket.columns.asset')">
                          <button
                            type="button"
                            class="app-touch-target px-2 py-1 transition hover:bg-[#edf3ee] hover:text-[#0f6b4f] dark:hover:bg-emerald-500/10 dark:hover:text-emerald-300"
                            @click="openChart(item)"
                          >
                            {{ displaySymbol(item.symbol) }}
                          </button>
                        </td>
                        <td class="px-5 py-4" :data-label="t('binanceMarket.columns.change24hShort')" :class="valueTone(item.price_change_pct)">{{ formatSigned(item.price_change_pct) }}</td>
                        <td class="px-5 py-4 text-slate-600 dark:text-slate-300" :data-label="t('binanceMarket.columns.price')">{{ formatPrice(item.mark_price ?? item.last_price) }}</td>
                        <td class="px-5 py-4" :data-label="t('binanceMarket.columns.oi24h')" :class="valueTone(item.oi_change_24h_pct)">{{ formatSigned(item.oi_change_24h_pct) }}</td>
                        <td class="px-5 py-4" :data-label="t('binanceMarket.columns.funding')" :class="valueTone(item.funding_rate_pct)">{{ formatSigned(item.funding_rate_pct, 4) }}</td>
                        <td class="px-5 py-4 text-slate-600 dark:text-slate-300" :data-label="t('binanceMarket.columns.quoteVolume')">{{ formatCompact(item.quote_volume) }}</td>
                      </tr>
                      <tr v-if="!contractRows.length" class="app-table-empty-row">
                        <td colspan="6" class="px-5 py-8 text-center text-sm text-slate-400 dark:text-slate-500">{{ t('binanceMarket.tables.noContractRows') }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </article>
        </section>
        <section v-show="activeRank === 'spot'" id="binance-rank-panel-spot" role="tabpanel" aria-labelledby="binance-rank-tab-spot" tabindex="0">
          <AppLoadingState v-if="loading && !spotRows.length" :label="t('binanceMarket.refreshing')" />
          <article v-else class="app-responsive-table app-panel overflow-hidden">
                <div class="app-panel-header flex items-center justify-between">
                  <div>
                    <h2 class="text-lg font-semibold text-slate-900 dark:text-white">{{ t('binanceMarket.tables.rankSpot') }}</h2>
                  </div>
                </div>
                <div class="app-table-scroll" tabindex="0" :aria-label="t('binanceMarket.tables.rankSpot')">
                  <table class="app-data-table w-full min-w-[44rem] text-left text-sm">
                    <thead class="app-table-head">
                      <tr>
                        <th class="px-5 py-3 font-semibold">{{ t('binanceMarket.columns.asset') }}</th>
                        <th class="px-5 py-3 font-semibold" :aria-sort="spotSort.field === 'price_change_pct' ? (spotSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'">
                          <button
                            type="button"
                            @click="toggleSpotSort('price_change_pct')"
                            class="app-touch-target inline-flex items-center gap-2 transition"
                            :class="spotSort.field === 'price_change_pct' ? 'text-slate-900 dark:text-white' : 'hover:text-slate-700 dark:hover:text-slate-200'"
                          >
                            <span>{{ t('binanceMarket.columns.change24hShort') }}</span>
                            <span class="text-xs">{{ sortDirectionIcon(spotSort.field === 'price_change_pct', spotSort.direction) }}</span>
                          </button>
                        </th>
                        <th class="px-5 py-3 font-semibold">{{ t('binanceMarket.columns.price') }}</th>
                        <th class="px-5 py-3 font-semibold" :aria-sort="spotSort.field === 'quote_volume' ? (spotSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'">
                          <button
                            type="button"
                            @click="toggleSpotSort('quote_volume')"
                            class="app-touch-target inline-flex items-center gap-2 transition"
                            :class="spotSort.field === 'quote_volume' ? 'text-slate-900 dark:text-white' : 'hover:text-slate-700 dark:hover:text-slate-200'"
                          >
                            <span>{{ t('binanceMarket.columns.quoteVolume') }}</span>
                            <span class="text-xs">{{ sortDirectionIcon(spotSort.field === 'quote_volume', spotSort.direction) }}</span>
                          </button>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(item, index) in spotRows" :key="item.symbol || `spot-${index}`" class="app-table-row">
                        <td class="app-table-primary px-5 py-4 font-medium text-slate-900 dark:text-white" :data-label="t('binanceMarket.columns.asset')">
                          <button
                            type="button"
                            class="app-touch-target px-2 py-1 transition hover:bg-[#edf3ee] hover:text-[#0f6b4f] dark:hover:bg-emerald-500/10 dark:hover:text-emerald-300"
                            @click="openChart({ ...item, market: 'spot' })"
                          >
                            {{ displaySymbol(item.symbol) }}
                          </button>
                        </td>
                        <td class="px-5 py-4" :data-label="t('binanceMarket.columns.change24hShort')" :class="valueTone(item.price_change_pct)">{{ formatSigned(item.price_change_pct) }}</td>
                        <td class="px-5 py-4 text-slate-600 dark:text-slate-300" :data-label="t('binanceMarket.columns.price')">{{ formatPrice(item.last_price) }}</td>
                        <td class="px-5 py-4 text-slate-600 dark:text-slate-300" :data-label="t('binanceMarket.columns.quoteVolume')">{{ formatCompact(item.quote_volume) }}</td>
                      </tr>
                      <tr v-if="!spotRows.length" class="app-table-empty-row">
                        <td colspan="4" class="px-5 py-8 text-center text-sm text-slate-400 dark:text-slate-500">{{ t('binanceMarket.tables.noSpotRows') }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </article>
        </section>
      </section>
    </div>
    <BinanceSymbolChartDialog
      :open="chartDialog.open"
      :market-label="chartMarketLabel"
      :title="chartTitle"
      :symbol="chartSymbol"
      :timeframe="chartTimeframe"
      :timeframes="chartTimeframes"
      :chart-colors="chartColors"
      :chart-data="chartData"
      :volume-data="volumeData"
      :loading-more="chartLoadingMore"
      :chart-error="chartError"
      :contract-detail="contractDetail"
      :contract-detail-loading="contractDetailLoading"
      :contract-detail-error="contractDetailError"
      :monitor-item="detailItem"
      :format-score="formatScore"
      :format-signed="formatSigned"
      :format-compact="formatCompact"
      :value-tone="valueTone"
      :verdict-tone="verdictTone"
      :format-verdict="formatVerdict"
      :format-follow-status="formatFollowStatus"
      :format-reason="formatReason"
      @close="closeChart"
      @load-more="loadMoreChartHistory"
      @retry-chart="retryChart"
      @update:timeframe="chartTimeframe = $event"
    />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'BinanceMarket' })

import { computed, ref } from 'vue'
import AppTabs from '@/components/AppTabs.vue'
import AppLoadingState from '@/components/AppLoadingState.vue'
import BinanceSymbolChartDialog from '@/components/market/BinanceSymbolChartDialog.vue'
import { useBinanceMarketPage } from '@/modules/market'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const activeView = ref('monitor')
const activeRank = ref('contracts')
const viewTabs = computed(() => [
  { id: 'monitor', label: t('binanceMarket.tables.monitor'), count: filteredItems.value.length },
  { id: 'rankings', label: t('binanceMarket.rankTitle') },
])
const rankTabs = computed(() => [
  { id: 'contracts', label: t('binanceMarket.tables.rankContract'), count: contractRows.value.length },
  { id: 'spot', label: t('binanceMarket.tables.rankSpot'), count: spotRows.value.length },
])

const {
  loading,
  error,
  minRisePct,
  mode,
  marketFilter,
  autoRefresh,
  monitor,
  spotRows,
  spotSort,
  contractRows,
  contractSort,
  filteredItems,
  detailKey,
  detailItem,
  chartDialog,
  chartSymbol,
  chartTitle,
  chartMarketLabel,
  chartTimeframe,
  chartTimeframes,
  chartColors,
  chartData,
  volumeData,
  chartLoadingMore,
  chartError,
  contractDetail,
  contractDetailLoading,
  contractDetailError,
  openChart,
  closeChart,
  openMonitorDetail,
  loadMoreChartHistory,
  retryChart,
  summaryCards,
  fetchData,
  toggleSpotSort,
  toggleContractSort,
  formatSigned,
  formatScore,
  formatTime,
  formatPrice,
  formatCompact,
  displaySymbol,
  formatMarketLabel,
  formatVerdict,
  formatFollowStatus,
  formatReason,
  sortDirectionIcon,
  valueTone,
  verdictTone,
  toItemKey,
} = useBinanceMarketPage()
</script>

<style scoped>
.binance-monitor-toolbar { padding: 0 0 4px; }
.binance-live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ui-faint); }
.binance-live-dot.is-active { background: var(--ui-accent); }
[role=tabpanel]:focus { outline: none; }
</style>
