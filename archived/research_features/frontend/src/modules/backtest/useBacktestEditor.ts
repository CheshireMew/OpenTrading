import { computed, reactive, ref, type ComputedRef, type Ref } from 'vue'

import { isRecord, readBoolean, readString } from '@/composables/pageSnapshot'
import type {
  EditableStrategyTemplateConfig,
} from './contracts'
import type {
  StrategyDefinitionResponse,
  StrategyIndicatorRegistryResponse,
  StrategyOperatorResponse,
  StrategyStateBranchResponse,
  StrategyTemplateResponse,
  StrategyTemplateConfigResponse,
  StrategyVersionResponse,
} from './contracts'

import {
  buildId,
  clone,
  createBlankConfig,
  createBlankIndicatorDraft,
  createBlankTemplateDraft,
  createBlankVersionDraft,
  normalizeEditableStrategyConfig,
  pruneTreeByIndicator,
} from './editorContract'
import type { IndicatorCard, OptimizableTarget, SourceOption, UseBacktestEditorOptions } from './editorTypes'
import { buildIndicatorCards, buildOptimizableTargets, buildSourceOptions } from './editorDerived'
import type { BacktestEditorSnapshot } from './pageSnapshots'
import { supportsVersionEditing } from './templateRuntime'

type StrategyBranchKey = 'trend' | 'range'
type StrategyBranchSignalKey = 'long_entry' | 'long_exit' | 'short_entry' | 'short_exit'
type DraftOverrides = { description?: string }


