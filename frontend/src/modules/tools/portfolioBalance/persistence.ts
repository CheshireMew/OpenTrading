import { PAGE_SNAPSHOT_KEYS, readPersistentPageSnapshotData } from '@/composables/pageSnapshot'
import { apiErrorMessage } from '@/api/request'
import { toolsApi } from '../api'
import type {
  PortfolioCollectionImportCommand,
  PortfolioCollectionResponse,
} from '../contracts'
import { buildPortfolioChangeCommand, clonePortfolioSnapshot } from './changeSet'
import { createPortfolioSaveState } from './saveState'

import {
  createEmptyPortfolioBalanceSnapshot,
  normalizePortfolioBalancePortfolio,
  normalizePortfolioBalanceSnapshot,
  normalizePortfolioSimulationSummary,
} from './snapshot'
import type { PortfolioBalancePageState } from './state'
import type { PortfolioBalanceSnapshot, PortfolioSimulationSummary } from './types'

const IMPORT_MAX_BYTES = 128 * 1024 * 1024

export const parsePortfolioImportFile = async (
  file: File,
): Promise<PortfolioCollectionImportCommand['document']> => {
  if (file.size > IMPORT_MAX_BYTES) throw new Error('Portfolio backup exceeds the 128 MB limit')
  const text = await file.text()
  const parsed: unknown = JSON.parse(text)
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error('Portfolio backup must be a JSON object')
  }
  return parsed as PortfolioCollectionImportCommand['document']
}

