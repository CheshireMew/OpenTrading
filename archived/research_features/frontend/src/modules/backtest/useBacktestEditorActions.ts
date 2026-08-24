import type { StrategyIndicatorConfigResponse } from './contracts'

import { buildParameterSpaceJson, clone } from './editorContract'
import { backtestApi } from './api'
import type { UseBacktestEditorActionsOptions } from './editorTypes'

export const useBacktestEditorActions = ({
  t,
  router,
  config,
  editor,
  fetchStrategies,
  fetchTemplates,
  fetchIndicators,
  syncStrategyVersion,
}: UseBacktestEditorActionsOptions) => {
  const createIndicator = async () => {
    try {
      await backtestApi.createIndicator({
        key: editor.indicatorDraft.key.trim(),
        name: editor.indicatorDraft.name.trim(),
        engine_key: editor.indicatorDraft.engine_key,
        description: editor.indicatorDraft.description.trim() || null,
        params: clone(editor.indicatorDraft.params),
      })
      await fetchIndicators()
      editor.resetIndicatorDraft()
      alert(t('backtest.indicatorSaved'))
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      alert(`${t('backtest.versionSaveFailed')}: ${detail}`)
    }
  }

  const createTemplate = async () => {
    try {
      if (!editor.versionDraft.config) throw new Error(t('backtest.templateMissing'))
      if (!editor.templateDraft.key.trim() || !editor.templateDraft.name.trim()) throw new Error(t('backtest.templateDraftRequired'))
      const indicatorKeys = Array.from(new Set([
        ...editor.templateDraft.indicator_keys,
        ...Object.values(editor.versionDraft.config.indicators).map((item) => (item as StrategyIndicatorConfigResponse).type),
      ]))
      const res = await backtestApi.createTemplate({
        key: editor.templateDraft.key.trim(),
        name: editor.templateDraft.name.trim(),
        category: editor.templateDraft.category.trim() || 'custom',
        description: editor.templateDraft.description.trim() || null,
        indicator_keys: indicatorKeys,
        default_config: clone(editor.versionDraft.config),
        default_parameter_space: buildParameterSpaceJson(editor.optimizableTargets.value, editor.versionDraft.parameterSpaceValues),
      })
      await fetchTemplates()
      editor.applyDraftFromTemplate(res.template, res.default_config, res.default_parameter_space, { description: res.description || '' })
      editor.resetTemplateDraft()
      alert(t('backtest.templateSaved'))
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      alert(`${t('backtest.versionSaveFailed')}: ${detail}`)
    }
  }

  const createStrategyVersion = async () => {
    try {
      if (!editor.versionDraft.key.trim() || !editor.versionDraft.name.trim()) throw new Error(t('backtest.versionDraftRequired'))
      if (!editor.versionDraft.config) throw new Error(t('backtest.templateMissing'))
      if (!editor.versionDraft.template || !editor.editorTemplate.value) throw new Error(t('backtest.templateMissing'))
      const res = await backtestApi.createStrategyVersion({
        key: editor.versionDraft.key.trim(),
        name: editor.versionDraft.name.trim(),
        template: editor.versionDraft.template,
        category: editor.editorTemplate.value.category || editor.versionDraft.category,
        description: editor.versionDraft.description.trim() || null,
        notes: editor.versionDraft.notes.trim() || null,
        config: clone(editor.versionDraft.config),
        parameter_space: buildParameterSpaceJson(editor.optimizableTargets.value, editor.versionDraft.parameterSpaceValues),
        make_default: editor.versionDraft.make_default,
      })
      await fetchStrategies()
      config.strategy_key = editor.versionDraft.key.trim()
      config.strategy_version = res.version
      syncStrategyVersion()
      await router.replace({
        path: '/backtest/editor',
        query: {
          mode: 'copy',
          strategy: config.strategy_key,
          version: String(config.strategy_version),
        },
      })
      alert(t('backtest.versionSaved'))
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error)
      alert(`${t('backtest.versionSaveFailed')}: ${detail}`)
    }
  }

  return {
    createIndicator,
    createTemplate,
    createStrategyVersion,
  }
}


