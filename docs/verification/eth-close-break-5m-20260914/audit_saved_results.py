"""Read saved project output and pair the original 84 signals; no simulation."""
import csv
import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUN = '2a840fd5a5c7d1e6de974e5979b37425'
OLD = '524a8f56d9ac334b9b8e283e762a4326'
FOLDER = ROOT / '.heimdall_runtime/local_backtests' / RUN


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def local_time(ms):
    return datetime.fromtimestamp(ms / 1000, timezone(timedelta(hours=8))).isoformat()


def save(name, value):
    with (OUT / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


cohort = read(OUT / 'original-84.json')
result = read(FOLDER / 'result.json')
config = read(FOLDER / 'config.json')
meta = read(FOLDER / 'metadata.json')
old_meta = read(ROOT / '.heimdall_runtime/local_backtests' / OLD / 'metadata.json')
assert meta['data_hash'] == old_meta['data_hash']
assert config['parameters']['confirmation_level'] == 1
assert config['parameters']['max_wait_bars'] == 0
assert config['parameters']['entry_bar_assumption'] == 0
assert config['execution_timeframe'] == '5m' and config['intrabar_profit_protection']

trades = result['trades']
posted = {t['entry_order_signal_time'] for t in trades}
origins = {x['timestamp']: int(x['values']['确认起点时间'])
           for x in result['indicators'] if x['timestamp'] in posted}
by_origin = {}
for t in trades:
    origin = origins[t['entry_order_signal_time']]
    identity = origin, t['side']
    assert identity not in by_origin, 'Signal consumed more than once'
    assert origin <= t['entry_order_signal_time'] < t['entry_time']
    by_origin[identity] = t

audit = []
for old in cohort:
    t = by_origin.get((old['origin'], old['side']))
    row = dict(old_trade_id=old['trade_id'], origin=old['origin'],
               origin_utc8=local_time(old['origin']), side=old['side'],
               old_entry_time=old['entry_time'], old_entry_price=old['actual_entry'],
               old_return_pct=old['return_pct'], old_exit_reason=old['exit_reason'])
    if t is None:
        row['category'] = 'not_entered_in_new_run'
    else:
        ambiguous = bool(t.get('entry_bar_ambiguous'))
        category = ('still_ambiguous_at_5m' if ambiguous else
                    'profit' if t['return_pct'] > 1e-9 else
                    'flat' if abs(t['return_pct']) <= 1e-9 else
                    'initial_stop_loss' if t['exit_reason'] == 'stop_loss' else 'other_loss')
        row.update(category=category, new_trade_id=t['trade_id'],
                   new_entry_time=t['entry_time'], new_entry_utc8=local_time(t['entry_time']),
                   new_entry_price=t['entry_price'], new_exit_time=t['exit_time'],
                   new_exit_utc8=local_time(t['exit_time']), new_exit_price=t['exit_price'],
                   new_return_pct=t['return_pct'], new_exit_reason=t['exit_reason'],
                   new_entry_phase=t['entry_phase'], new_ambiguous=ambiguous,
                   same_native_entry_bar=t['entry_time'] // 900000 * 900000 == old['entry_time'],
                   same_entry_price=abs(t['entry_price']-old['actual_entry']) < 1e-8)
    audit.append(row)

report = result['report']
assert report['total_trades'] == report['wins'] + report['losses'] + report['breakeven']
assert report['total_trades'] == len(trades)
summary = dict(run_id=RUN, batch_id='0e64d958d69a452cb2ed9dd3cd878822', config=config,
               report=report, execution_detail=result.get('execution_detail'),
               original_cohort_size=len(cohort), paired=sum('new_trade_id' in r for r in audit),
               cohort_categories=dict(Counter(r['category'] for r in audit)),
               cohort_exit_reasons=dict(Counter(r['new_exit_reason'] for r in audit if 'new_trade_id' in r)),
               same_native_entry_bar=sum(r.get('same_native_entry_bar', False) for r in audit),
               same_entry_price=sum(r.get('same_entry_price', False) for r in audit),
               all_new_entry_ambiguous=sum(bool(t.get('entry_bar_ambiguous')) for t in trades),
               all_new_exit_reasons=dict(Counter(t['exit_reason'] for t in trades)),
               data_hash=meta['data_hash'], execution_data_hash=meta['execution_data_hash'],
               result_hash=meta['result_hash'], strategy_hash=meta['strategy_hash'],
               engine_hash=meta['engine_code_hash'], old_coarse_data_unchanged=True,
               all_new_signals_consumed_once=True,
               caution='Matched by original signal and direction. New execution/protection can change whether or when a signal enters; unpaired signals are not counted as rescued profits. Five-minute ambiguity is retained, not assumed resolved.')
save('cohort-84-audit.json', audit)
save('results.json', summary)
fields = list(dict.fromkeys(k for row in audit for k in row))
with (OUT / 'cohort-84-audit.csv').open('x', encoding='utf-8-sig', newline='') as stream:
    writer = csv.DictWriter(stream, fields)
    writer.writeheader()
    writer.writerows(audit)

# Preserve actual five-minute OHLC around each old ambiguous entry for inspection.
wanted = {t['entry_time'] for t in cohort}
fine = read(FOLDER / 'execution_data.json')
samples = [bar for bar in fine if bar[0] // 900000 * 900000 in wanted]
assert len(samples) == 3 * len(wanted)
save('original-entry-5m-candles.json', dict(columns=['timestamp','open','high','low','close','volume'], rows=samples))
del fine
examples = {}
for row in audit:
    if row['category'] not in examples:
        examples[row['category']] = row
print(json.dumps(dict(report=report, cohort_categories=summary['cohort_categories'],
                      paired=summary['paired'], same_native_entry_bar=summary['same_native_entry_bar'],
                      same_entry_price=summary['same_entry_price'], all_ambiguous=summary['all_new_entry_ambiguous'],
                      execution_detail=summary['execution_detail'], examples=examples), ensure_ascii=False))
