<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-2 backdrop-blur-sm sm:p-4"
    @click.self="$emit('close')"
  >
    <section
      ref="dialogRef"
      role="dialog"
      aria-modal="true"
      aria-labelledby="binance-chart-dialog-title"
      tabindex="-1"
      class="flex h-[min(88vh,820px)] w-full max-w-7xl flex-col overflow-hidden border border-[#d8d1c5] bg-[#fbfaf7] shadow-2xl outline-none dark:border-slate-700 dark:bg-slate-800"
    >
      <header class="flex flex-wrap items-center justify-between gap-3 border-b border-[#e4ded3] px-4 py-4 dark:border-slate-700 sm:px-6 sm:py-5">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-3">
            <span class="border border-[#e4ded3] bg-white px-3 py-1 text-xs font-semibold text-stone-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">{{ marketLabel }}</span>
            <h3 id="binance-chart-dialog-title" class="text-2xl font-semibold text-slate-900 dark:text-white" :title="symbol">{{ title }}</h3>
          </div>
        </div>

        <div class="flex w-full min-w-0 items-center gap-2 sm:w-auto">
          <AddToResearchButton
            v-if="symbol"
            :symbol="symbol"
            asset-class="crypto"
            :display-name="title"
            :source-context="{ route: '/indicators/binance-market', marketLabel, timeframe }"
          />
          <div class="flex min-w-0 flex-1 gap-2 overflow-x-auto border border-[#e4ded3] bg-white p-1 dark:border-slate-700 dark:bg-slate-900 sm:flex-none">
            <button
              v-for="item in timeframes"
              :key="item"
              type="button"
              class="px-4 py-2 text-sm transition"
              :class="timeframe === item ? 'bg-[#0f6b4f] text-white dark:bg-emerald-600' : 'text-slate-600 hover:bg-[#f1ece3] dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white'"
              @click="$emit('update:timeframe', item)"
            >
              {{ item }}
            </button>
          </div>

          <button
            type="button"
            class="inline-flex h-10 w-10 flex-none items-center justify-center border border-[#e4ded3] bg-white text-stone-600 transition hover:bg-[#f1ece3] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
            :aria-label="t('binanceMarket.close')"
            :title="t('binanceMarket.close')"
            @click="$emit('close')"
          >
            <XMarkIcon class="h-5 w-5" />
          </button>
        </div>
      </header>

      <div class="grid min-h-0 flex-1 overflow-y-auto bg-slate-950 lg:overflow-hidden" :class="hasSidePanel ? 'lg:grid-cols-[minmax(0,1fr)_460px]' : ''">
        <div class="relative min-h-[320px] p-4 sm:min-h-[420px]">
          <div v-if="chartError" role="alert" class="absolute left-1/2 top-6 z-20 flex -translate-x-1/2 items-center gap-3 border border-rose-500/30 bg-rose-950/90 px-4 py-2 text-sm text-rose-200 shadow-lg">
            <span>{{ chartError }}</span>
            <button type="button" class="font-semibold underline" @click="emit('retryChart')">{{ t('app.retry') }}</button>
          </div>
          <div
            v-if="loadingMore"
            class="absolute left-1/2 top-6 z-10 -translate-x-1/2 bg-[#0f6b4f] px-3 py-1 text-xs font-semibold text-white shadow-lg"
          >
            {{ t('binanceMarket.loadingMoreHistory') }}
          </div>
          <TradingViewChart
            :data="chartData"
            :volume-data="volumeData"
            :colors="chartColors"
            @load-more="$emit('loadMore')"
          />
        </div>

        <aside v-if="hasSidePanel" class="border-t border-slate-800 bg-white p-5 dark:bg-slate-800 lg:overflow-y-auto lg:border-l lg:border-t-0">
          <div v-if="monitorItem" class="flex items-start justify-between gap-3">
            <div>
              <p class="text-sm text-slate-500 dark:text-slate-400">{{ renderFollowStatus(monitorItem.follow_status) }}</p>
              <h4 class="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{{ t('binanceMarket.tables.monitor') }}</h4>
            </div>
            <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold ring-1" :class="renderVerdictTone(monitorItem.verdict)">
              {{ renderVerdict(monitorItem.verdict) }}
            </span>
          </div>

          <div v-if="monitorItem" class="mt-5 grid grid-cols-2 gap-3">
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs uppercase tracking-[0.18em] text-slate-400">{{ t('binanceMarket.columns.today') }}</div>
              <div class="mt-2 text-lg font-semibold" :class="renderValueTone(monitorItem.price_change_pct)">{{ renderSigned(monitorItem.price_change_pct) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs uppercase tracking-[0.18em] text-slate-400">{{ t('binanceMarket.columns.quoteVolume') }}</div>
              <div class="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{{ renderCompact(monitorItem.quote_volume) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs uppercase tracking-[0.18em] text-slate-400">{{ t('binanceMarket.columns.naturalScore') }}</div>
              <div class="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{{ renderScore(monitorItem.natural_score) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs uppercase tracking-[0.18em] text-slate-400">{{ t('binanceMarket.columns.momentumScore') }}</div>
              <div class="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{{ renderScore(monitorItem.momentum_score) }}</div>
            </div>
          </div>

          <div v-if="monitorItem" class="mt-5 space-y-3 border border-[#e4ded3] bg-white p-4 text-stone-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white">
            <div class="flex items-center justify-between gap-4 text-sm">
              <span class="text-slate-500 dark:text-slate-400">15m / 1h</span>
              <span>{{ renderSigned(monitorItem.change_15m_pct) }} / {{ renderSigned(monitorItem.change_1h_pct) }}</span>
            </div>
            <div class="flex items-center justify-between gap-4 text-sm">
              <span class="text-slate-500 dark:text-slate-400">{{ t('binanceMarket.columns.distanceFromHigh') }}</span>
              <span :class="renderValueTone(monitorItem.pullback_from_high_pct, false)">{{ renderSigned(monitorItem.pullback_from_high_pct) }}</span>
            </div>
            <div class="flex items-center justify-between gap-4 text-sm">
              <span class="text-slate-500 dark:text-slate-400">{{ t('binanceMarket.columns.ema20Gap') }}</span>
              <span>{{ renderSigned(monitorItem.ema20_gap_15m_pct) }} / {{ renderSigned(monitorItem.ema20_gap_1h_pct) }}</span>
            </div>
            <div class="flex items-center justify-between gap-4 text-sm">
              <span class="text-slate-500 dark:text-slate-400">RSI</span>
              <span>{{ renderSigned(monitorItem.rsi_15m, 1, '', false) }} / {{ renderSigned(monitorItem.rsi_1h, 1, '', false) }}</span>
            </div>
            <div class="flex items-center justify-between gap-4 text-sm" v-if="monitorItem.funding_rate_pct !== null && monitorItem.funding_rate_pct !== undefined">
              <span class="text-slate-500 dark:text-slate-400">{{ t('binanceMarket.columns.funding') }}</span>
              <span :class="renderValueTone(monitorItem.funding_rate_pct)">{{ renderSigned(monitorItem.funding_rate_pct, 3) }}</span>
            </div>
          </div>

          <div v-if="monitorItem" class="mt-5">
            <h5 class="text-sm font-semibold text-slate-900 dark:text-white">{{ t('binanceMarket.columns.basis') }}</h5>
            <div class="mt-3 flex flex-wrap gap-2">
              <span
                v-for="reason in monitorItem.reasons || []"
                :key="reason"
                class="border border-[#b8d2c4] bg-[#edf3ee] px-3 py-1.5 text-sm text-[#0f6b4f] dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
              >
                {{ renderReason(reason) }}
              </span>
            </div>
          </div>

          <div v-if="contractDetailLoading" class="mt-5 border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-400">
            {{ t('binanceMarket.contractDetail.loading') }}
          </div>
          <div v-else-if="contractDetailError" class="mt-5 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
            {{ contractDetailError }}
          </div>

          <section v-if="contractDetail" class="mt-5 space-y-4">
            <div>
              <h4 class="text-lg font-semibold text-slate-900 dark:text-white">{{ t('binanceMarket.contractDetail.title') }}</h4>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
                <div class="text-xs uppercase tracking-[0.18em] text-slate-400">{{ t('binanceMarket.columns.oi') }}</div>
                <div class="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{{ renderCompact(latestOpenInterest?.sum_open_interest_value) }}</div>
              </div>
              <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
                <div class="text-xs uppercase tracking-[0.18em] text-slate-400">{{ t('binanceMarket.columns.oi24h') }}</div>
                <div class="mt-2 text-lg font-semibold" :class="renderValueTone(openInterestChange24h)">{{ renderSigned(openInterestChange24h) }}</div>
              </div>
              <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
                <div class="text-xs uppercase tracking-[0.18em] text-slate-400">{{ t('binanceMarket.columns.takerBuySell') }}</div>
                <div class="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{{ renderSigned(latestTakerVolume?.buy_sell_ratio, 2, '', false) }}</div>
              </div>
              <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
                <div class="text-xs uppercase tracking-[0.18em] text-slate-400">{{ t('binanceMarket.columns.basisPremium') }}</div>
                <div class="mt-2 text-lg font-semibold" :class="renderValueTone(latestBasisRatePct)">{{ renderSigned(latestBasisRatePct, 3) }}</div>
              </div>
            </div>

            <div class="space-y-2 border border-[#e4ded3] bg-white p-4 text-stone-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white">
              <div class="flex items-center justify-between gap-4 text-sm">
                <span class="text-slate-500 dark:text-slate-400">{{ t('binanceMarket.columns.globalLongShort') }}</span>
                <span>{{ renderSigned(latestLongShort?.long_short_ratio, 2, '', false) }}</span>
              </div>
              <div class="flex items-center justify-between gap-4 text-sm">
                <span class="text-slate-500 dark:text-slate-400">{{ t('binanceMarket.columns.topTraderAccounts') }}</span>
                <span>{{ renderSigned(latestTopAccounts?.long_short_ratio, 2, '', false) }}</span>
              </div>
              <div class="flex items-center justify-between gap-4 text-sm">
                <span class="text-slate-500 dark:text-slate-400">{{ t('binanceMarket.columns.topTraderPositions') }}</span>
                <span>{{ renderSigned(latestTopPositions?.long_short_ratio, 2, '', false) }}</span>
              </div>
              <div class="flex items-center justify-between gap-4 text-sm">
                <span class="text-slate-500 dark:text-slate-400">{{ t('binanceMarket.columns.liquidations') }}</span>
                <span>{{ renderCompact(forceOrderQuoteSum) }}</span>
              </div>
            </div>

            <div class="space-y-3">
              <MiniSeries :title="t('binanceMarket.contractDetail.openInterest')" :rows="openInterestRows" value-key="sum_open_interest_value" :format-value="renderCompact" />
              <MiniSeries :title="t('binanceMarket.contractDetail.takerVolume')" :rows="takerVolumeRows" value-key="buy_sell_ratio" :format-value="formatRatioValue" />
              <MiniSeries :title="t('binanceMarket.contractDetail.basis')" :rows="basisRows" value-key="basis_rate" :format-value="formatRateValue" />
              <MiniSeries :title="t('binanceMarket.contractDetail.liquidations')" :rows="forceOrderRows" value-key="cum_quote" :format-value="renderCompact" />
            </div>
          </section>
        </aside>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/24/outline'
import AddToResearchButton from '@/components/research/AddToResearchButton.vue'
import TradingViewChart from '@/components/TradingViewChart.vue'
import type { TradingViewChartColors } from '@/components/useTradingViewChart'
import { useModalDialog } from '@/composables/useModalDialog'
import type { BinanceBreakoutMonitorItem, BinanceContractResearchDetail, CandlestickData, VolumeData } from '@/modules/market/contracts'
import { computed, defineComponent, h, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { percentChange } from '@/utils/number'

const { t } = useI18n()

const props = defineProps<{
  open: boolean
  marketLabel: string
  title: string
  symbol: string
  timeframe: string
  timeframes: string[]
  chartColors: TradingViewChartColors
  chartData: CandlestickData[]
  volumeData: VolumeData[]
  loadingMore: boolean
  chartError?: string
  contractDetail?: BinanceContractResearchDetail | null
  contractDetailLoading?: boolean
  contractDetailError?: string
  monitorItem?: BinanceBreakoutMonitorItem | null
  formatScore?: (value: number | null | undefined) => string
  formatSigned?: (value: number | null | undefined, digits?: number, suffix?: string, withSign?: boolean) => string
  formatCompact?: (value: number | null | undefined) => string
  valueTone?: (value: number | null | undefined, positiveIsGood?: boolean) => string
  verdictTone?: (verdict: string | null | undefined) => string
  formatVerdict?: (verdict: string | null | undefined) => string
  formatFollowStatus?: (status: string | null | undefined) => string
  formatReason?: (reason: string | null | undefined) => string
}>()

const emit = defineEmits<{
  close: []
  loadMore: []
  retryChart: []
  'update:timeframe': [timeframe: string]
}>()

const { dialogRef } = useModalDialog(toRef(props, 'open'), () => emit('close'))

const renderScore = (value: number | null | undefined) => props.formatScore?.(value) ?? '--'
const renderSigned = (value: number | null | undefined, digits = 2, suffix = '%', withSign = true) => (
  props.formatSigned?.(value, digits, suffix, withSign) ?? '--'
)
const renderCompact = (value: number | null | undefined) => props.formatCompact?.(value) ?? '--'
const renderValueTone = (value: number | null | undefined, positiveIsGood = true) => (
  props.valueTone?.(value, positiveIsGood) ?? 'text-slate-500 dark:text-slate-400'
)
const renderVerdictTone = (value: string | null | undefined) => (
  props.verdictTone?.(value) ?? 'bg-stone-100 text-stone-600 ring-stone-300/70 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-600/40'
)
const renderVerdict = (value: string | null | undefined) => props.formatVerdict?.(value) ?? value ?? '--'
const renderFollowStatus = (value: string | null | undefined) => props.formatFollowStatus?.(value) ?? value ?? '--'
const renderReason = (value: string | null | undefined) => props.formatReason?.(value) ?? value ?? '--'

const hasSidePanel = computed(() => Boolean(props.monitorItem || props.contractDetail || props.contractDetailLoading || props.contractDetailError))
const openInterestRows = computed(() => props.contractDetail?.open_interest.items?.slice(-6).reverse() || [])
const takerVolumeRows = computed(() => props.contractDetail?.taker_volume.items?.slice(-6).reverse() || [])
const basisRows = computed(() => props.contractDetail?.basis.items?.slice(-6).reverse() || [])
const forceOrderRows = computed(() => props.contractDetail?.force_orders.items?.slice(-6).reverse() || [])
const lastItem = <T>(items: T[] | null | undefined): T | null => (
  items?.length ? items[items.length - 1] : null
)
const latestOpenInterest = computed(() => lastItem(props.contractDetail?.open_interest.items))
const latestTakerVolume = computed(() => lastItem(props.contractDetail?.taker_volume.items))
const latestBasis = computed(() => lastItem(props.contractDetail?.basis.items))
const latestLongShort = computed(() => lastItem(props.contractDetail?.long_short_ratio.items))
const latestTopAccounts = computed(() => lastItem(props.contractDetail?.top_trader_accounts.items))
const latestTopPositions = computed(() => lastItem(props.contractDetail?.top_trader_positions.items))
const latestBasisRatePct = computed(() => (
  latestBasis.value?.basis_rate === null || latestBasis.value?.basis_rate === undefined
    ? null
    : latestBasis.value.basis_rate * 100
))
const openInterestChange24h = computed(() => {
  const items = props.contractDetail?.open_interest.items || []
  if (items.length <= 24) return null
  const current = Number(items[items.length - 1]?.sum_open_interest)
  const previous = Number(items[items.length - 25]?.sum_open_interest)
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) return null
  return percentChange(current, previous)
})
const forceOrderQuoteSum = computed(() => (
  (props.contractDetail?.force_orders.items || []).reduce((sum, item) => sum + (Number(item.cum_quote) || 0), 0)
))

const formatRatioValue = (value: number | null | undefined) => renderSigned(value, 2, '', false)
const formatRateValue = (value: number | null | undefined) => (
  value === null || value === undefined ? '--' : renderSigned(Number(value) * 100, 3)
)

const MiniSeries = defineComponent({
  props: {
    title: { type: String, required: true },
    rows: { type: Array, required: true },
    valueKey: { type: String, required: true },
    formatValue: { type: Function, required: true },
  },
  setup(seriesProps) {
    const formatTime = (row: Record<string, unknown>) => {
      const raw = row.timestamp ?? row.time ?? row.update_time
      const timestamp = Number(raw)
      if (!Number.isFinite(timestamp) || timestamp <= 0) return '--'
      return new Intl.DateTimeFormat(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(timestamp))
    }
    return () => h('section', { class: 'border border-[#e4ded3] bg-[#fbfaf7] p-4 dark:border-slate-700 dark:bg-slate-900/70' }, [
      h('h5', { class: 'text-sm font-semibold text-slate-900 dark:text-white' }, seriesProps.title),
      h('div', { class: 'mt-3 space-y-2' }, (seriesProps.rows as Record<string, unknown>[]).length
        ? (seriesProps.rows as Record<string, unknown>[]).map((row, index) => h('div', { key: index, class: 'flex items-center justify-between gap-3 text-sm' }, [
          h('span', { class: 'text-slate-500 dark:text-slate-400' }, formatTime(row)),
          h('span', { class: 'font-medium text-slate-900 dark:text-white' }, String(seriesProps.formatValue(row[seriesProps.valueKey] as number | null | undefined))),
        ]))
        : [h('div', { class: 'text-sm text-slate-400 dark:text-slate-500' }, '--')]),
    ])
  },
})
</script>
