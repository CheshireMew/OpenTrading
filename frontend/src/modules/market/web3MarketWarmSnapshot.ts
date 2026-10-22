import type { BinanceWeb3HeatRankBoardsResponse } from './contracts'
import { createWarmSnapshotStore } from './warmSnapshotStorage'

const WEB3_KEY_PREFIX = 'opentrading_web3_market_rank_warm_snapshot:heat-rank'
const WEB3_SNAPSHOT_LABEL = 'Web3 market warm snapshot'

const web3HeatRankKey = (chainId: string, size: number) => (
  `${WEB3_KEY_PREFIX}:${chainId}:${size}`
)

export const web3HeatRankWarmSnapshot = createWarmSnapshotStore<BinanceWeb3HeatRankBoardsResponse, [string, number]>({
  label: WEB3_SNAPSHOT_LABEL,
  key: web3HeatRankKey,
  validate: (payload, chainId, size) => payload.chain_id === chainId && payload.size === size && Boolean(payload.boards),
  hasContent: (payload) => Object.values(payload.boards || {}).some((board) => Boolean(board.items?.length)),
})

