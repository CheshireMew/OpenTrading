import type { BinanceMarketPageResponse } from './contracts'
import { createWarmSnapshotStore } from './warmSnapshotStorage'

const MARKET_KEY_PREFIX = 'opentrading_binance_market_warm_snapshot:market-page'
const MARKET_SNAPSHOT_LABEL = 'Binance market warm snapshot'

const marketPageKey = (minRisePct: number, quoteAsset: string) => (
  `${MARKET_KEY_PREFIX}:${quoteAsset.toUpperCase()}:${Number(minRisePct).toFixed(2)}`
)

export const binanceMarketWarmSnapshot = createWarmSnapshotStore<BinanceMarketPageResponse, [number, string]>({
  label: MARKET_SNAPSHOT_LABEL,
  key: marketPageKey,
  validate: (payload, _minRisePct, quoteAsset) => (
    payload.exchange === 'binance'
    && payload.quote_asset === quoteAsset.toUpperCase()
    && Boolean(payload.monitor && payload.spot_boards && payload.contract_boards)
  ),
  hasContent: (payload) => {
    const hasSpotRows = Object.values(payload.spot_boards || {}).some((board) => Boolean(board.items?.length))
    const hasContractRows = Object.values(payload.contract_boards || {}).some((board) => Boolean(board.items?.length))
    return Boolean(payload.monitor?.items?.length || hasSpotRows || hasContractRows)
  },
})

