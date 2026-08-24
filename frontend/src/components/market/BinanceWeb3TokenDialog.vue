<template>
  <div
    v-if="open && token"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-2 backdrop-blur-sm sm:p-4"
    @click.self="$emit('close')"
  >
    <section
      ref="dialogRef"
      role="dialog"
      aria-modal="true"
      aria-labelledby="web3-token-dialog-title"
      tabindex="-1"
      class="flex h-[min(90vh,860px)] w-full max-w-7xl flex-col overflow-hidden border border-[#d8d1c5] bg-[#fbfaf7] shadow-2xl outline-none dark:border-slate-700 dark:bg-slate-800"
    >
      <header class="flex flex-wrap items-center justify-between gap-3 border-b border-[#e4ded3] px-4 py-4 dark:border-slate-700 sm:px-6 sm:py-5">
        <div class="flex min-w-0 flex-1 items-center gap-3 sm:gap-4">
          <Web3TokenIcon :src="token.icon_url" :symbol="token.symbol" size="lg" />
          <div class="min-w-0">
            <div class="flex items-center gap-3">
              <h3 id="web3-token-dialog-title" class="text-2xl font-semibold text-slate-900 dark:text-white">{{ token.symbol || '--' }}</h3>
              <span class="border border-[#b8d2c4] bg-[#edf3ee] px-3 py-1 text-xs font-semibold text-[#0f6b4f] dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">{{ t('web3Rank.dialog.score') }} {{ formatScore(token.heat_score) }}</span>
            </div>
            <p class="mt-2 break-all text-xs text-slate-500 dark:text-slate-400 sm:max-w-[680px] sm:truncate sm:text-sm">{{ token.contract_address }}</p>
          </div>
        </div>

        <div class="flex w-full min-w-0 items-center gap-2 sm:w-auto">
          <div class="flex min-w-0 flex-1 gap-2 overflow-x-auto border border-[#e4ded3] bg-white p-1 dark:border-slate-700 dark:bg-slate-900 sm:flex-none">
            <button
              v-for="item in intervals"
              :key="item"
              type="button"
              class="px-4 py-2 text-sm transition"
              :class="interval === item ? 'bg-[#0f6b4f] text-white dark:bg-emerald-600' : 'text-slate-600 hover:bg-[#f1ece3] dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white'"
              @click="$emit('update:interval', item)"
            >
              {{ item }}
            </button>
          </div>
          <button
            type="button"
            class="inline-flex h-10 w-10 flex-none items-center justify-center border border-[#e4ded3] bg-white text-stone-600 transition hover:bg-[#f1ece3] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
            :aria-label="t('web3Rank.dialog.close')"
            :title="t('web3Rank.dialog.close')"
            @click="$emit('close')"
          >
            <XMarkIcon class="h-5 w-5" />
          </button>
        </div>
      </header>

      <div v-if="detailError" class="border-b border-rose-100 bg-rose-50 px-6 py-3 text-sm text-rose-600 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">{{ detailError }}</div>

      <div class="grid min-h-0 flex-1 gap-0 overflow-y-auto lg:grid-cols-[360px_minmax(0,1fr)] lg:overflow-hidden">
        <aside class="border-b border-slate-200 p-5 dark:border-slate-700 lg:overflow-y-auto lg:border-b-0 lg:border-r">
          <div v-if="detailLoading" class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">{{ t('web3Rank.dialog.loading') }}</div>

          <div class="grid grid-cols-2 gap-3">
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs text-slate-400 dark:text-slate-500">{{ t('web3Rank.dialog.price') }}</div>
              <div class="mt-2 font-semibold text-slate-900 dark:text-white">{{ formatPrice(dynamic?.price ?? token.metrics?.price) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs text-slate-400 dark:text-slate-500">24H</div>
              <div class="mt-2 font-semibold" :class="valueTone(dynamic?.percent_change_24h ?? token.metrics?.percent_change_24h)">
                {{ formatSigned(dynamic?.percent_change_24h ?? token.metrics?.percent_change_24h) }}
              </div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs text-slate-400 dark:text-slate-500">{{ t('web3Rank.dialog.marketCap') }}</div>
              <div class="mt-2 font-semibold text-slate-900 dark:text-white">{{ formatCompact(dynamic?.market_cap ?? token.metrics?.market_cap) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs text-slate-400 dark:text-slate-500">{{ t('web3Rank.dialog.liquidity') }}</div>
              <div class="mt-2 font-semibold text-slate-900 dark:text-white">{{ formatCompact(dynamic?.liquidity ?? token.metrics?.liquidity) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs text-slate-400 dark:text-slate-500">{{ t('web3Rank.dialog.volume1h') }}</div>
              <div class="mt-2 font-semibold text-slate-900 dark:text-white">{{ formatCompact(dynamic?.volume_1h ?? token.metrics?.volume_1h) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs text-slate-400 dark:text-slate-500">{{ t('web3Rank.dialog.volume24h') }}</div>
              <div class="mt-2 font-semibold text-slate-900 dark:text-white">{{ formatCompact(dynamic?.volume_24h ?? token.metrics?.volume_24h) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs text-slate-400 dark:text-slate-500">{{ t('web3Rank.dialog.holders') }}</div>
              <div class="mt-2 font-semibold text-slate-900 dark:text-white">{{ formatCompact(dynamic?.holders ?? token.metrics?.holders) }}</div>
            </div>
            <div class="border border-[#e4ded3] bg-[#fbfaf7] px-4 py-3 dark:border-slate-700 dark:bg-slate-900/70">
              <div class="text-xs text-slate-400 dark:text-slate-500">{{ t('web3Rank.dialog.trades') }}</div>
              <div class="mt-2 font-semibold text-slate-900 dark:text-white">{{ formatCompact(dynamic?.count_24h ?? token.metrics?.count_24h) }}</div>
            </div>
          </div>

          <div class="mt-5 border border-[#e4ded3] bg-white p-4 text-sm text-stone-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white">
            <div class="flex items-center justify-between">
              <span class="text-slate-400">{{ t('web3Rank.dialog.topSearch') }}</span>
              <span>{{ token.components?.top_search?.toFixed?.(1) ?? '--' }}</span>
            </div>
            <div class="mt-3 flex items-center justify-between">
              <span class="text-slate-400">{{ t('web3Rank.dialog.trending') }}</span>
              <span>{{ token.components?.trending?.toFixed?.(1) ?? '--' }}</span>
            </div>
            <div class="mt-3 flex items-center justify-between">
              <span class="text-slate-400">{{ t('web3Rank.dialog.social') }}</span>
              <span>{{ token.components?.social_hype?.toFixed?.(1) ?? '--' }}</span>
            </div>
            <div class="mt-3 flex items-center justify-between">
              <span class="text-slate-400">{{ t('web3Rank.dialog.volumeTx') }}</span>
              <span>{{ token.components?.volume_growth?.toFixed?.(1) ?? '--' }} / {{ token.components?.transaction_growth?.toFixed?.(1) ?? '--' }}</span>
            </div>
            <div class="mt-3 flex items-center justify-between">
              <span class="text-slate-400">{{ t('web3Rank.dialog.smartMoney') }}</span>
              <span>{{ formatCompact(token.metrics?.smart_money_inflow) }}</span>
            </div>
            <div class="mt-3 flex items-center justify-between">
              <span class="text-slate-400">{{ t('web3Rank.dialog.meme') }}</span>
              <span>{{ token.ranks?.meme ? `#${token.ranks.meme}` : '--' }}</span>
            </div>
          </div>

          <div class="mt-5 border border-[#e4ded3] p-4 text-sm dark:border-slate-700">
            <div class="flex items-center justify-between">
              <span class="text-slate-500 dark:text-slate-400">{{ t('web3Rank.dialog.sentiment') }}</span>
              <span class="font-semibold text-slate-900 dark:text-white">{{ token.sentiment || '--' }}</span>
            </div>
            <p v-if="token.summary" class="mt-3 text-xs leading-5 text-slate-500 dark:text-slate-400">{{ token.summary }}</p>
            <div class="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div class="border border-[#e4ded3] bg-[#fbfaf7] px-3 py-2 dark:border-slate-700 dark:bg-slate-900/70">
                <div class="text-slate-400">{{ t('web3Rank.dialog.topSearch') }}</div>
                <div class="mt-1 font-semibold text-slate-900 dark:text-white">{{ token.ranks?.top_search ? `#${token.ranks.top_search}` : '--' }}</div>
              </div>
              <div class="border border-[#e4ded3] bg-[#fbfaf7] px-3 py-2 dark:border-slate-700 dark:bg-slate-900/70">
                <div class="text-slate-400">{{ t('web3Rank.dialog.trending') }}</div>
                <div class="mt-1 font-semibold text-slate-900 dark:text-white">{{ token.ranks?.trending ? `#${token.ranks.trending}` : '--' }}</div>
              </div>
              <div class="border border-[#e4ded3] bg-[#fbfaf7] px-3 py-2 dark:border-slate-700 dark:bg-slate-900/70">
                <div class="text-slate-400">{{ t('web3Rank.dialog.socialHype') }}</div>
                <div class="mt-1 font-semibold text-slate-900 dark:text-white">{{ formatCompact(token.metrics?.social_hype) }}</div>
              </div>
              <div class="border border-[#e4ded3] bg-[#fbfaf7] px-3 py-2 dark:border-slate-700 dark:bg-slate-900/70">
                <div class="text-slate-400">{{ t('web3Rank.dialog.memeScore') }}</div>
                <div class="mt-1 font-semibold text-slate-900 dark:text-white">{{ formatCompact(token.metrics?.meme_score) }}</div>
              </div>
            </div>
          </div>

          <div class="mt-5 border border-[#e4ded3] p-4 text-sm dark:border-slate-700">
            <div class="flex items-center justify-between">
              <span class="text-slate-500 dark:text-slate-400">{{ t('web3Rank.dialog.contractRisk') }}</span>
              <span class="font-semibold text-slate-900 dark:text-white">{{ audit?.risk_level_enum || audit?.risk_level || '--' }}</span>
            </div>
            <div class="mt-3 flex items-center justify-between">
              <span class="text-slate-500 dark:text-slate-400">{{ t('web3Rank.dialog.buySellTax') }}</span>
              <span class="font-semibold text-slate-900 dark:text-white">{{ formatSigned(audit?.buy_tax, 2) }} / {{ formatSigned(audit?.sell_tax, 2) }}</span>
            </div>
            <div class="mt-3 flex items-center justify-between">
              <span class="text-slate-500 dark:text-slate-400">{{ t('web3Rank.dialog.contractVerification') }}</span>
              <span class="font-semibold text-slate-900 dark:text-white">{{ audit?.is_verified === true ? t('web3Rank.dialog.verified') : audit?.is_verified === false ? t('web3Rank.dialog.unverified') : '--' }}</span>
            </div>
          </div>
        </aside>

        <main class="min-h-[320px] bg-slate-950 p-4 lg:min-h-0">
          <TradingViewChart
            :data="chartData"
            :volume-data="volumeData"
            :colors="chartColors"
          />
        </main>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/24/outline'
import TradingViewChart from '@/components/TradingViewChart.vue'
import Web3TokenIcon from '@/components/market/Web3TokenIcon.vue'
import { useModalDialog } from '@/composables/useModalDialog'
import { toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  BinanceWeb3HeatRankItem,
  BinanceWeb3TokenAudit,
  BinanceWeb3TokenDynamic,
  CandlestickData,
  VolumeData,
} from '@/modules/market/contracts'

const { t } = useI18n()

const props = defineProps<{
  open: boolean
  token: BinanceWeb3HeatRankItem | null
  interval: string
  intervals: string[]
  detailLoading: boolean
  detailError: string
  dynamic: BinanceWeb3TokenDynamic | null
  audit: BinanceWeb3TokenAudit | null
  chartData: CandlestickData[]
  volumeData: VolumeData[]
  chartColors: Record<string, string>
  formatScore: (value: number | null | undefined) => string
  formatPrice: (value: number | null | undefined) => string
  formatSigned: (value: number | null | undefined, digits?: number, suffix?: string, withSign?: boolean) => string
  formatCompact: (value: number | null | undefined) => string
  valueTone: (value: number | null | undefined, positiveIsGood?: boolean) => string
}>()

const emit = defineEmits<{
  close: []
  'update:interval': [interval: string]
}>()

const { dialogRef } = useModalDialog(toRef(props, 'open'), () => emit('close'))
</script>
