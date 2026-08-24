import type {
  BacktestExecutionMetadataResponse,
  PaperLiveExecutionMetadataResponse,
  StrategyConditionNodeResponse,
  StrategyGroupNodeResponse,
  StrategyIndicatorConfigResponse,
  StrategyPartialExitResponse,
  StrategyRiskConfigResponse,
  StrategyRoiTargetResponse,
  StrategyTemplateConfigResponse,
} from './generatedContracts'
export type * from './generatedContracts'

type StrategyConditionNode = StrategyConditionNodeResponse
type StrategyGroupNodeContract = StrategyGroupNodeResponse
type StrategyTemplateConfigContract = StrategyTemplateConfigResponse
type StrategyIndicatorConfigContract = StrategyIndicatorConfigResponse
type StrategyRiskConfigContract = StrategyRiskConfigResponse
type StrategyRoiTargetContract = StrategyRoiTargetResponse
type StrategyPartialExitContract = StrategyPartialExitResponse

export type StrategyGroupNode = Omit<StrategyGroupNodeContract, 'children'> & {
  children?: StrategyRuleNode[]
}

export type StrategyRuleNode = StrategyConditionNode | StrategyGroupNode

export type EditableStrategyTemplateConfig = Omit<StrategyTemplateConfigContract, 'indicators' | 'risk'> & {
  indicators: Record<string, StrategyIndicatorConfigContract>
  risk: Omit<StrategyRiskConfigContract, 'roi_targets' | 'partial_exits'> & {
    roi_targets: StrategyRoiTargetContract[]
    partial_exits: StrategyPartialExitContract[]
  }
}

export interface CandlestickData {
  time: number
  open: number
  high: number
  low: number
  close: number
}

export interface VolumeData {
  time: number
  value: number
  color: string
}

export interface ChartMarkerData {
  time: number
  kind: string
  label: string
  color?: string
  shape?: 'arrowUp' | 'arrowDown' | 'circle' | 'square'
  position?: 'aboveBar' | 'belowBar' | 'inBar'
}

export const isStrategyConditionNode = (
  node: StrategyRuleNode | null | undefined,
): node is StrategyConditionNodeResponse => node?.node_type === 'condition'

export const isStrategyGroupNode = (
  node: StrategyRuleNode | null | undefined,
): node is StrategyGroupNode => node?.node_type === 'group'

export const isPaperLiveMetadata = (
  metadata: BacktestExecutionMetadataResponse | PaperLiveExecutionMetadataResponse | null | undefined,
): metadata is PaperLiveExecutionMetadataResponse => metadata?.execution_mode === 'paper_live'

