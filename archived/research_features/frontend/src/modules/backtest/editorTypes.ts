import type { ComputedRef, Ref } from 'vue'
import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'

import type {
  EditableStrategyTemplateConfig,
} from './contracts'
import type {
  StrategyDefinitionResponse,
  StrategyEditorContractResponse,
  StrategyGroupLogicResponse,
  StrategyIndicatorEngineResponse,
  StrategyIndicatorParamResponse,
  StrategyIndicatorRegistryResponse,
  StrategyOperatorResponse,
  StrategyTemplateConfigResponse,
  StrategyTemplateResponse,
  StrategyTemplateRuntimeResponse,
  StrategyVersionResponse,
} from './contracts'

import type { createBlankIndicatorDraft, createBlankTemplateDraft, createBlankVersionDraft } from './editorContract'
import type { BacktestEditorSnapshot } from './pageSnapshots'

export interface StrategySelectionConfig {
  strategy_key: string
  strategy_version: number
}

export type VersionDraft = ReturnType<typeof createBlankVersionDraft>
export type EditableVersionDraft = Omit<VersionDraft, 'config'> & {
  config: EditableStrategyTemplateConfig | null
}
export type IndicatorDraft = ReturnType<typeof createBlankIndicatorDraft>
export type TemplateDraft = ReturnType<typeof createBlankTemplateDraft>

export type EditorTemplateRuntimeCarrier = {
  template_runtime?: StrategyTemplateRuntimeResponse | null
} | null | undefined

export interface IndicatorCard {
  id: string
  label: string
  typeLabel: string
  timeframeLabel: string
  params: StrategyIndicatorParamResponse[]
}

export interface SourceOption {
  value: string
  label: string
}

export interface OptimizableTarget {
  path: string
  label: string
  type: string
  fallback: number
}

export interface UseBacktestEditorOptions {
  t: (key: string) => string
  editorContract: Ref<StrategyEditorContractResponse | null>
  templates: Ref<StrategyTemplateResponse[]>
  indicators: Ref<StrategyIndicatorRegistryResponse[]>
  indicatorEngines: Ref<StrategyIndicatorEngineResponse[]>
  selectedStrategy: ComputedRef<StrategyDefinitionResponse | null>
  selectedVersion: ComputedRef<StrategyVersionResponse | null>
}

export interface UseBacktestEditorCatalogOptions {
  t: (key: string) => string
  config: StrategySelectionConfig
  strategies: Ref<StrategyDefinitionResponse[]>
  templates: Ref<StrategyTemplateResponse[]>
  indicators: Ref<StrategyIndicatorRegistryResponse[]>
  indicatorEngines: Ref<StrategyIndicatorEngineResponse[]>
  editorContract: Ref<StrategyEditorContractResponse | null>
  selectedStrategyVersions: ComputedRef<StrategyVersionResponse[]>
  editor: BacktestEditorState
}

export interface UseBacktestEditorActionsOptions {
  t: (key: string) => string
  router: Router
  config: StrategySelectionConfig
  editor: BacktestEditorState
  fetchStrategies: () => Promise<void>
  fetchTemplates: () => Promise<void>
  fetchIndicators: () => Promise<void>
  syncStrategyVersion: () => void
}

export interface UseBacktestEditorSeedsOptions {
  route: RouteLocationNormalizedLoaded
  router: Router
  config: StrategySelectionConfig
  strategies: Ref<StrategyDefinitionResponse[]>
  selectedStrategy: ComputedRef<StrategyDefinitionResponse | null>
  selectedVersion: ComputedRef<StrategyVersionResponse | null>
  editor: BacktestEditorState
  syncStrategyVersion: () => void
}

