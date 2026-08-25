import { onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { toBaseSymbol } from '@/modules/market'

import { createPortfolioBalancePageCommands } from './commands'
import { createPortfolioBalancePageState } from './state'
import { createPortfolioPersistence } from './persistence'
import { hasMarketGap } from './snapshot'
import { portfolioSimulationInputKey } from './simulation'

export function usePortfolioBalancePage() {
  const { t } = useI18n()
  const defaultPortfolioName = t('portfolioBalance.defaultPortfolioName')
  const state = createPortfolioBalancePageState(defaultPortfolioName)
  const persistence = createPortfolioPersistence(state, defaultPortfolioName)
  const commands = createPortfolioBalancePageCommands(state, t, persistence)

  watch(() => {
    const portfolio = state.activePortfolio.value
    return portfolio ? `${portfolio.id}:${portfolioSimulationInputKey(portfolio)}` : ''
  }, (_next, previous) => {
    if (!previous) return
    state.clearSimulationResult()
  })

  watch([state.portfolios, state.activePortfolioId], () => {
    persistence.queueSave()
  }, { deep: true })

  watch([state.activePortfolioId, state.storageReady], async () => {
    if (!state.storageReady.value) return
    commands.clearScheduledMarketRefresh()
    const portfolio = state.activePortfolio.value
    if (!portfolio) return
    if (!portfolio.assets.some((asset) => toBaseSymbol(asset.symbol))) return
    if (!hasMarketGap(portfolio)) return
    await commands.refreshMarketPrices()
  }, { immediate: true })

  void persistence.initialize()

  onBeforeUnmount(() => {
    commands.clearScheduledMarketRefresh()
    void persistence.stop().catch(() => undefined)
  })

  return {
    portfolios: state.portfolios,
    deletedPortfolios: state.deletedPortfolios,
    hasMoreDeletedPortfolios: state.hasMoreDeletedPortfolios,
    activePortfolioId: state.activePortfolioId,
    activePortfolio: state.activePortfolio,
    assets: state.assets,
    strategy: state.strategy,
    tracking: state.tracking,
    simulation: state.simulation,
    plan: state.plan,
    canRemoveAsset: state.canRemoveAsset,
    marketLoading: state.marketLoading,
    simulationLoading: state.simulationLoading,
    sourceMessage: state.sourceMessage,
    sourceError: state.sourceError,
    storageReady: state.storageReady,
    portfolioTransitioning: state.portfolioTransitioning,
    storageLoading: state.storageLoading,
    storageSaving: state.storageSaving,
    storageError: state.storageError,
    simulationResult: state.simulationResult,
    selectPortfolio: commands.selectPortfolio,
    createPortfolio: commands.createPortfolio,
    createSamplePortfolio: commands.createSamplePortfolio,
    copyPortfolio: commands.copyPortfolio,
    deletePortfolio: commands.deletePortfolio,
    restorePortfolio: commands.restorePortfolio,
    addAsset: commands.addAsset,
    removeAsset: commands.removeAsset,
    updateAssetSymbol: commands.updateAssetSymbol,
    updateAssetTargetWeight: commands.updateAssetTargetWeight,
    applyPortfolioLedger: commands.applyPortfolioLedger,
    refreshMarketPrices: commands.refreshMarketPrices,
    runSimulation: commands.runSimulation,
    importPortfolioDocument: persistence.importDocument,
    exportPortfolioDocument: persistence.exportDocument,
    loadMoreDeletedPortfolios: () => persistence.loadDeleted(false),
    reloadPortfolios: persistence.reload,
  }
}
