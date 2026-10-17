"""Read completed project results, verify comparability and save a small summary.

This script does not simulate or select a strategy. The project CLI runs the
three immutable request files; its run folders retain all candles and trades.
"""
from collections import Counter
from hashlib import sha256
from math import isclose, prod
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUNTIME = ROOT/'.heimdall_runtime/local_backtests'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    runs = read(OUT/'runs.json')
    old_bnb = read(ROOT/'docs/verification/bnb-final-two-20260914/results.json')['rows'][0]
    old_sol_source = ROOT/'docs/verification/alt-cloud-transfer-20260911/results.json'
    sol = read(old_sol_source)
    old_sol = sol['results']['sol']['c55_w50_t0p4_d2_a2_g50_s1']['full']
    sol_data = ROOT/sol['data']['sol']['path']
    btc_source = ROOT/'docs/verification/cloud-direct-adaptation-20260912/results.json'
    btc = read(btc_source)
    old_btc = btc['results']['btc']['1h']['c0r0t0']['metrics']
    btc_data = ROOT/btc['plan']['data']['btc']['1h']['path']
    baseline = dict(bnb=old_bnb['report'], sol=old_sol, btc=old_btc)
    old_data = dict(bnb=RUNTIME/'657b2b8086588a254442b82b128d34df/data.json',
                    sol=sol_data, btc=btc_data)
    source = dict(bnb=ROOT/'docs/verification/bnb-final-two-20260914/results.json',
                  sol=old_sol_source, btc=btc_source)
    summary = {'scope': read(OUT/'plan.json')['scope'], 'rows': [],
               'tests': {'command': 'python -m pytest test/test_intrabar_support_gate.py -q',
                         'passed': 6},
               'notes': ['100% current equity compounding; no fees/slippage/leverage.',
                         'BNB changes only the signal-time location gate.',
                         'SOL/BTC jointly change confirmation and execution/protection granularity; not separate attribution.',
                         'Maximum drawdown measured at each native timeframe close.',
                         'Historical explorations, not an untouched holdout.']}
    for asset in ('bnb','sol','btc'):
        location = RUNTIME/runs[asset]['run']
        config = read(location/'config.json')
        metadata = read(location/'metadata.json')
        # Final metadata records the atomically saved completed result hash.
        assert metadata.get('result_hash'), (asset, 'result not fully saved')
        assert metadata['result_hash'] == digest(location/'result.json')
        request = read(OUT/f'{asset}-request.json')['base']
        assert config == request, (asset, 'configuration drift')
        native = read(location/'data.json')
        assert native == read(old_data[asset]), (asset, 'native prices differ from baseline')
        if asset == 'bnb':
            old_config = read(RUNTIME/'657b2b8086588a254442b82b128d34df/config.json')
            assert {k:v for k,v in config['parameters'].items() if k!='support_gate'} == old_config['parameters']
            old_metadata = read(RUNTIME/'657b2b8086588a254442b82b128d34df/metadata.json')
            assert metadata['execution_data_hash'] == old_metadata['execution_data_hash']
            assert metadata['engine_code_hash'] == old_metadata['engine_code_hash']
        result = read(location/'result.json')
        report, trades = result['report'], result['trades']
        assert len(trades) == report['total_trades']
        assert sum(t['profit']>0 for t in trades) == report['wins']
        assert sum(t['profit']<0 for t in trades) == report['losses']
        assert report['total_trades'] == report['wins']+report['losses']+report['breakeven']
        equity = report['initial_cash']*prod(1+t['return_pct']/100 for t in trades)
        assert isclose(equity,report['final_equity'],rel_tol=1e-9)
        assert isclose(report['initial_cash']+sum(t['profit'] for t in trades),equity,rel_tol=1e-9)
        assert isclose(max(p['drawdown_pct'] for p in result['equity']), report['max_drawdown_pct'],abs_tol=1e-8)
        indicators = {i['timestamp']:i for i in result['indicators']}
        step = 3600000 if asset=='btc' else 900000
        indices = {row[0]:i for i,row in enumerate(native)}
        consumed = set()
        for t in trades:
            order = indicators[t['entry_order_signal_time']]
            origin = order['values']['确认起点时间']
            original = indicators[origin]
            assert original['checks']['记录新信号']
            assert original['checks']['原做多信号' if t['side']=='long' else '原做空信号']
            assert origin <= t['entry_order_signal_time'] < t['entry_time']
            parent = t['entry_time']//step*step
            assert indices[parent]-indices[origin] in (1,2), (asset, t['trade_id'], 'outside confirmation window')
            identity = (origin,t['side'])
            assert identity not in consumed, (asset, 'duplicate entry from one original signal')
            consumed.add(identity)
            if asset == 'bnb':
                assert original['checks']['做多位置合适' if t['side']=='long' else '做空位置合适']
        keys = ('return_pct','wins','losses','win_rate','max_drawdown_pct')
        old_report = {k:baseline[asset][k] for k in keys}
        old_report['total_trades'] = baseline[asset].get('total_trades',baseline[asset].get('trades'))
        old_report['breakeven'] = baseline[asset].get('breakeven',baseline[asset].get('flat',0))
        row = dict(asset=asset.upper(),**runs[asset],config=config,
            baseline=old_report,report=report,execution_detail=result.get('execution_detail'),
            baseline_source=str(source[asset].relative_to(ROOT)),baseline_source_hash=digest(source[asset]),
            hashes={k:v for k,v in metadata.items() if k.endswith('_hash')},
            native_rows_equal=True,entry_lineage_checks=len(trades),
            source_folder=str(location),
            exits=dict(Counter(t['exit_reason'] for t in trades)),
            losing_exits=dict(Counter(t['exit_reason'] for t in trades if t['profit']<0)))
        if asset=='bnb':
            row['location_gate_counts'] = dict(
                raw_signals=sum(bool(i['checks']['原做多信号'] or i['checks']['原做空信号']) for i in indicators.values()),
                raw_signals_failing_location=sum(i['checks']['位置检查拦截新信号'] for i in indicators.values()),
                armed=sum(i['checks']['记录新信号'] for i in indicators.values()))
        summary['rows'].append(row)
        print(asset, old_report['return_pct'], '->', report['return_pct'],
              'trades',len(trades),'data+lineage verified',flush=True)
        del result, native, trades, indicators
    with (OUT/'results.json').open('x',encoding='utf-8') as f:
        json.dump(summary,f,ensure_ascii=False,indent=2)


if __name__=='__main__':
    main()
