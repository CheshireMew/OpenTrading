"""Replay only the already-discussed Sep 11 stop as a mechanical example.

Uses project simulator and archived Binance data; excluded from six-year ranking.
"""
from pathlib import Path
from datetime import datetime, timezone
from app.domain.local_backtest import Bar, simulate
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from scripts.cloud_width_reentry_study import OUT, ROOT, SOURCE, keep

CASE = ROOT/'.opentrading_runtime/local_backtests/67f07fcba58e4ceead15917e326d8c4d'


def main():
    rows = read_json(CASE/'data.json')
    bars = [Bar(*r) for r in rows]
    old = read_json(CASE/'result.json')
    start = int(datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc).timestamp()*1000)
    end = int(datetime(2026, 9, 11, 16, 0, tzinfo=timezone.utc).timestamp()*1000)
    module, spec = load_strategy(SOURCE)
    new = simulate(bars, module, validate_parameters(spec, {'stop_reentry': True}), warmup=650, step_ms=900000)
    original_stop = next(t for t in old['trades'] if t['entry_time'] == start and t['side'] == 'long')
    retry = next(f for f in new['fills'] if f['timestamp'] >= start and f['action'] == 'long' and f['reason'] == '初始止损后补一次')
    retried_trade = next(t for t in new['trades'] if t['trade_id'] == retry['trade_id'])
    trigger = next(s for s in new['signals'] if s['timestamp'] == retry['timestamp']-900000)
    obs = next(o for o in new['indicators'] if o['timestamp'] == trigger['timestamp'])
    close = next(r[4] for r in rows if r[0] == trigger['timestamp'])
    assert close > obs['values']['外侧上沿']
    assert retry['timestamp'] == start+900000
    assert original_stop['exit_reason'] == 'stop_loss'
    assert not [f for f in new['fills'] if f['action'] == 'long' and
                retried_trade['entry_time'] < f['timestamp'] <= retried_trade['exit_time']]
    result = dict(source_run=CASE.name, data_hash=file_hash(CASE/'data.json'), source_hash=file_hash(SOURCE),
        original_stop=original_stop, retry=retried_trade,
        retry_signal=dict(close=close, outer_upper=obs['values']['外侧上沿'], **trigger),
        event_window=[f for f in new['fills'] if start <= f['timestamp'] < end],
        note='仅说明真实止损后下一开盘可补一次及该例后续结果；不参与六年排名。Binance 现货，与用户 Bybit 永续图可能有报价差异。')
    keep(OUT/'sept11-reentry-example.json', result)
    print({k: {x: result[k][x] for x in ('entry_time', 'entry_price', 'exit_time', 'exit_price', 'return_pct', 'exit_reason')}
           for k in ('original_stop', 'retry')})


if __name__ == '__main__':
    main()
