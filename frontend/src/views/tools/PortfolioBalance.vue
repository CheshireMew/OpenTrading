<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <header class="app-workspace-header"><h1 class="app-title">{{ t('portfolioBalance.title') }}</h1></header>
      <div class="space-y-5">
        <PortfolioBalanceSidebar
          :portfolios="portfolios"
          :deleted-portfolios="deletedPortfolios"
          :has-more-deleted-portfolios="hasMoreDeletedPortfolios"
          :active-portfolio-id="activePortfolioId"
          :plan="plan"
          :show-strategy="activeSection === 'allocation' && hasHoldings"
          :storage-ready="storageReady"
          :storage-loading="storageLoading"
          :storage-saving="storageSaving"
          :storage-error="storageError"
          :portfolio-file-error="portfolioFileError"
          @create="handleCreatePortfolio"
          @export="exportBackup"
          @import-file="importBackup"
          @reload="reloadPortfolios"
          @select="selectPortfolio"
          @copy="handleCopyPortfolio"
          @delete="confirmDeletePortfolio"
          @restore="handleRestorePortfolio"
          @load-more-deleted="handleLoadMoreDeletedPortfolios"
        />

        <div v-if="storageReady && !storageLoading && !portfolioTransitioning && activePortfolio" class="min-w-0 space-y-6">
          <div v-if="sourceMessage || sourceError" :role="sourceError ? 'alert' : 'status'" class="app-inline-note" :class="sourceError ? 'text-amber-800 dark:text-amber-200' : ''">{{ sourceError || sourceMessage }}</div>
          <AppTabs id="portfolio" v-model="activeSection" :label="t('portfolioBalance.title')" :tabs="portfolioTabs" />
          <div v-show="activeSection === 'overview'" id="portfolio-panel-overview" role="tabpanel" aria-labelledby="portfolio-tab-overview" tabindex="0"><PortfolioOverview v-if="activeSection === 'overview'" :plan="plan" :ledger="ledgerSnapshot" :ledger-state="ledgerState" @navigate="activeSection = $event" /></div>
          <div v-show="activeSection === 'allocation'" id="portfolio-panel-allocation" role="tabpanel" aria-labelledby="portfolio-tab-allocation" tabindex="0" class="space-y-5">
            <div v-if="!hasHoldings" class="app-inline-note flex flex-wrap items-center justify-between gap-3"><span>{{ t('ui.portfolioPlanHint') }}</span><button type="button" class="font-semibold underline underline-offset-4" @click="activeSection = 'ledger'">{{ t('ui.ledgerTab') }}</button></div>
            <PortfolioAssetsTable
            :assets="assets"
            :plan="plan"
            :holdings-source="activePortfolio.holdingsSource"
            :can-remove-asset="canRemoveAsset"
            :market-loading="marketLoading"
            @add="addAsset"
            @refresh="refreshMarketPrices"
            @update-symbol="updateAssetSymbol"
            @update-weight="updateAssetTargetWeight"
            @remove="removeAsset"
          />
            <PortfolioBalanceSetup
            :active-portfolio="activePortfolio"
            :tracking="tracking"
            :strategy="strategy"
            :plan="plan"
            @update-name="activePortfolio.name = $event"
            @update-inception-date="tracking.inceptionDate = $event"
            @update-review-frequency="strategy.reviewFrequency = $event"
            @update-tracking-capital="tracking.virtualCapital = $event"
            @update-rebalance-band="strategy.rebalanceBand = $event"
            @update-min-trade-amount="strategy.minTradeAmount = $event"
          />
          </div>
          <div v-show="activeSection === 'ledger'" id="portfolio-panel-ledger" role="tabpanel" aria-labelledby="portfolio-tab-ledger" tabindex="0"><PortfolioLedgerPanel
            :portfolio-id="activePortfolio.id"
            :price-refresh-key="activePortfolio.lastPriceUpdatedAt"
            @ledger-updated="onLedgerUpdated" @load-state="ledgerState = $event"
          /></div>
          <div v-show="activeSection === 'simulation'" id="portfolio-panel-simulation" role="tabpanel" aria-labelledby="portfolio-tab-simulation" tabindex="0"><PortfolioSimulationPanel
            :simulation="simulation"
            :result="simulationResult"
            :loading="simulationLoading"
            :today="today"
            @run="runSimulation"
            @update-start-date="simulation.simulationStartDate = $event"
            @update-initial-capital="simulation.initialCapital = $event"
          /></div>
          <div v-show="activeSection === 'risk'" id="portfolio-panel-risk" role="tabpanel" aria-labelledby="portfolio-tab-risk" tabindex="0"><PortfolioRiskPanel v-if="visitedRisk" :portfolio-id="activePortfolio.id" :refresh-key="activePortfolio.lastPriceUpdatedAt" /></div>
        </div>
        <section v-else-if="storageReady && !storageLoading && portfolioTransitioning" role="status" aria-live="polite" class="app-panel flex min-h-[24rem] min-w-0 items-center justify-center p-8 text-center">
          <div class="max-w-lg">
            <h2 class="app-section-title text-xl">{{ $t('portfolioBalance.preparingTitle') }}</h2>
          </div>
        </section>
        <section v-else-if="storageReady && !storageLoading" class="app-panel flex min-h-[24rem] min-w-0 items-center justify-center p-8 text-center">
          <div class="max-w-lg">
            <h2 class="app-section-title text-xl">{{ $t('portfolioBalance.emptyTitle') }}</h2>
            <div class="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
              <button type="button" class="app-button-primary px-5 py-3" :disabled="storageSaving" @click="handleCreatePortfolio">{{ $t('portfolioBalance.createBlank') }}</button>
              <button type="button" class="app-button-secondary px-5 py-3" :disabled="storageSaving" @click="handleCreateSamplePortfolio">{{ $t('portfolioBalance.useSample') }}</button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import PortfolioOverview from '@/components/portfolio/PortfolioOverview.vue'