export const useBacktestEditor = ({
  t,
  editorContract,
  templates,
  indicators,
  indicatorEngines,
  selectedStrategy,
  selectedVersion,
}: UseBacktestEditorOptions) => {
  const normalizedTemplates = computed<StrategyTemplateResponse[]>(() => templates.value.filter((item) => Boolean(item?.template)))
  const editableTemplates = computed<StrategyTemplateResponse[]>(() => normalizedTemplates.value.filter((item) => supportsVersionEditing(item)))
  const normalizedIndicators = computed<StrategyIndicatorRegistryResponse[]>(() => indicators.value.filter((item) => Boolean(item?.key)))
  const normalizedIndicatorEngines = computed(() => indicatorEngines.value.filter((item) => Boolean(item?.key)))
  const showVersionEditor = ref(false)
  const showIndicatorCreator = ref(false)
  const showTemplateCreator = ref(false)
  const useGlobalIndicatorCatalog = ref(false)
  const newIndicatorType = ref('')
  const editorReady = computed(() => Boolean(editorContract.value))

  const versionDraft = reactive({
    key: '',
    name: 'Variant',
    template: '',
    category: 'custom',
    description: '',
    notes: '',
    config: null as EditableStrategyTemplateConfig | null,
    parameterSpaceValues: {} as Record<string, string>,
    make_default: true,
  })
  const indicatorDraft = reactive(createBlankIndicatorDraft())
  const templateDraft = reactive(createBlankTemplateDraft())

  const editorTemplate = computed<StrategyTemplateResponse | null>(() => normalizedTemplates.value.find((item) => item.template === versionDraft.template) || null)
  const availableIndicators = computed<StrategyIndicatorRegistryResponse[]>(() => (
    useGlobalIndicatorCatalog.value
      ? normalizedIndicators.value
      : (editorTemplate.value?.indicator_registry || normalizedIndicators.value).filter((item) => Boolean(item?.key))
  ).filter((item) => Boolean(item?.key)))
  const operatorOptions = computed<StrategyOperatorResponse[]>(() => editorTemplate.value?.operators || editorContract.value?.operators || [])
  const groupLogicOptions = computed(() => editorTemplate.value?.group_logics || editorContract.value?.group_logics || [])
  const indicatorCards = computed<IndicatorCard[]>(() => buildIndicatorCards(
    versionDraft,
    editorContract.value,
    availableIndicators.value,
    normalizedIndicators.value,
  ))

  const sourceOptions = computed<SourceOption[]>(() => buildSourceOptions(
    versionDraft,
    editorContract.value,
    availableIndicators.value,
    normalizedIndicators.value,
    t,
  ))
  const indicatorSourceOptions = computed(() => sourceOptions.value.filter((item) => item.value.startsWith('indicator:')))
  const branchKeys: StrategyBranchKey[] = ['trend', 'range']
  const branchSignalKeys: StrategyBranchSignalKey[] = ['long_entry', 'long_exit', 'short_entry', 'short_exit']

  const resolveDraftSeed = () => {
    const strategy = selectedStrategy.value
    const preferredKey = supportsVersionEditing(strategy) ? (strategy?.key || editorContract.value?.run_defaults?.strategy_key || '') : ''
    const templateSpec = editableTemplates.value.find((item) => item.template === strategy?.template)
      || normalizedTemplates.value.find((item) => item.template === versionDraft.template)
      || editableTemplates.value[0]
      || null

    return {
      key: preferredKey || templateSpec?.template || '',
      template: templateSpec?.template || '',
      category: templateSpec?.category || 'custom',
      description: strategy?.description || templateSpec?.description || '',
    }
  }

  const optimizableTargets = computed<OptimizableTarget[]>(() => buildOptimizableTargets(
    versionDraft,
    availableIndicators.value,
    normalizedIndicators.value,
    t,
  ))

  const resetIndicatorDraft = () => {
    Object.assign(indicatorDraft, createBlankIndicatorDraft(normalizedIndicatorEngines.value))
  }

  const resetTemplateDraft = () => {
    Object.assign(templateDraft, createBlankTemplateDraft())
  }

  const syncIndicatorDraftEngine = () => {
    const engine = normalizedIndicatorEngines.value.find((item) => item.key === indicatorDraft.engine_key)
    indicatorDraft.params = clone(engine?.params || [])
  }

  const applyDraftFromTemplate = (
    templateKey: string,
    configValues: Partial<StrategyTemplateConfigResponse> = {},
    parameterSpaceValues: Record<string, unknown[]> = {},
    overrides: DraftOverrides = {},
  ) => {
    const templateSpec = editableTemplates.value.find((item) => item.template === templateKey)
    if (!templateSpec) return
    useGlobalIndicatorCatalog.value = false
    versionDraft.template = templateSpec.template
    versionDraft.category = templateSpec.category
    versionDraft.description = overrides.description ?? templateSpec.description ?? ''
    versionDraft.config = normalizeEditableStrategyConfig(Object.keys(configValues).length ? {
      ...templateSpec.default_config,
      ...configValues,
    } : templateSpec.default_config)

    const nextParameterSpaceValues: Record<string, string> = {}
    const source = Object.keys(parameterSpaceValues).length ? parameterSpaceValues : templateSpec.default_parameter_space
    for (const [key, values] of Object.entries(source || {})) {
      nextParameterSpaceValues[key] = Array.isArray(values) ? values.join(', ') : ''
    }
    versionDraft.parameterSpaceValues = nextParameterSpaceValues
    newIndicatorType.value = templateSpec.indicator_registry?.find((item) => item?.key)?.key || normalizedIndicators.value[0]?.key || 'ema'
  }

  const syncVersionDraftTemplate = () => {
    if (!versionDraft.template) return
    applyDraftFromTemplate(versionDraft.template)
  }

  const addIndicator = () => {
    if (!versionDraft.config) return
    const spec = availableIndicators.value.find((item) => item.key === newIndicatorType.value)
    if (!spec) return
    let candidateId = spec.key
    let suffix = 2
    while (versionDraft.config.indicators[candidateId]) {
      candidateId = `${spec.key}_${suffix}`
      suffix += 1
    }
    const params: Record<string, number | boolean> = {}
    for (const param of spec.params || []) params[param.key] = param.default
    versionDraft.config.indicators[candidateId] = { label: spec.name, type: spec.key, timeframe: 'base', params }
  }

  const removeIndicator = (indicatorId: string) => {
    if (!versionDraft.config) return
    delete versionDraft.config.indicators[indicatorId]
    for (const branchKey of branchKeys) {
      const branch = versionDraft.config?.[branchKey] as StrategyStateBranchResponse | undefined
      if (!branch) continue
      pruneTreeByIndicator(branch.regime, indicatorId)
      for (const signalKey of branchSignalKeys) {
        pruneTreeByIndicator(branch[signalKey], indicatorId)
      }
    }
    Object.keys(versionDraft.parameterSpaceValues).forEach((key) => {
      if (key.startsWith(`indicators.${indicatorId}.`)) delete versionDraft.parameterSpaceValues[key]
    })
  }

  const syncExecutionConfig = () => {
    if (!versionDraft.config?.execution) return
    if (versionDraft.config.execution.market_type === 'spot') {
      versionDraft.config.execution.direction = 'long_only'
    }
  }

  const addRoiTarget = () => {
    if (!versionDraft.config) return
    versionDraft.config.risk.roi_targets.push({ id: buildId('roi'), minutes: 0, profit: 0.03, enabled: true })
  }

  const removeRoiTarget = (targetId: string) => {
    if (!versionDraft.config) return
    const next = versionDraft.config.risk.roi_targets.filter((item) => item.id !== targetId)
    versionDraft.config.risk.roi_targets.splice(0, versionDraft.config.risk.roi_targets.length, ...next)
  }

  const addPartialExit = () => {
    if (!versionDraft.config) return
    versionDraft.config.risk.partial_exits.push({ id: buildId('partial'), profit: 0.05, size_pct: 25, enabled: true })
  }

  const removePartialExit = (itemId: string) => {
    if (!versionDraft.config) return
    const next = versionDraft.config.risk.partial_exits.filter((item) => item.id !== itemId)
    versionDraft.config.risk.partial_exits.splice(0, versionDraft.config.risk.partial_exits.length, ...next)
  }

  const fillVersionDraft = () => {
    const strategy = selectedStrategy.value
    const version = selectedVersion.value
    if (!strategy || !version) return
    versionDraft.key = strategy.key
    versionDraft.name = `${version.name} Copy`
    versionDraft.notes = version.notes || ''
    versionDraft.make_default = true
    applyDraftFromTemplate(strategy.template, version.config || {}, version.parameter_space || {}, { description: strategy.description || '' })
    showVersionEditor.value = true
  }

  const startBlankBuilder = () => {
    if (!editorContract.value) return
    useGlobalIndicatorCatalog.value = true
    versionDraft.template = ''
    versionDraft.category = 'custom'
    versionDraft.description = ''
    versionDraft.notes = ''
    versionDraft.config = createBlankConfig(editorContract.value)
    versionDraft.parameterSpaceValues = {}
    versionDraft.make_default = true
    newIndicatorType.value = normalizedIndicators.value[0]?.key || 'ema'
    resetTemplateDraft()
    showVersionEditor.value = true
  }

  const toggleTemplateIndicator = (indicatorKey: string) => {
    if (templateDraft.indicator_keys.includes(indicatorKey)) {
      templateDraft.indicator_keys = templateDraft.indicator_keys.filter((item) => item !== indicatorKey)
      return
    }
    templateDraft.indicator_keys = [...templateDraft.indicator_keys, indicatorKey]
  }

  const initializeDraftFromContract = () => {
    if (versionDraft.config || !editorContract.value) return

    const seed = resolveDraftSeed()
    Object.assign(versionDraft, createBlankVersionDraft(editorContract.value))
    versionDraft.key = seed.key || versionDraft.key
    versionDraft.template = seed.template
    versionDraft.category = seed.category
    versionDraft.description = seed.description

    if (seed.template) {
      applyDraftFromTemplate(seed.template, {}, {}, { description: seed.description })
    }
    if (!newIndicatorType.value) {
      newIndicatorType.value = normalizedIndicators.value[0]?.key || 'ema'
    }
  }

  const buildSnapshot = (): BacktestEditorSnapshot => ({
    showVersionEditor: showVersionEditor.value,
    showIndicatorCreator: showIndicatorCreator.value,
    showTemplateCreator: showTemplateCreator.value,
    useGlobalIndicatorCatalog: useGlobalIndicatorCatalog.value,
    newIndicatorType: newIndicatorType.value,
    versionDraft: clone(versionDraft),
    indicatorDraft: clone(indicatorDraft),
    templateDraft: clone(templateDraft),
  })

  const applySnapshot = (snapshot: BacktestEditorSnapshot) => {
    showVersionEditor.value = readBoolean(snapshot.showVersionEditor, showVersionEditor.value)
    showIndicatorCreator.value = readBoolean(snapshot.showIndicatorCreator, showIndicatorCreator.value)
    showTemplateCreator.value = readBoolean(snapshot.showTemplateCreator, showTemplateCreator.value)
    useGlobalIndicatorCatalog.value = readBoolean(snapshot.useGlobalIndicatorCatalog, useGlobalIndicatorCatalog.value)
    newIndicatorType.value = readString(snapshot.newIndicatorType, newIndicatorType.value)

    if (isRecord(snapshot.versionDraft)) {
      const seed = resolveDraftSeed()
      Object.assign(versionDraft, clone(snapshot.versionDraft))
      versionDraft.key = readString(versionDraft.key, seed.key)
      versionDraft.name = readString(versionDraft.name, 'Variant')
      versionDraft.template = readString(versionDraft.template, seed.template)
      versionDraft.category = readString(versionDraft.category, seed.category)
      versionDraft.description = readString(versionDraft.description, seed.description)
      versionDraft.notes = typeof versionDraft.notes === 'string' ? versionDraft.notes : ''
      versionDraft.make_default = typeof versionDraft.make_default === 'boolean' ? versionDraft.make_default : true
      versionDraft.parameterSpaceValues = isRecord(versionDraft.parameterSpaceValues)
        ? Object.fromEntries(Object.entries(versionDraft.parameterSpaceValues).filter((entry): entry is [string, string] => typeof entry[0] === 'string' && typeof entry[1] === 'string'))
        : {}
      if (!versionDraft.config && editorContract.value) {
        versionDraft.config = createBlankConfig(editorContract.value)
      } else if (versionDraft.config) {
        versionDraft.config = normalizeEditableStrategyConfig(versionDraft.config)
      }
    }

    if (isRecord(snapshot.indicatorDraft)) {
      Object.assign(indicatorDraft, clone(snapshot.indicatorDraft))
      indicatorDraft.key = typeof indicatorDraft.key === 'string' ? indicatorDraft.key : ''
      indicatorDraft.name = typeof indicatorDraft.name === 'string' ? indicatorDraft.name : ''
      indicatorDraft.engine_key = readString(indicatorDraft.engine_key, normalizedIndicatorEngines.value[0]?.key || 'ema')
      indicatorDraft.description = typeof indicatorDraft.description === 'string' ? indicatorDraft.description : ''
      indicatorDraft.params = Array.isArray(indicatorDraft.params) ? clone(indicatorDraft.params) : clone(normalizedIndicatorEngines.value[0]?.params || [])
    }

    if (isRecord(snapshot.templateDraft)) {
      Object.assign(templateDraft, clone(snapshot.templateDraft))
      templateDraft.key = typeof templateDraft.key === 'string' ? templateDraft.key : ''
      templateDraft.name = typeof templateDraft.name === 'string' ? templateDraft.name : ''
      templateDraft.category = readString(templateDraft.category, 'custom')
      templateDraft.description = typeof templateDraft.description === 'string' ? templateDraft.description : ''
      templateDraft.indicator_keys = Array.isArray(templateDraft.indicator_keys)
        ? templateDraft.indicator_keys.filter((item): item is string => typeof item === 'string' && item.length > 0)
        : []
    }
  }

  return {
    showVersionEditor,
    showIndicatorCreator,
    showTemplateCreator,
    useGlobalIndicatorCatalog,
    newIndicatorType,
    editorReady,
    versionDraft,
    indicatorDraft,
    templateDraft,
    editableTemplates,
    editorTemplate,
    availableIndicators,
    operatorOptions,
    groupLogicOptions,
    indicatorCards,
    sourceOptions,
    indicatorSourceOptions,
    optimizableTargets,
    resetIndicatorDraft,
    resetTemplateDraft,
    syncIndicatorDraftEngine,
    applyDraftFromTemplate,
    syncVersionDraftTemplate,
    addIndicator,
    removeIndicator,
    syncExecutionConfig,
    addRoiTarget,
    removeRoiTarget,
    addPartialExit,
    removePartialExit,
    fillVersionDraft,
    startBlankBuilder,
    toggleTemplateIndicator,
    initializeDraftFromContract,
    buildSnapshot,
    applySnapshot,
  }
}

