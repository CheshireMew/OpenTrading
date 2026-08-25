<template>
  <div class="app-page">
    <div class="app-page-inner-wide flex min-h-full flex-col">
    <div class="dashboard-workspace app-panel flex flex-1 flex-col overflow-hidden transition-colors">
      <aside class="dashboard-sidebar w-full border-b border-stone-200 bg-white transition-colors dark:border-gray-700 dark:bg-gray-900">
        <div class="border-b border-stone-200 p-4 dark:border-gray-700">
          <div class="app-section-title">{{ $t('dashboard.tradeSetup') }}</div>
        </div>

        <div class="space-y-4 p-4">
          <div class="grid grid-cols-2 gap-3">
            <label class="space-y-1">
              <span class="text-xs text-stone-500 dark:text-gray-400">{{ $t('dashboard.initialMargin') }} ({{ page.displayCurrency }})</span>
              <input
                v-model.number="page.displayAccountSize"
                class="app-control w-full"
                type="number"
                min="0"
              />
            </label>
            <label class="space-y-1">
              <span class="text-xs text-stone-500 dark:text-gray-400">{{ $t('dashboard.style') }}</span>
            <select
              v-model="page.tradeStyle"
              class="app-control w-full"
            >
                <option>Scalping</option>
                <option>Intraday</option>
                <option>Swing</option>
              </select>
            </label>
          </div>

          <label class="block space-y-1">
            <span class="text-xs text-stone-500 dark:text-gray-400">{{ $t('dashboard.decisionMode') }}</span>
            <select
              v-model="page.decisionMode"
              class="app-control w-full"
            >
              <option value="rules">{{ $t('dashboard.builtInRules') }}</option>
              <option value="ai">{{ $t('dashboard.aiDecision') }}</option>
            </select>
          </label>

          <label class="block space-y-1">
            <span class="text-xs text-stone-500 dark:text-gray-400">{{ $t('dashboard.strategy') }}</span>
            <select
              v-model="page.tradeStrategy"
              class="app-control w-full"
            >
              <option value="最大收益">{{ $t('dashboard.strategies.maxReturn') }}</option>
              <option value="稳健突破">{{ $t('dashboard.strategies.steadyBreakout') }}</option>
              <option value="回撤反转">{{ $t('dashboard.strategies.pullbackReversal') }}</option>
            </select>
          </label>

          <button
            type="button"
            class="app-button-primary app-touch-target w-full px-4 py-3"
            :disabled="page.tradeSetupLoading || !page.canAskTradeSetup"
            @click="page.askTradeSetup"
          >
            {{ page.tradeSetupLoading ? $t('dashboard.analyzing') : page.canAskTradeSetup ? $t('dashboard.askDirection') : $t('dashboard.unsupported') }}
          </button>

          <div v-if="page.tradeSetupResult" class="border border-stone-200 bg-[#fbfaf7] p-4 dark:border-gray-700 dark:bg-gray-800">
            <template v-if="page.tradeSetupResult.setup">
              <div class="flex items-center justify-between">
                <span :class="['text-sm font-semibold', page.tradeSetupResult.setup.side === 'long' ? 'text-emerald-600' : 'text-rose-600']">
                  {{ page.tradeSetupResult.setup.side === 'long' ? $t('dashboard.long') : $t('dashboard.short') }}
                </span>
                <span class="text-xs text-gray-500 dark:text-gray-400">
                  {{ page.tradeSetupResult.setup.source === 'ai' ? 'AI' : $t('dashboard.rules') }} {{ page.tradeSetupResult.setup.confidence }}%
                </span>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-2 text-sm">
                <div class="text-gray-500 dark:text-gray-400">{{ $t('dashboard.entry') }}</div>
                <div class="text-right font-semibold text-gray-900 dark:text-white">{{ page.formatTradePrice(page.tradeSetupResult.setup.entry) }}</div>
                <div class="text-gray-500 dark:text-gray-400">{{ $t('dashboard.target') }}</div>
                <div class="text-right font-semibold text-emerald-600">{{ page.formatTradePrice(page.tradeSetupResult.setup.target) }}</div>
                <div class="text-gray-500 dark:text-gray-400">{{ $t('dashboard.stop') }}</div>
                <div class="text-right font-semibold text-rose-600">{{ page.formatTradePrice(page.tradeSetupResult.setup.stop) }}</div>
                <div class="text-gray-500 dark:text-gray-400">{{ $t('dashboard.riskReward') }}</div>
                <div class="text-right font-semibold text-gray-900 dark:text-white">{{ page.tradeSetupResult.setup.risk_reward.toFixed(2) }}</div>
              </div>
            </template>
            <div v-else class="text-sm text-gray-600 dark:text-gray-300">
              <p>{{ page.tradeSetupMessage }}</p>
              <router-link v-if="page.tradeSetupNeedsConfiguration" to="/settings" class="mt-2 inline-block font-semibold text-[#0f6b4f] underline dark:text-emerald-300">{{ $t('dashboard.openSettings') }}</router-link>
            </div>
          </div>

          <div v-if="page.tradeSetupError" role="alert" class="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
            {{ page.tradeSetupError }}
          </div>
        </div>
      </aside>

      <div class="flex min-w-0 flex-1 flex-col">
      <div class="flex items-center justify-between border-b border-stone-200 bg-[#fbfaf7] p-4 transition-colors dark:border-gray-700 dark:bg-gray-800/50">
         <div class="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-center">
            <SymbolSearchBox
              v-model="page.currentSymbol"
              class="w-full sm:w-72"
              @select="page.handleSymbolSelect"
            />
            <AddToResearchButton
              :symbol="page.currentSymbol"
              asset-class="crypto"
              :display-name="page.currentSymbol"
              :source-context="{ route: '/', timeframe: page.currentTimeframe }"
            />
            <div class="flex max-w-full space-x-1 overflow-x-auto border border-stone-200 bg-white p-1 transition-colors dark:border-gray-700 dark:bg-gray-900">
                <button v-for="tf in page.visibleTimeframes" :key="tf" type="button"
                    @click="page.currentTimeframe = tf"
                    :class="['app-touch-target px-3 py-1 text-xs transition-all', page.currentTimeframe === tf ? 'bg-[#edf3ee] text-[#0f6b4f] dark:bg-emerald-500 dark:text-slate-950' : 'text-stone-500 hover:bg-stone-100 hover:text-stone-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200']">
                    {{ tf }}
                </button>
            </div>
         </div>
      </div>

      <div class="dashboard-chart relative h-[420px] flex-none">
         <div v-if="page.klineLoadError" role="alert" class="absolute left-1/2 top-4 z-20 flex -translate-x-1/2 items-center gap-3 border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700 shadow-lg dark:border-rose-500/30 dark:bg-rose-950/90 dark:text-rose-200">
            <span>{{ $t('dashboard.historyLoadFailed') }}</span>
            <button type="button" class="font-semibold underline" @click="page.retryKline">{{ $t('app.retry') }}</button>
         </div>
         <div v-if="page.loadingMore" class="absolute left-1/2 top-4 z-20 flex -translate-x-1/2 transform items-center bg-[#0f6b4f] px-3 py-1 text-xs text-white shadow-lg">
            <span class="animate-spin mr-2">&#10227;</span> {{ $t('dashboard.loadingHistory') }}
         </div>
         <TradingViewChart
            :data="page.chartData"
            :volume-data="page.volumeData"
            :colors="page.chartColors"
            :trade-setup="page.activeTradeSetup"
            @load-more="page.loadMore"
         />
      </div>
      </div>
    </div>
    </div>
  </div>
</template>

<script setup>
defineOptions({ name: 'Dashboard' })

import TradingViewChart from '@/components/TradingViewChart.vue'
import SymbolSearchBox from '@/components/SymbolSearchBox.vue'
import AddToResearchButton from '@/components/research/AddToResearchButton.vue'
import { useDashboardPage } from '@/modules/market'

const page = useDashboardPage()

</script>