import AppTabs from '@/components/AppTabs.vue'
import { useI18n } from 'vue-i18n'
import PortfolioAssetsTable from '@/components/portfolio/PortfolioAssetsTable.vue'
import PortfolioBalanceSetup from '@/components/portfolio/PortfolioBalanceSetup.vue'
import PortfolioBalanceSidebar from '@/components/portfolio/PortfolioBalanceSidebar.vue'
import PortfolioSimulationPanel from '@/components/portfolio/PortfolioSimulationPanel.vue'
import PortfolioLedgerPanel from '@/components/portfolio/PortfolioLedgerPanel.vue'
import PortfolioRiskPanel from '@/components/portfolio/PortfolioRiskPanel.vue'
import { usePortfolioBalancePage } from '@/modules/tools'
import { parsePortfolioImportFile } from '@/modules/tools/portfolioBalance'
import { useSymbolCatalog } from '@/modules/market'
import { apiErrorMessage } from '@/api/request'
import { todayLocalIsoDate } from '@/utils/localDate'

const {
  portfolios,
  deletedPortfolios,
  hasMoreDeletedPortfolios,
  activePortfolioId,
  activePortfolio,
  assets,
  strategy,
  tracking,
  simulation,
  plan,
  canRemoveAsset,
  marketLoading,
  simulationLoading,
  sourceMessage,
  sourceError,
  storageReady,
  portfolioTransitioning,
  storageLoading,
  storageSaving,
  storageError,
  simulationResult,
  selectPortfolio,
  createPortfolio,
  createSamplePortfolio,
  copyPortfolio,
  deletePortfolio,
  restorePortfolio,
  addAsset,
  removeAsset,
  updateAssetSymbol,
  updateAssetTargetWeight,
  applyPortfolioLedger,
  refreshMarketPrices,
  runSimulation,
  importPortfolioDocument,
  exportPortfolioDocument,
  reloadPortfolios,
  loadMoreDeletedPortfolios,
} = usePortfolioBalancePage()
const { t } = useI18n()
const activeSection = ref('overview')
const ledgerSnapshot = ref(null)
const ledgerState = ref({ loading: true, error: '' })
const onLedgerUpdated = ledger => { if (ledger.portfolioId !== activePortfolioId.value) return; ledgerSnapshot.value = ledger; applyPortfolioLedger(ledger) }
watch(activePortfolioId, () => { ledgerSnapshot.value = null; ledgerState.value = { loading: true, error: '' } })
const visitedRisk = ref(false)
const hasHoldings = computed(() => assets.value.some(asset => Number(asset.units) > 0))
const portfolioTabs = computed(() => [
  { id: 'overview', label: t('workspaceViews.overview') },
  { id: 'allocation', label: t('ui.allocationTab') },
  { id: 'ledger', label: t('ui.ledgerTab') },
  { id: 'simulation', label: t('ui.historicalSimulation') },
  { id: 'risk', label: t('ui.riskTab') },
])
watch(activeSection, section => { if (section === 'risk') visitedRisk.value = true })
const { loadSymbols } = useSymbolCatalog()
const today = todayLocalIsoDate()
const portfolioFileError = ref('')
const runPortfolioAction = async (action) => {
  try {
    await action()
  } catch {
    // The persistence layer has already populated storageError for inline recovery.
  }
}
const handleCreatePortfolio = () => runPortfolioAction(createPortfolio)
const handleCreateSamplePortfolio = () => runPortfolioAction(createSamplePortfolio)
const handleCopyPortfolio = (portfolioId) => runPortfolioAction(() => copyPortfolio(portfolioId))
const handleRestorePortfolio = (portfolioId) => runPortfolioAction(() => restorePortfolio(portfolioId))
const handleLoadMoreDeletedPortfolios = () => runPortfolioAction(loadMoreDeletedPortfolios)
const confirmDeletePortfolio = async (portfolioId) => {
  const portfolio = portfolios.find((item) => item.id === portfolioId)
  if (!portfolio || !window.confirm(t('portfolioBalance.confirmDelete', { name: portfolio.name }))) return
  await runPortfolioAction(() => deletePortfolio(portfolioId))
}
const exportBackup = async () => {
  portfolioFileError.value = ''
  try {
    const document = await exportPortfolioDocument()
    const blob = new Blob([JSON.stringify(document, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = window.document.createElement('a')
    anchor.href = url
    anchor.download = `opentrading-portfolios-${todayLocalIsoDate()}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    portfolioFileError.value = apiErrorMessage(error, t('portfolioBalance.exportFailed'))
  }
}
const importBackup = async (file) => {
  portfolioFileError.value = ''
  try {
    const document = await parsePortfolioImportFile(file)
    await importPortfolioDocument(document, 'merge')
  } catch (error) {
    portfolioFileError.value = apiErrorMessage(error, t('portfolioBalance.importFailed'))
  }
}

onMounted(loadSymbols)
</script>

<style scoped>
[role=tabpanel]:focus { outline: none; }
</style>
