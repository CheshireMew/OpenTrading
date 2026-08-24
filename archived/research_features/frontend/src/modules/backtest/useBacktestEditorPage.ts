import { computed, onBeforeUnmount, onMounted, reactive, ref, watch, type WatchStopHandle } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { createPersistentPageSnapshot, PAGE_SNAPSHOT_KEYS } from '@/composables/pageSnapshot'
import type {
  StrategyDefinitionResponse,
  StrategyEditorContractResponse,
  StrategyIndicatorEngineResponse,
  StrategyIndicatorRegistryResponse,
  StrategyTemplateResponse,
  StrategyVersionResponse,
} from './contracts'

import type { BacktestEditorSeedPanel, BacktestVersionEditorPanel, StrategySelectionConfig } from './editorTypes'
import {
  buildBacktestEditorPageSnapshot,
  createDefaultBacktestEditorPageSnapshot,
  normalizeBacktestEditorPageSnapshot,
} from './pageSnapshots'
import { defineReactiveView } from './viewTypes'
import { useBacktestEditor } from './useBacktestEditor'
import { useBacktestEditorActions } from './useBacktestEditorActions'
import { useBacktestEditorCatalog } from './useBacktestEditorCatalog'
import { useBacktestEditorSeeds } from './useBacktestEditorSeeds'
import { supportsPaperTrading, supportsVersionEditing } from './templateRuntime'

