import type { StrategyEditorContractResponse } from './contracts'

import { backtestApi } from './api'
import type { UseBacktestEditorCatalogOptions } from './editorTypes'
import { syncStrategyVersionSelection } from './selection'

export const useBacktestEditorCatalog = ({
  t,
  config,
  strategies,
  templates,
  indicators,
  indicatorEngines,
  editorContract,
  selectedStrategyVersions,
  editor,
}: UseBacktestEditorCatalogOptions) => {
  const categoryLabel = (value: string) => {
    if (value === 'trend') return t('backtest.categoryTrend')
    if (value === 'mean_reversion') return t('backtest.categoryMeanReversion')
    if (value === 'breakout') return t('backtest.categoryBreakout')
    if (value === 'custom') return t('backtest.categoryCustom')
    return value || '-'
  }

  const syncStrategyVersion = () => {
    const versions = selectedStrategyVersions.value
    syncStrategyVersionSelection(config, versions)
  }

  const fetchStrategies = async () => {
    try {
      const res = await backtestApi.listStrategies()
      strategies.value = res
      if (strategies.value.length && !strategies.value.find((item) => item.key === config.strategy_key)) {
        config.strategy_key = strategies.value[0].key
      }
      syncStrategyVersion()
    } catch (error) {
      console.error(error)
    }
  }

  const fetchTemplates = async () => {
    try {
      const res = await backtestApi.listTemplates()
      templates.value = res
      if (!templates.value.length) return
      const editableTemplates = Array.isArray(editor.editableTemplates?.value) ? editor.editableTemplates.value : templates.value
      const matchedTemplate = editableTemplates.find((item) => item.template === editor.versionDraft.template) || editableTemplates[0]
      if (!matchedTemplate) return
      if (!editor.versionDraft.template) return
      if (!Object.keys(editor.versionDraft.config?.indicators || {}).length) {
        editor.applyDraftFromTemplate(matchedTemplate.template)
      } else {
        editor.newIndicatorType.value = matchedTemplate.indicator_registry?.[0]?.key || indicators.value[0]?.key || 'ema'
      }
    } catch (error) {
      console.error(error)
    }
  }

  const fetchIndicators = async () => {
    try {
      const [indicatorRes, engineRes] = await Promise.all([backtestApi.listIndicators(), backtestApi.listIndicatorEngines()])
      indicators.value = indicatorRes
      indicatorEngines.value = engineRes
      if (!editor.newIndicatorType.value) editor.newIndicatorType.value = indicators.value[0]?.key || 'ema'
      editor.resetIndicatorDraft()
    } catch (error) {
      console.error(error)
    }
  }

  const fetchEditorContract = async () => {
    try {
      const res = await backtestApi.getEditorContract()
      editorContract.value = res
    } catch (error) {
      console.error(error)
    }
  }

  return {
    categoryLabel,
    syncStrategyVersion,
    fetchStrategies,
    fetchTemplates,
    fetchIndicators,
    fetchEditorContract,
  }
}