export const createPortfolioPersistence = (
  state: PortfolioBalancePageState,
  defaultPortfolioName: string,
) => {
  let saveTimer: ReturnType<typeof setTimeout> | null = null
  const saveState = createPortfolioSaveState()
  let simulationLoadVersion = 0
  let acknowledgedSnapshot: PortfolioBalanceSnapshot | null = null
  let operationChain: Promise<void> = Promise.resolve()

  const serializeOperation = <T>(action: () => Promise<T>): Promise<T> => {
    const operation = operationChain.then(action, action)
    operationChain = operation.then(() => undefined, () => undefined)
    return operation
  }

  const acknowledgeResponse = (response: PortfolioCollectionResponse) => {
    acknowledgedSnapshot = clonePortfolioSnapshot({
      activePortfolioId: response.snapshot.activePortfolioId || '',
      portfolios: (response.snapshot.portfolios || []).map(normalizePortfolioBalancePortfolio),
    })
  }

  const saveCurrent = async () => {
    const saveVersion = saveState.captureVersion()
    const snapshot = state.buildSnapshot()
    const baseline = acknowledgedSnapshot || { activePortfolioId: '', portfolios: [] }
    const command = buildPortfolioChangeCommand(snapshot, baseline, state.revision.value)
    if (!command) {
      saveState.acknowledge(saveVersion)
      return null
    }
    state.storageSaving.value = true
    state.storageError.value = ''
    try {
      const response = await toolsApi.changePortfolioCollection(command)
      state.applySaveMetadata(response)
      acknowledgeResponse(response)
      saveState.acknowledge(saveVersion)
      return response
    } catch (error: unknown) {
      state.storageError.value = apiErrorMessage(error, 'Failed to save portfolio changes')
      throw error
    } finally {
      state.storageSaving.value = false
    }
  }

  const saveNow = (force = false) => serializeOperation(async () => {
    if (!force && !saveState.isDirty()) return null
    return saveCurrent()
  })

  const queueSave = () => {
    if (!state.storageReady.value) return
    saveState.markDirty()
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      void saveNow().catch(() => undefined)
    }, 500)
  }

  const loadDeleted = async (reset = true) => {
    const offset = reset ? 0 : state.deletedPortfolios.length
    const response = await toolsApi.listDeletedPortfolios(offset, 20)
    state.applyDeletedPage(response, !reset)
    return response
  }

  const loadSimulation = async (portfolioId = state.activePortfolioId.value) => {
    const loadVersion = ++simulationLoadVersion
    state.clearSimulationResult()
    if (!portfolioId) return null
    try {
      const response = await toolsApi.getPortfolioSimulation(portfolioId)
      if (
        loadVersion === simulationLoadVersion
        && portfolioId === state.activePortfolioId.value
      ) {
        state.setSimulationResult(
          portfolioId,
          normalizePortfolioSimulationSummary(response.result),
        )
      }
      return response
    } catch (error: unknown) {
      if (loadVersion === simulationLoadVersion) {
        state.storageError.value = apiErrorMessage(error, 'Failed to load simulation result')
      }
      throw error
    }
  }

  const saveSimulation = async (
    portfolioId: string,
    result: PortfolioSimulationSummary,
  ) => {
    const response = await toolsApi.savePortfolioSimulation(portfolioId, {
      expectedRevision: state.revision.value,
      result,
    })
    state.setSimulationResult(
      portfolioId,
      normalizePortfolioSimulationSummary(response.result),
    )
    return response
  }

  const initialize = async () => {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = null
    saveState.clear()
    acknowledgedSnapshot = null
    state.storageReady.value = false
    state.storageLoading.value = true
    state.storageError.value = ''
    try {
      const response = await toolsApi.getPortfolioCollection()
      if ((response.snapshot.portfolios || []).length > 0) {
        state.applyCollection(response)
        acknowledgeResponse(response)
      } else {
        const emptySnapshot = createEmptyPortfolioBalanceSnapshot()
        const legacy = readPersistentPageSnapshotData(PAGE_SNAPSHOT_KEYS.portfolioBalance, true)
        const legacySnapshot = normalizePortfolioBalanceSnapshot(legacy, emptySnapshot)
        state.replaceSnapshot(legacySnapshot)
        state.revision.value = response.revision
        const emptyBaseline: PortfolioBalanceSnapshot = {
          activePortfolioId: response.snapshot.activePortfolioId || '',
          portfolios: [],
        }
        acknowledgedSnapshot = clonePortfolioSnapshot(emptyBaseline)
        if (legacySnapshot.portfolios.length > 0) {
          const command = buildPortfolioChangeCommand(state.buildSnapshot(), emptyBaseline, response.revision)
          if (!command) throw new Error('Portfolio migration produced no changes')
          const saved = await toolsApi.changePortfolioCollection(command)
          state.applySaveMetadata(saved)
          acknowledgeResponse(saved)
        } else {
          acknowledgeResponse(response)
        }
      }
      state.storageReady.value = true
      await loadDeleted(true)
      if (state.activePortfolioId.value) await loadSimulation(state.activePortfolioId.value)
    } catch (error: unknown) {
      state.storageError.value = apiErrorMessage(error, 'Failed to load portfolios')
    } finally {
      state.storageLoading.value = false
    }
  }

  const restore = (portfolioId: string) => serializeOperation(async () => {
    if (saveState.isDirty()) await saveCurrent()
    state.storageSaving.value = true
    try {
      const response = await toolsApi.restorePortfolio(portfolioId, {
        expectedRevision: state.revision.value,
      })
      state.applyCollection(response)
      acknowledgeResponse(response)
      await Promise.all([
        loadDeleted(true),
        loadSimulation(response.snapshot.activePortfolioId || ''),
      ])
      saveState.clear()
      state.storageError.value = ''
      return response
    } catch (error: unknown) {
      state.storageError.value = apiErrorMessage(error, 'Failed to restore portfolio')
      throw error
    } finally {
      state.storageSaving.value = false
    }
  })

  const importDocument = (
    document: PortfolioCollectionImportCommand['document'],
    mode: PortfolioCollectionImportCommand['mode'] = 'merge',
  ) => serializeOperation(async () => {
    if (saveState.isDirty()) await saveCurrent()
    state.storageSaving.value = true
    try {
      const response = await toolsApi.importPortfolioCollection({
        expectedRevision: state.revision.value,
        mode,
        document,
      })
      state.applyCollection(response)
      acknowledgeResponse(response)
      await Promise.all([
        loadDeleted(true),
        loadSimulation(response.snapshot.activePortfolioId || ''),
      ])
      saveState.clear()
      state.storageError.value = ''
      return response
    } catch (error: unknown) {
      state.storageError.value = apiErrorMessage(error, 'Failed to import portfolio backup')
      throw error
    } finally {
      state.storageSaving.value = false
    }
  })

  const exportDocument = () => serializeOperation(async () => {
    if (saveState.isDirty()) await saveCurrent()
    return toolsApi.exportPortfolioCollection()
  })

  const stop = () => {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = null
    return saveNow()
  }

  const reload = () => serializeOperation(async () => {
    if (saveState.isDirty()) await saveCurrent()
    await initialize()
  })

  return {
    initialize,
    queueSave,
    saveNow,
    loadDeleted,
    loadSimulation,
    saveSimulation,
    restore,
    importDocument,
    exportDocument,
    reload,
    stop,
  }
}

export type PortfolioPersistence = ReturnType<typeof createPortfolioPersistence>