export const useBacktestEditorPage = () => {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const pageSnapshot = createPersistentPageSnapshot(
    PAGE_SNAPSHOT_KEYS.backtestEditor,
    normalizeBacktestEditorPageSnapshot,
    createDefaultBacktestEditorPageSnapshot(),
  )
  const restoredSnapshot = pageSnapshot.initial

  const editorContract = ref<StrategyEditorContractResponse | null>(null)
  const strategies = ref<StrategyDefinitionResponse[]>([])
  const templates = ref<StrategyTemplateResponse[]>([])
  const indicators = ref<StrategyIndicatorRegistryResponse[]>([])
  const indicatorEngines = ref<StrategyIndicatorEngineResponse[]>([])
  const config = reactive<StrategySelectionConfig>(restoredSnapshot.config)
  let snapshotStopHandle: WatchStopHandle | null = null

  const selectedStrategy = computed<StrategyDefinitionResponse | null>(() => strategies.value.find((item) => item.key === config.strategy_key) || null)
  const selectedStrategyVersions = computed<StrategyVersionResponse[]>(() => {
    const versions = selectedStrategy.value?.versions
    if (!Array.isArray(versions)) return []
    return versions.filter(Boolean)
  })
  const selectedVersion = computed<StrategyVersionResponse | null>(() => selectedStrategyVersions.value.find((item) => item.version === config.strategy_version) || null)
  const canCopyCurrentStrategy = computed(() => Boolean(selectedVersion.value) && Boolean(supportsVersionEditing(selectedStrategy.value)))
  const strategyCapabilityHint = computed(() => {
    if (!selectedStrategy.value) return ''
    if (!supportsVersionEditing(selectedStrategy.value) && !supportsPaperTrading(selectedStrategy.value)) {
      return t('backtest.scriptedReadonlyHint')
    }
    if (!supportsVersionEditing(selectedStrategy.value)) {
      return t('backtest.readonlyStrategyHint')
    }
    return ''
  })

  const editor = useBacktestEditor({
    t,
    editorContract,
    templates,
    indicators,
    indicatorEngines,
    selectedStrategy,
    selectedVersion,
  })

  const catalog = useBacktestEditorCatalog({
    t,
    config,
    strategies,
    templates,
    indicators,
    indicatorEngines,
    editorContract,
    selectedStrategyVersions,
    editor,
  })

  const actions = useBacktestEditorActions({
    t,
    router,
    config,
    editor,
    fetchStrategies: catalog.fetchStrategies,
    fetchTemplates: catalog.fetchTemplates,
    fetchIndicators: catalog.fetchIndicators,
    syncStrategyVersion: catalog.syncStrategyVersion,
  })

  const seeds = useBacktestEditorSeeds({
    route,
    router,
    config,
    strategies,
    selectedStrategy,
    selectedVersion,
    editor,
    syncStrategyVersion: catalog.syncStrategyVersion,
  })

  const hasExplicitSeed = () => (
    typeof route.query.mode === 'string'
    || typeof route.query.strategy === 'string'
    || typeof route.query.version === 'string'
  )

  const startSnapshotSync = () => {
    snapshotStopHandle?.()
    snapshotStopHandle = pageSnapshot.bind(
      [
        config,
        editor.showVersionEditor,
        editor.showIndicatorCreator,
        editor.showTemplateCreator,
        editor.useGlobalIndicatorCatalog,
        editor.newIndicatorType,
        editor.versionDraft,
        editor.indicatorDraft,
        editor.templateDraft,
      ],
      () => buildBacktestEditorPageSnapshot(config, editor.buildSnapshot()),
    )
  }

  onMounted(async () => {
    await catalog.fetchEditorContract()
    await Promise.all([catalog.fetchStrategies(), catalog.fetchTemplates(), catalog.fetchIndicators()])
    editor.initializeDraftFromContract()

    if (hasExplicitSeed()) {
      seeds.applyRouteSeed()
    } else if (restoredSnapshot.editor) {
      editor.applySnapshot(restoredSnapshot.editor)
    } else {
      seeds.applyRouteSeed()
    }

    startSnapshotSync()
  })

  watch(
    () => [route.query.mode, route.query.strategy, route.query.version],
    () => {
      if (!strategies.value.length) return
      seeds.applyRouteSeed()
    },
  )

  onBeforeUnmount(() => {
    snapshotStopHandle?.()
  })

  const toggleIndicatorCreator = () => {
    editor.showIndicatorCreator.value = !editor.showIndicatorCreator.value
  }

  const toggleTemplateCreator = () => {
    editor.showTemplateCreator.value = !editor.showTemplateCreator.value
  }

  const seedPanel = defineReactiveView<BacktestEditorSeedPanel>({
    config,
    strategies,
    selectedStrategy,
    selectedStrategyVersions,
    selectedVersion,
    canCopyCurrentStrategy,
    strategyCapabilityHint,
    syncStrategyVersion: catalog.syncStrategyVersion,
    openCopySeed: seeds.openCopySeed,
    openBlankSeed: seeds.openBlankSeed,
    goBackToCenter: seeds.goBackToCenter,
  })

  const editorPanel = defineReactiveView<BacktestVersionEditorPanel>({
    showVersionEditor: editor.showVersionEditor,
    versionDraft: editor.versionDraft,
    metaPanel: {
      versionDraft: editor.versionDraft,
      templates: editor.editableTemplates,
      categoryLabel: catalog.categoryLabel,
      syncVersionDraftTemplate: editor.syncVersionDraftTemplate,
      startBlankBuilder: editor.startBlankBuilder,
      showIndicatorCreator: editor.showIndicatorCreator,
      showTemplateCreator: editor.showTemplateCreator,
      toggleIndicatorCreator,
      toggleTemplateCreator,
    },
    indicatorCreatorPanel: {
      show: editor.showIndicatorCreator,
      indicatorDraft: editor.indicatorDraft,
      indicatorEngines,
      createIndicator: actions.createIndicator,
      syncIndicatorDraftEngine: editor.syncIndicatorDraftEngine,
    },
    templateCreatorPanel: {
      show: editor.showTemplateCreator,
      templateDraft: editor.templateDraft,
      indicators,
      toggleTemplateIndicator: editor.toggleTemplateIndicator,
      createTemplate: actions.createTemplate,
    },
    strategyBuilderPanel: {
      editorContract,
      versionDraft: editor.versionDraft,
      editorTemplate: editor.editorTemplate,
      useGlobalIndicatorCatalog: editor.useGlobalIndicatorCatalog,
      availableIndicators: editor.availableIndicators,
      newIndicatorType: editor.newIndicatorType,
      indicatorCards: editor.indicatorCards,
      sourceOptions: editor.sourceOptions,
      indicatorSourceOptions: editor.indicatorSourceOptions,
      operatorOptions: editor.operatorOptions,
      groupLogicOptions: editor.groupLogicOptions,
      optimizableTargets: editor.optimizableTargets,
      syncExecutionConfig: editor.syncExecutionConfig,
      addIndicator: editor.addIndicator,
      removeIndicator: editor.removeIndicator,
      addRoiTarget: editor.addRoiTarget,
      removeRoiTarget: editor.removeRoiTarget,
      addPartialExit: editor.addPartialExit,
      removePartialExit: editor.removePartialExit,
    },
    createStrategyVersion: actions.createStrategyVersion,
  })

  return {
    seedPanel,
    editorPanel,
  }
}


