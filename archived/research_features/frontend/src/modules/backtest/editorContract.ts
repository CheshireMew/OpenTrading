import type {
  EditableStrategyTemplateConfig,
  StrategyGroupNode,
  StrategyRuleNode,
} from './contracts'
import type {
  StrategyConditionNodeResponse,
  StrategyEditorContractResponse,
  StrategyIndicatorEngineResponse,
  StrategyTemplateConfigResponse,
} from './contracts'
import { isStrategyConditionNode, isStrategyGroupNode } from './contracts'

export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value))

export const buildId = (prefix: string) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`

export const normalizeEditableStrategyConfig = (value: StrategyTemplateConfigResponse): EditableStrategyTemplateConfig => {
  const config = clone(value) as EditableStrategyTemplateConfig
  config.indicators = config.indicators || {}
  config.risk.roi_targets = config.risk.roi_targets || []
  config.risk.partial_exits = config.risk.partial_exits || []
  return config
}

export const createBlankConfig = (contract: StrategyEditorContractResponse): EditableStrategyTemplateConfig => (
  normalizeEditableStrategyConfig(contract.blank_config)
)

export const createBlankGroup = (
  contract: StrategyEditorContractResponse,
  overrides: Partial<StrategyGroupNode> = {},
): StrategyGroupNode => ({
  ...clone(contract.blank_group),
  ...overrides,
  children: clone(overrides.children ?? contract.blank_group.children),
})

export const createBlankCondition = (
  contract: StrategyEditorContractResponse,
  overrides: Partial<StrategyConditionNodeResponse> = {},
): StrategyConditionNodeResponse => ({
  ...clone(contract.blank_condition),
  ...overrides,
  left: clone(overrides.left ?? contract.blank_condition.left),
  right: clone(overrides.right ?? contract.blank_condition.right),
})

export const createBlankIndicatorDraft = (indicatorEngines: StrategyIndicatorEngineResponse[] = []) => ({
  key: '',
  name: '',
  engine_key: indicatorEngines[0]?.key || 'ema',
  description: '',
  params: clone(indicatorEngines[0]?.params || []),
})

export const createBlankTemplateDraft = () => ({
  key: '',
  name: '',
  category: 'custom',
  description: '',
  indicator_keys: [] as string[],
})

export const createBlankVersionDraft = (contract: StrategyEditorContractResponse) => ({
  key: contract.run_defaults?.strategy_key || '',
  name: 'Variant',
  template: '',
  category: 'custom',
  description: '',
  notes: '',
  config: createBlankConfig(contract),
  parameterSpaceValues: {} as Record<string, string>,
  make_default: true,
})

export const coerceByType = (type: string, value: unknown, fallback: number = 0) => {
  if (type === 'bool') return Boolean(value)
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return fallback
  return type === 'int' ? Math.round(numeric) : numeric
}

export const collectRuleTargets = (
  node: StrategyRuleNode | null | undefined,
  prefix: string,
  targets: Array<{ path: string; label: string; type: string; fallback: number }>,
  constantLabel: string,
  multiplierLabel: string,
) => {
  if (!node) return
  if (isStrategyConditionNode(node)) {
    if (node.right.kind === 'value') {
      targets.push({ path: `${prefix}.${node.id}.right.value`, label: `${node.label} · ${constantLabel}`, type: 'float', fallback: 0 })
    }
    if (node.right.kind === 'indicator_multiplier') {
      targets.push({ path: `${prefix}.${node.id}.right.multiplier`, label: `${node.label} · ${multiplierLabel}`, type: 'float', fallback: 1 })
    }
    if (node.right.kind === 'indicator_offset') {
      targets.push({ path: `${prefix}.${node.id}.right.offset_multiplier`, label: `${node.label} · ${multiplierLabel}`, type: 'float', fallback: 1 })
    }
    return
  }
  if (!isStrategyGroupNode(node)) return
  for (const child of node.children || []) {
    collectRuleTargets(child, prefix, targets, constantLabel, multiplierLabel)
  }
}

export const buildParameterSpaceJson = (
  targets: Array<{ path: string; type: string; fallback: number }>,
  parameterSpaceValues: Record<string, string>,
) => {
  const parameterSpaceJson: Record<string, Array<number | boolean>> = {}
  for (const target of targets) {
    const raw = String(parameterSpaceValues[target.path] || '').trim()
    if (!raw) continue
    parameterSpaceJson[target.path] = raw
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => coerceByType(target.type, item, target.fallback))
  }
  return parameterSpaceJson
}

export const treeUsesIndicator = (node: StrategyRuleNode | null | undefined, indicatorId: string): boolean => {
  if (!node) return false
  if (isStrategyConditionNode(node)) {
    return [node.left, node.right].some((part) => {
      if (!part) return false
      if (part.kind === 'indicator' || part.kind === 'indicator_multiplier') {
        return part.indicator === indicatorId
      }
      if (part.kind === 'indicator_offset') {
        return part.base_indicator === indicatorId || part.offset_indicator === indicatorId
      }
      return false
    })
  }
  return isStrategyGroupNode(node) && (node.children || []).some((child) => treeUsesIndicator(child, indicatorId))
}

export const pruneTreeByIndicator = (node: StrategyGroupNode | null | undefined, indicatorId: string) => {
  if (!node?.children) return
  for (let index = node.children.length - 1; index >= 0; index -= 1) {
    const child = node.children[index]
    if (treeUsesIndicator(child, indicatorId)) {
      node.children.splice(index, 1)
      continue
    }
    if (isStrategyGroupNode(child)) pruneTreeByIndicator(child, indicatorId)
  }
}


