import type { BinanceWeb3HeatRankItemResponse } from './contracts'
import type { SortDirection } from './binanceMarketShared'
export { WEB3_ALL_CHAIN_ID, WEB3_SUPPORTED_CHAIN_OPTIONS } from './generatedWeb3Chains'
import { WEB3_ALL_CHAIN_ID } from './generatedWeb3Chains'

export type Web3HeatRankSortField = 'heat_score' | 'percent_change_24h' | 'market_cap' | 'liquidity'

export type Web3HeatRankSortState = {
  field: Web3HeatRankSortField
  direction: SortDirection
}

export type Web3TokenDialogState = {
  open: boolean
  token: BinanceWeb3HeatRankItemResponse | null
}

export const WEB3_KLINE_INTERVALS = ['5min', '15min', '1h', '4h', '1d']

export const isWeb3AllChain = (chainId: string | null | undefined) => !chainId || chainId === WEB3_ALL_CHAIN_ID

export const web3ApiChainId = (chainId: string | null | undefined) => (
  isWeb3AllChain(chainId) ? undefined : String(chainId)
)

