import { computed, reactive, ref, shallowRef } from 'vue'

import type { PortfolioSimulationSummary, PortfolioBalancePortfolio } from './types'
import type {
  PortfolioCollectionResponse,
  PortfolioDeletedPage,
  PortfolioDeletedSummary,
} from '../contracts'

import { computePortfolioBalancePlan } from './plan'
import {
  createEmptyPortfolioBalanceSnapshot,
  createPortfolioBalancePortfolio,
  normalizePortfolioBalancePortfolio,
  normalizePortfolioBalanceSnapshot,
  touchPortfolio,
} from './snapshot'

export const createPortfolioBalancePageState = (defaultPortfolioName: string) => {
  const defaultSnapshot = createEmptyPortfolioBalanceSnapshot()
  const fallbackPortfolio = createPortfolioBalancePortfolio()

  const portfolios = reactive(defaultSnapshot.portfolios) as PortfolioBalancePortfolio[]
  const deletedPortfolios = reactive([]) as PortfolioDeletedSummary[]
  const deletedPortfolioTotal = ref(0)
  const activePortfolioId = ref(defaultSnapshot.activePortfolioId || portfolios[0]?.id || '')
  const revision = ref(0)
  const storageLoading = ref(true)
  const storageSaving = ref(false)
  const storageReady = ref(false)
  const storageError = ref('')
  const marketLoading = ref(false)
  const simulationLoading = ref(false)
  const simulationResult = shallowRef<PortfolioSimulationSummary | null>(null)
  const simulationResultPortfolioId = ref('')
  const sourceMessage = ref('')
  const sourceError = ref('')

  const activePortfolio = computed(() => portfolios.find((portfolio) => portfolio.id === activePortfolioId.value) || portfolios[0] || null)
  const assets = computed(() => activePortfolio.value?.assets || [])
  const strategy = computed(() => activePortfolio.value?.strategy || fallbackPortfolio.strategy)
  const tracking = computed(() => activePortfolio.value?.tracking || fallbackPortfolio.tracking)
  const simulation = computed(() => activePortfolio.value?.simulation || fallbackPortfolio.simulation)
  const plan = computed(() => computePortfolioBalancePlan(assets.value, strategy.value, tracking.value))
  const canRemoveAsset = computed(() => assets.value.length > 2)
  const hasMoreDeletedPortfolios = computed(() => deletedPortfolios.length < deletedPortfolioTotal.value)

  const resetFeedback = () => {
    sourceMessage.value = ''
    sourceError.value = ''
  }

  const updateActivePortfolio = (updater: (portfolio: PortfolioBalancePortfolio) => void) => {
    const portfolio = activePortfolio.value
    if (!portfolio) return
    updater(portfolio)
    touchPortfolio(portfolio)
  }

  const replaceSnapshot = (value: unknown) => {
    const snapshot = normalizePortfolioBalanceSnapshot(value, createEmptyPortfolioBalanceSnapshot())
    portfolios.splice(0, portfolios.length, ...snapshot.portfolios)
    activePortfolioId.value = snapshot.activePortfolioId
    if (simulationResultPortfolioId.value !== snapshot.activePortfolioId) {
      simulationResult.value = null
      simulationResultPortfolioId.value = ''
    }
  }

  const applyCollection = (response: PortfolioCollectionResponse) => {
    replaceSnapshot(response.snapshot)
    revision.value = response.revision
  }

  const applySaveMetadata = (response: PortfolioCollectionResponse) => {
    revision.value = response.revision
  }

  const applyDeletedPage = (page: PortfolioDeletedPage, append = false) => {
    const next = append ? [...deletedPortfolios] : []
    const seen = new Set(next.map((portfolio) => portfolio.id))
    for (const portfolio of page.items || []) {
      if (seen.has(portfolio.id)) continue
      next.push(portfolio)
      seen.add(portfolio.id)
    }
    deletedPortfolios.splice(0, deletedPortfolios.length, ...next)
    deletedPortfolioTotal.value = page.total
  }

  const setSimulationResult = (
    portfolioId: string,
    result: PortfolioSimulationSummary | null,
  ) => {
    if (portfolioId !== activePortfolioId.value) return
    simulationResultPortfolioId.value = result ? portfolioId : ''
    simulationResult.value = result
  }

  const clearSimulationResult = (portfolioId = activePortfolioId.value) => {
    if (simulationResultPortfolioId.value !== portfolioId) return
    simulationResultPortfolioId.value = ''
    simulationResult.value = null
  }

  const buildSnapshot = () => ({
    activePortfolioId: activePortfolioId.value,
    portfolios: portfolios.map((portfolio) => normalizePortfolioBalancePortfolio(portfolio)),
  })

  const removeDeletedPortfolio = (portfolioId: string) => {
    const index = deletedPortfolios.findIndex((portfolio) => portfolio.id === portfolioId)
    if (index >= 0) {
      deletedPortfolios.splice(index, 1)
      deletedPortfolioTotal.value = Math.max(0, deletedPortfolioTotal.value - 1)
    }
  }

  return {
    portfolios,
    deletedPortfolios,
    deletedPortfolioTotal,
    hasMoreDeletedPortfolios,
    activePortfolioId,
    revision,
    storageLoading,
    storageSaving,
    storageReady,
    storageError,
    marketLoading,
    simulationLoading,
    sourceMessage,
    sourceError,
    activePortfolio,
    assets,
    strategy,
    tracking,
    simulation,
    simulationResult,
    plan,
    canRemoveAsset,
    resetFeedback,
    updateActivePortfolio,
    replaceSnapshot,
    applyCollection,
    applySaveMetadata,
    applyDeletedPage,
    setSimulationResult,
    clearSimulationResult,
    buildSnapshot,
    removeDeletedPortfolio,
  }
}

export type PortfolioBalancePageState = ReturnType<typeof createPortfolioBalancePageState>
