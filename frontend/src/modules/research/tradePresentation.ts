import type { TradingViewStrategyMarker } from '../../components/tradingViewChartPresentation'

type RecordRow = Record<string, unknown>
export const signalStatus = (s: unknown) => ({ pending: '等待后续行情', executed: '已执行', ignored_flat: '空仓，忽略平仓', ignored_same_side: '已有同向持仓', ignored_position: '已有持仓', ignored_price_cap: '超出追价上限', ignored_stop_pause: '止损所在区间暂停入场', not_triggered: '有效区间内未触及突破价', ignored_nonpositive_equity: '权益不足', unexecuted_end: '区间结束，未执行' }[String(s)] ?? String(s))
export const exitReason = (s: unknown) => ({ stop: '止损', target: '止盈', protection: '利润回吐保护', end: '回测结束', stop_loss: '止损', take_profit: '止盈', profit_protection: '利润回吐保护', reversal: '反向信号', signal: '策略退出', end_of_backtest: '回测结束' }[String(s)] ?? String(s))
export const tradeColors = { long: '#F23645', short: '#4CAF50', closeLong: '#E91E63', closeShort: '#00897B', stop: '#FF9800' }

export function signalMarkers(signals: RecordRow[]): TradingViewStrategyMarker[] {
  return signals.filter(v => v.action === 'long' || v.action === 'short').map(v => ({
    time: Number(v.timestamp), kind: `${v.action}_entry`, position: v.action === 'short' ? 'aboveBar' : 'belowBar',
    label: v.action === 'long' ? '做多' : '做空', color: v.action === 'long' ? tradeColors.long : tradeColors.short,
  }))
}

export function fillMarkers(fills: RecordRow[], trades: RecordRow[], focusedTrade?: unknown): TradingViewStrategyMarker[] {
  const sides = new Map(trades.map(t => [t.trade_id, t.side]))
  for (const fill of fills) if (fill.action === 'long' || fill.action === 'short') sides.set(fill.trade_id, fill.action)
  const pairs = new Map<number, number>()
  for (let i = 0; i < fills.length - 1; i++) {
    const close = fills[i]!, open = fills[i + 1]!
    // Only merge a genuine opposite-side exit followed by a new entry on this
    // bar. A stopped position or missing lineage never becomes a reversal.
    if (close.action === 'close' && ['reversal', 'signal'].includes(String(close.reason))
        && ['long', 'short'].includes(String(open.action)) && sides.has(close.trade_id)
        && sides.get(close.trade_id) !== open.action && close.timestamp === open.timestamp
        && close.phase !== 'close') pairs.set(i, i + 1)
  }
  const reversed = new Map([...pairs].map(([a,b]) => [b,a]))
  return fills.flatMap((fill, i) => {
    if (focusedTrade != null && fill.trade_id !== focusedTrade) return []
    if (pairs.has(i) && (focusedTrade == null || fills[pairs.get(i)!]?.trade_id === focusedTrade)) return []
    const side = sides.get(fill.trade_id)
    const isClose = fill.action === 'close'
    const stopped = isClose && ['stop_loss', 'profit_protection'].includes(String(fill.reason))
    const reverse = reversed.has(i)
    const label = stopped ? '止损' : !isClose ? `${reverse ? '平仓' : ''}${fill.action === 'long' ? '做多' : '做空'}`
      : fill.reason === 'take_profit' ? '止盈' : side === 'long' ? '平多' : side === 'short' ? '平空' : '平仓'
    return [{ time: Number(fill.timestamp), kind: isClose ? 'exit' : `${fill.action}_entry`, label,
      position: stopped || (isClose ? side !== 'short' : fill.action === 'short') ? 'aboveBar' as const : 'belowBar' as const,
      color: stopped ? tradeColors.stop : !isClose ? fill.action === 'long' ? tradeColors.long : tradeColors.short
        : side === 'short' ? tradeColors.closeShort : tradeColors.closeLong }]
  })
}
