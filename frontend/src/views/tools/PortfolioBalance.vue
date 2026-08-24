<template>
  <div class="app-page">
    <div class="app-page-inner-wide">
      <div class="grid gap-6 xl:grid-cols-[20rem_minmax(0,1fr)]">
        <PortfolioBalanceSidebar
          :portfolios="portfolios"
          :deleted-portfolios="deletedPortfolios"
          :has-more-deleted-portfolios="hasMoreDeletedPortfolios"
          :active-portfolio-id="activePortfolioId"
          :plan="plan"
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

        <main v-if="storageReady && !storageLoading && activePortfolio" class="min-w-0 space-y-6">
          <PortfolioBalanceSetup
            :active-portfolio="activePortfolio"
            :tracking="tracking"
            :strategy="strategy"
            :plan="plan"
            :market-loading="marketLoading"
            :source-message="sourceMessage"
            :source-error="sourceError"
            @update-name="activePortfolio.name = $event"
            @update-inception-date="tracking.inceptionDate = $event"
            @refresh-prices="refreshMarketPrices"
            @add-asset="addAsset"
            @update-review-frequency="strategy.reviewFrequency = $event"
            @update-tracking-capital="tracking.virtualCapital = $event"
            @update-rebalance-band="strategy.rebalanceBand = $event"
            @update-min-trade-amount="strategy.minTradeAmount = $event"
          />
          <PortfolioAssetsTable
            :assets="assets"
            :plan="plan"
            :can-remove-asset="canRemoveAsset"
            @update-symbol="updateAssetSymbol"
            @update-weight="updateAssetTargetWeight"
            @remove="removeAsset"
          />
          <PortfolioSimulationPanel
            :simulation="simulation"
            :result="simulationResult"
            :loading="simulationLoading"
            :today="today"
            @run="runSimulation"
            @update-start-date="simulation.simulationStartDate = $event"
            @update-initial-capital="simulation.initialCapital = $event"
          />
        </main>
        <section v-else-if="storageReady && !storageLoading" class="app-panel flex min-h-[24rem] min-w-0 items-center justify-center p-8 text-center">
          <div class="max-w-lg">
            <h2 class="app-section-title text-xl">{{ $t('portfolioBalance.emptyTitle') }}</h2>
            <p class="app-muted mt-3 text-sm leading-6">{{ $t('portfolioBalance.emptyDescription') }}</p>
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
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import PortfolioAssetsTable from '@/components/portfolio/PortfolioAssetsTable.vue'
import PortfolioBalanceSetup from '@/components/portfolio/PortfolioBalanceSetup.vue'
import PortfolioBalanceSidebar from '@/components/portfolio/PortfolioBalanceSidebar.vue'
import PortfolioSimulationPanel from '@/components/portfolio/PortfolioSimulationPanel.vue'
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
  refreshMarketPrices,
  runSimulation,
  importPortfolioDocument,
  exportPortfolioDocument,
  reloadPortfolios,
  loadMoreDeletedPortfolios,
} = usePortfolioBalancePage()
const { t } = useI18n()
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
    anchor.download = `heimdall-portfolios-${todayLocalIsoDate()}.json`
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