export interface BacktestEditorState {
  showVersionEditor: Ref<boolean>
  showIndicatorCreator: Ref<boolean>
  showTemplateCreator: Ref<boolean>
  useGlobalIndicatorCatalog: Ref<boolean>
  newIndicatorType: Ref<string>
  editorReady: ComputedRef<boolean>
  versionDraft: EditableVersionDraft
  indicatorDraft: IndicatorDraft
  templateDraft: TemplateDraft
  editableTemplates: ComputedRef<StrategyTemplateResponse[]>
  editorTemplate: ComputedRef<StrategyTemplateResponse | null>
  availableIndicators: ComputedRef<StrategyIndicatorRegistryResponse[]>
  operatorOptions: ComputedRef<StrategyOperatorResponse[]>
  groupLogicOptions: ComputedRef<StrategyGroupLogicResponse[]>
  indicatorCards: ComputedRef<IndicatorCard[]>
  sourceOptions: ComputedRef<SourceOption[]>
  indicatorSourceOptions: ComputedRef<SourceOption[]>
  optimizableTargets: ComputedRef<OptimizableTarget[]>
  resetIndicatorDraft: () => void
  resetTemplateDraft: () => void
  syncIndicatorDraftEngine: () => void
  applyDraftFromTemplate: (
    templateKey: string,
    configValues?: Partial<StrategyTemplateConfigResponse>,
    parameterSpaceValues?: Record<string, unknown[]>,
    overrides?: { description?: string },
  ) => void
  syncVersionDraftTemplate: () => void
  addIndicator: () => void
  removeIndicator: (indicatorId: string) => void
  syncExecutionConfig: () => void
  addRoiTarget: () => void
  removeRoiTarget: (targetId: string) => void
  addPartialExit: () => void
  removePartialExit: (itemId: string) => void
  fillVersionDraft: () => void
  startBlankBuilder: () => void
  toggleTemplateIndicator: (indicatorKey: string) => void
  initializeDraftFromContract: () => void
  buildSnapshot: () => BacktestEditorSnapshot
  applySnapshot: (snapshot: BacktestEditorSnapshot) => void
}

export interface BacktestEditorSeedPanel {
  config: StrategySelectionConfig
  strategies: StrategyDefinitionResponse[]
  selectedStrategy: StrategyDefinitionResponse | null
  selectedStrategyVersions: StrategyVersionResponse[]
  selectedVersion: StrategyVersionResponse | null
  canCopyCurrentStrategy: boolean
  strategyCapabilityHint: string
  syncStrategyVersion: () => void
  openCopySeed: () => Promise<void>
  openBlankSeed: () => Promise<void>
  goBackToCenter: () => void
}

export interface BacktestVersionMetaPanel {
  versionDraft: EditableVersionDraft
  templates: StrategyTemplateResponse[]
  categoryLabel: (value: string) => string
  syncVersionDraftTemplate: () => void
  startBlankBuilder: () => void
  showIndicatorCreator: boolean
  showTemplateCreator: boolean
  toggleIndicatorCreator: () => void
  toggleTemplateCreator: () => void
}

export interface BacktestIndicatorCreatorPanel {
  show: boolean
  indicatorDraft: IndicatorDraft
  indicatorEngines: StrategyIndicatorEngineResponse[]
  createIndicator: () => Promise<void>
  syncIndicatorDraftEngine: () => void
}

export interface BacktestTemplateCreatorPanel {
  show: boolean
  templateDraft: TemplateDraft
  indicators: StrategyIndicatorRegistryResponse[]
  toggleTemplateIndicator: (indicatorKey: string) => void
  createTemplate: () => Promise<void>
}

export interface BacktestStrategyBuilderPanel {
  editorContract: StrategyEditorContractResponse | null
  versionDraft: EditableVersionDraft
  editorTemplate: StrategyTemplateResponse | null
  useGlobalIndicatorCatalog: boolean
  availableIndicators: StrategyIndicatorRegistryResponse[]
  newIndicatorType: string
  indicatorCards: IndicatorCard[]
  sourceOptions: SourceOption[]
  indicatorSourceOptions: SourceOption[]
  operatorOptions: StrategyOperatorResponse[]
  groupLogicOptions: StrategyGroupLogicResponse[]
  optimizableTargets: OptimizableTarget[]
  syncExecutionConfig: () => void
  addIndicator: () => void
  removeIndicator: (indicatorId: string) => void
  addRoiTarget: () => void
  removeRoiTarget: (targetId: string) => void
  addPartialExit: () => void
  removePartialExit: (itemId: string) => void
}

export interface BacktestVersionEditorPanel {
  showVersionEditor: boolean
  versionDraft: EditableVersionDraft
  metaPanel: BacktestVersionMetaPanel
  indicatorCreatorPanel: BacktestIndicatorCreatorPanel
  templateCreatorPanel: BacktestTemplateCreatorPanel
  strategyBuilderPanel: BacktestStrategyBuilderPanel
  createStrategyVersion: () => Promise<void>
}


