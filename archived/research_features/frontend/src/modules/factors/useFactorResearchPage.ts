import { computed, reactive, type WatchStopHandle } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import {
  createPersistentPageSnapshot,
  PAGE_SNAPSHOT_KEYS,
} from '@/composables/pageSnapshot'
import { useTheme } from '@/composables/useTheme'

import { buildFactorResearchSnapshot, createDefaultFactorResearchSnapshot, normalizeFactorResearchSnapshot } from './pageSnapshot'
import { factorApi } from './api'
import {
  createFactorExecutionForm,
  createFactorResearchForm,
  createFactorResearchState,
  factorExecutionPayload,
  factorResearchPayload,
} from './state'
import { useFactorResearchData } from './useFactorResearchData'
import { useFactorResearchFormatting } from './useFactorResearchFormatting'
import { useFactorResearchSelection } from './useFactorResearchSelection'


export const useFactorResearchPage = () => {
  const { t } = useI18n()
  const { theme } = useTheme()
  const router = useRouter()
  const pageSnapshot = createPersistentPageSnapshot(
    PAGE_SNAPSHOT_KEYS.factorResearch,
    normalizeFactorResearchSnapshot,
    createDefaultFactorResearchSnapshot(),
  )
  const restoredSnapshot = pageSnapshot.initial

  const state = createFactorResearchState()
  let snapshotStop: WatchStopHandle | null = null
  const isDark = computed(() => theme.value === 'dark')

  const initializeContract = async () => {
    const response = await factorApi.getContract()
    const fallbackSnapshot = {
      form: createFactorResearchForm(response),
      executionForm: createFactorExecutionForm(response),
      selectedRunId: null,
      selectedFactorId: '',
    }
    const normalizedSnapshot = normalizeFactorResearchSnapshot(restoredSnapshot, fallbackSnapshot)
    Object.assign(state.form, normalizedSnapshot.form)
    Object.assign(state.executionForm, normalizedSnapshot.executionForm)
    state.selectedRunId.value = normalizedSnapshot.selectedRunId
    state.selectedFactorId.value = normalizedSnapshot.selectedFactorId
    if (!snapshotStop) {
      snapshotStop = pageSnapshot.bind(
        [state.form, state.executionForm, state.selectedRunId, state.selectedFactorId],
        () => buildFactorResearchSnapshot({
          form: factorResearchPayload(state.form),
          executionForm: factorExecutionPayload(state.executionForm),
          selectedRunId: state.selectedRunId.value,
          selectedFactorId: state.selectedFactorId.value,
        }),
      )
    }
  }

  const selection = useFactorResearchSelection(state)
  const formatting = useFactorResearchFormatting(state)
  const data = useFactorResearchData(state, selection.applyRun, t, router, initializeContract)

  const heroPanel = reactive({
    catalog: state.catalog,
  })

  const filtersPanel = reactive({
    form: state.form,
    catalog: state.catalog,
    factorPool: state.factorPool,
    loading: state.loading,
    catalogLoading: state.catalogLoading,
    runAnalysis: data.runAnalysis,
    toggleCategory: selection.toggleCategory,
    resetFactorSelection: selection.resetFactorSelection,
    toggleFactor: selection.toggleFactor,
    categoryChipClass: formatting.categoryChipClass,
    factorChipClass: formatting.factorChipClass,
  })

  const summaryPanel = reactive({
    summary: state.summary,
    formatDate: formatting.formatDate,
  })

  const sidebarPanel = reactive({
    runsLoading: state.runsLoading,
    runs: state.runs,
    selectedRunId: state.selectedRunId,
    blend: state.blend,
    executionForm: state.executionForm,
    executionLoading: state.executionLoading,
    loadRun: data.loadRun,
    startExecution: data.startExecution,
    formatDate: formatting.formatDate,
    formatNumber: formatting.formatNumber,
    formatPct: formatting.formatPct,
    scoreClass: formatting.scoreClass,
  })

  const detailPanel = reactive({
    isDark,
    ranking: state.ranking,
    loading: state.loading,
    selectedFactorId: state.selectedFactorId,
    selectedDetail: state.selectedDetail,
    blend: state.blend,
    selectFactor: selection.selectFactor,
    scoreClass: formatting.scoreClass,
    correlationClass: formatting.correlationClass,
    formatNumber: formatting.formatNumber,
    formatPct: formatting.formatPct,
    formatDate: formatting.formatDate,
  })

  return reactive({
    error: state.error,
    heroPanel,
    filtersPanel,
    summaryPanel,
    sidebarPanel,
    detailPanel,
  })
}

