import { toBaseSymbol } from '@/modules/market'

import { buildPortfolioSimulationSummary, portfolioSimulationInputKey } from './simulation'
import { fetchPortfolioPriceMap, loadPortfolioSimulationHistory } from './data'
import {
  applyLatestMarketPrices,
  clearPortfolioHoldings,
  seedPortfolioHoldingsFromMarket,
} from './holdings'
import {
  createPortfolioBalanceAsset,
  readPortfolioSyntheticPrice,
} from './assets'
import { PortfolioDataError, toPortfolioUserError, type PortfolioTranslate } from './errors'
import { copyPortfolioInCollection, createPortfolioInCollection, deletePortfolioFromCollection } from './portfolioCrud'
import type { PortfolioBalancePageState } from './state'
import type { PortfolioPersistence } from './persistence'

export const createPortfolioBalancePageCommands = (
  state: PortfolioBalancePageState,
  t: PortfolioTranslate,
  persistence: PortfolioPersistence,
) => {
  let marketRefreshTimer: ReturnType<typeof setTimeout> | null = null

  const clearScheduledMarketRefresh = () => {
    if (!marketRefreshTimer) return
    clearTimeout(marketRefreshTimer)
    marketRefreshTimer = null
  }

  const refreshMarketPrices = async () => {
    const portfolio = state.activePortfolio.value
    if (!portfolio) return

    state.marketLoading.value = true
    state.resetFeedback()
    try {
      const { priceBySymbol, successCount, failedSymbols } = await fetchPortfolioPriceMap(portfolio)
      const needsSeed = (
        !portfolio.holdingsInitializedAt
        || portfolio.seedCapital !== portfolio.tracking.virtualCapital
        || portfolio.assets.some((asset) => toBaseSymbol(asset.symbol) && asset.units <= 0)
      )
      if (needsSeed) {
        seedPortfolioHoldingsFromMarket(portfolio, priceBySymbol)
        state.sourceMessage.value = failedSymbols.length
          ? t('portfolioBalance.feedback.initializedWithFailures', { count: successCount, symbols: failedSymbols.join(', ') })
          : t('portfolioBalance.feedback.initialized', { count: successCount })
      } else {
        applyLatestMarketPrices(portfolio, priceBySymbol)
        state.sourceMessage.value = failedSymbols.length
          ? t('portfolioBalance.feedback.refreshedWithFailures', { count: successCount, symbols: failedSymbols.join(', ') })
          : t('portfolioBalance.feedback.refreshed', { count: successCount })
      }
    } catch (error: unknown) {
      state.sourceError.value = toPortfolioUserError(error, 'portfolioBalance.feedback.refreshFailed', t)
    } finally {
      state.marketLoading.value = false
    }
  }

  const scheduleMarketRefresh = (delay = 600) => {
    clearScheduledMarketRefresh()
    marketRefreshTimer = setTimeout(async () => {
      marketRefreshTimer = null
      const portfolio = state.activePortfolio.value
      if (!portfolio || state.marketLoading.value) return
      if (!portfolio.assets.some((asset) => toBaseSymbol(asset.symbol))) return
      await refreshMarketPrices()
    }, delay)
  }

  const selectPortfolio = (portfolioId: string) => {
    state.clearSimulationResult()
    state.activePortfolioId.value = portfolioId
    state.resetFeedback()
    void persistence.loadSimulation(portfolioId).catch(() => undefined)
  }

  const createPortfolioFromTemplate = async (sample: boolean) => {
    state.clearSimulationResult()
    state.activePortfolioId.value = createPortfolioInCollection(
      state.portfolios,
      sample
        ? t('portfolioBalance.samplePortfolioName')
        : t('portfolioBalance.defaultPortfolioNumbered', { count: state.portfolios.length + 1 }),
      sample,
    )
    state.sourceMessage.value = t('portfolioBalance.feedback.created')
    state.sourceError.value = ''
    await persistence.saveNow(true)
    await persistence.loadSimulation(state.activePortfolioId.value)
  }
  const createPortfolio = () => createPortfolioFromTemplate(false)
  const createSamplePortfolio = () => createPortfolioFromTemplate(true)

  const copyPortfolio = async (portfolioId: string) => {
    const sourceName = state.portfolios.find((portfolio) => portfolio.id === portfolioId)?.name || t('portfolioBalance.defaultPortfolioName')
    const nextPortfolioId = copyPortfolioInCollection(
      state.portfolios,
      portfolioId,
      t('portfolioBalance.copyName', { name: sourceName }),
    )
    if (!nextPortfolioId) return
    state.clearSimulationResult()
    state.activePortfolioId.value = nextPortfolioId
    state.sourceMessage.value = t('portfolioBalance.feedback.copied')
    state.sourceError.value = ''
    await persistence.saveNow(true)
    await persistence.loadSimulation(state.activePortfolioId.value)
  }

  const deletePortfolio = async (portfolioId: string) => {
    state.clearSimulationResult()
    state.activePortfolioId.value = deletePortfolioFromCollection(
      state.portfolios,
      portfolioId,
      state.activePortfolioId.value,
      t('portfolioBalance.defaultPortfolioName'),
    )
    state.sourceMessage.value = t('portfolioBalance.feedback.deleted')
    state.sourceError.value = ''
    await persistence.saveNow(true)
    await persistence.loadDeleted(true)
    await persistence.loadSimulation(state.activePortfolioId.value)
  }

  const restorePortfolio = async (portfolioId: string) => {
    await persistence.restore(portfolioId)
    state.sourceMessage.value = t('portfolioBalance.feedback.restored')
    state.sourceError.value = ''
  }

  const addAsset = () => state.updateActivePortfolio((portfolio) => {
    portfolio.assets.push(createPortfolioBalanceAsset())
  })

  const removeAsset = (assetId: string) => state.updateActivePortfolio((portfolio) => {
    if (portfolio.assets.length <= 2) return
    const index = portfolio.assets.findIndex((asset) => asset.id === assetId)
    if (index < 0) return

    portfolio.assets.splice(index, 1)
    clearPortfolioHoldings(portfolio, 'virtual')
    scheduleMarketRefresh()
  })

  const updateAssetSymbol = (assetId: string, rawValue: string) => {
    let shouldRefresh = false
    state.updateActivePortfolio((portfolio) => {
      const asset = portfolio.assets.find((item) => item.id === assetId)
      if (!asset) return

      const previousSymbol = toBaseSymbol(asset.symbol)
      const nextSymbol = toBaseSymbol(rawValue)
      if (previousSymbol === nextSymbol) return

      asset.symbol = nextSymbol
      asset.currentPrice = readPortfolioSyntheticPrice(nextSymbol) ?? 0
      asset.units = 0
      if (!nextSymbol) {
        asset.targetWeight = 0
      }

      clearPortfolioHoldings(portfolio, 'virtual')
      shouldRefresh = true
    })

    if (!shouldRefresh) return
    state.resetFeedback()
    scheduleMarketRefresh()
  }

  const updateAssetTargetWeight = (assetId: string, rawValue: string | number) => state.updateActivePortfolio((portfolio) => {
    const asset = portfolio.assets.find((item) => item.id === assetId)
    if (!asset) return

    const nextWeight = Number(rawValue)
    asset.targetWeight = Number.isFinite(nextWeight) && nextWeight > 0 ? nextWeight : 0
    clearPortfolioHoldings(portfolio, 'virtual')
    scheduleMarketRefresh()
  })

  const runSimulation = async () => {
    const portfolio = state.activePortfolio.value
    if (!portfolio) return

    state.simulationLoading.value = true
    state.resetFeedback()
    state.clearSimulationResult(portfolio.id)
    try {
      await persistence.saveNow(true)
      const startText = portfolio.simulation.simulationStartDate
      if (!startText) throw new PortfolioDataError('portfolioBalance.feedback.chooseStartDate')
      const portfolioId = portfolio.id
      const inputKey = portfolioSimulationInputKey(portfolio)

      const historyBySymbol = await loadPortfolioSimulationHistory(portfolio, startText)
      const nextResult = buildPortfolioSimulationSummary(
        historyBySymbol,
        portfolio.assets,
        portfolio.strategy,
        portfolio.simulation,
        startText,
      )
      if (!nextResult) throw new PortfolioDataError('portfolioBalance.feedback.insufficientHistory')
      const currentPortfolio = state.activePortfolio.value
      if (
        !currentPortfolio
        || currentPortfolio.id !== portfolioId
        || portfolioSimulationInputKey(currentPortfolio) !== inputKey
      ) {
        throw new PortfolioDataError('portfolioBalance.feedback.simulationInputsChanged')
      }
      await persistence.saveSimulation(portfolioId, nextResult)
      state.sourceMessage.value = t('portfolioBalance.feedback.simulationCreated', { start: nextResult.startDate, end: nextResult.endDate })
    } catch (error: unknown) {
      state.sourceError.value = toPortfolioUserError(error, 'portfolioBalance.feedback.simulationFailed', t)
    } finally {
      state.simulationLoading.value = false
    }
  }

  return {
    clearScheduledMarketRefresh,
    refreshMarketPrices,
    scheduleMarketRefresh,
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
    runSimulation,
  }
}
