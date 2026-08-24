import type {
  StrategyEditorContractResponse,
  StrategyIndicatorConfigResponse,
  StrategyIndicatorRegistryResponse,
  StrategyPartialExitResponse,
  StrategyRoiTargetResponse,
  StrategyStateBranchResponse,
  StrategyTemplateResponse,
} from './contracts'
import { collectRuleTargets } from './editorContract'
import type { EditableVersionDraft, IndicatorCard, OptimizableTarget, SourceOption } from './editorTypes'

type StrategyBranchKey = 'trend' | 'range'
type StrategyBranchSignalKey = 'long_entry' | 'long_exit' | 'short_entry' | 'short_exit'

const branchKeys: StrategyBranchKey[] = ['trend', 'range']
const branchSignalKeys: StrategyBranchSignalKey[] = ['long_entry', 'long_exit', 'short_entry', 'short_exit']

const indicatorSpec = (
  config: StrategyIndicatorConfigResponse,
  availableIndicators: StrategyIndicatorRegistryResponse[],
  normalizedIndicators: StrategyIndicatorRegistryResponse[],
) => (
  availableIndicators.find((item) => item.key === config.type)
  || normalizedIndicators.find((item) => item.key === config.type)
)

const timeframeLabel = (
  editorContract: StrategyEditorContractResponse | null,
  timeframe: string | undefined,
) => (
  editorContract?.timeframe_options?.find((item) => item.key === (timeframe || 'base'))?.label
  || timeframe
  || 'base'
)

export const buildIndicatorCards = (
  versionDraft: EditableVersionDraft,
  editorContract: StrategyEditorContractResponse | null,
  availableIndicators: StrategyIndicatorRegistryResponse[],
  normalizedIndicators: StrategyIndicatorRegistryResponse[],
): IndicatorCard[] => Object.entries(versionDraft.config?.indicators || {}).map(([id, indicator]) => {
  const config = indicator as StrategyIndicatorConfigResponse
  const spec = indicatorSpec(config, availableIndicators, normalizedIndicators)
  return {
    id,
    label: config.label || spec?.name || id,
    typeLabel: spec?.name || config.type,
    timeframeLabel: timeframeLabel(editorContract, config.timeframe),
    params: Array.isArray(spec?.params) ? spec.params.filter((item) => Boolean(item?.key)) : [],
  }
})

export const buildSourceOptions = (
  versionDraft: EditableVersionDraft,
  editorContract: StrategyEditorContractResponse | null,
  availableIndicators: StrategyIndicatorRegistryResponse[],
  normalizedIndicators: StrategyIndicatorRegistryResponse[],
  t: (key: string) => string,
): SourceOption[] => {
  const base: SourceOption[] = [
    { value: 'price:open:0', label: `Price · Open · ${t('backtest.currentBar')}` },
    { value: 'price:high:0', label: `Price · High · ${t('backtest.currentBar')}` },
    { value: 'price:low:0', label: `Price · Low · ${t('backtest.currentBar')}` },
    { value: 'price:close:0', label: `Price · Close · ${t('backtest.currentBar')}` },
    { value: 'price:volume:0', label: `Price · Volume · ${t('backtest.currentBar')}` },
    { value: 'price:open:1', label: `Price · Open · ${t('backtest.previousBar')}` },
    { value: 'price:high:1', label: `Price · High · ${t('backtest.previousBar')}` },
    { value: 'price:low:1', label: `Price · Low · ${t('backtest.previousBar')}` },
    { value: 'price:close:1', label: `Price · Close · ${t('backtest.previousBar')}` },
    { value: 'price:volume:1', label: `Price · Volume · ${t('backtest.previousBar')}` },
  ]
  const extra: SourceOption[] = []
  for (const [indicatorId, indicator] of Object.entries(versionDraft.config?.indicators || {})) {
    const config = indicator as StrategyIndicatorConfigResponse
    const spec = indicatorSpec(config, availableIndicators, normalizedIndicators)
    for (const output of spec?.outputs || []) {
      const label = timeframeLabel(editorContract, config.timeframe)
      extra.push({
        value: `indicator:${indicatorId}:${output.key}:0`,
        label: `${config.label || indicatorId} · ${output.label} · ${label} · ${t('backtest.currentBar')}`,
      })
      extra.push({
        value: `indicator:${indicatorId}:${output.key}:1`,
        label: `${config.label || indicatorId} · ${output.label} · ${label} · ${t('backtest.previousBar')}`,
      })
    }
  }
  return [...base, ...extra]
}

export const buildOptimizableTargets = (
  versionDraft: EditableVersionDraft,
  availableIndicators: StrategyIndicatorRegistryResponse[],
  normalizedIndicators: StrategyIndicatorRegistryResponse[],
  t: (key: string) => string,
): OptimizableTarget[] => {
  const targets: OptimizableTarget[] = []
  for (const [indicatorId, indicator] of Object.entries(versionDraft.config?.indicators || {})) {
    const config = indicator as StrategyIndicatorConfigResponse
    const spec = indicatorSpec(config, availableIndicators, normalizedIndicators)
    for (const param of spec?.params || []) {
      if (param.type === 'bool') continue
      targets.push({ path: `indicators.${indicatorId}.params.${param.key}`, label: `${config.label || indicatorId} · ${param.label}`, type: param.type, fallback: Number(param.default) })
    }
  }
  for (const branchKey of branchKeys) {
    const branch = versionDraft.config?.[branchKey] as StrategyStateBranchResponse | undefined
    if (!branch) continue
    collectRuleTargets(branch.regime, `${branchKey}.regime`, targets, t('backtest.constantValue'), t('backtest.multiplier'))
    for (const signalKey of branchSignalKeys) {
      collectRuleTargets(branch[signalKey], `${branchKey}.${signalKey}`, targets, t('backtest.constantValue'), t('backtest.multiplier'))
    }
  }
  for (const target of (versionDraft.config?.risk?.roi_targets || []) as StrategyRoiTargetResponse[]) {
    targets.push({ path: `risk.roi_targets.${target.id}.profit`, label: `ROI · ${target.minutes}m`, type: 'float', fallback: target.profit || 0 })
  }
  for (const item of (versionDraft.config?.risk?.partial_exits || []) as StrategyPartialExitResponse[]) {
    targets.push({ path: `risk.partial_exits.${item.id}.profit`, label: `Partial Exit · ${item.id}`, type: 'float', fallback: item.profit || 0 })
  }
  targets.push({ path: 'risk.stoploss', label: t('backtest.stoplossLabel'), type: 'float', fallback: versionDraft.config?.risk?.stoploss || -0.1 })
  targets.push({ path: 'risk.trailing.positive', label: t('backtest.trailingPositive'), type: 'float', fallback: versionDraft.config?.risk?.trailing?.positive || 0.02 })
  targets.push({ path: 'risk.trailing.offset', label: t('backtest.trailingOffset'), type: 'float', fallback: versionDraft.config?.risk?.trailing?.offset || 0.03 })
  return targets
}

