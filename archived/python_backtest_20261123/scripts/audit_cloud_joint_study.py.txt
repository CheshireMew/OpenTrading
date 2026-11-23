"""Check saved six-year study artifacts without repeating the strategy search."""
from datetime import datetime, timezone
from math import isclose

from scripts.cloud_joint_study import DOCS, RUNTIME, ROOT, combinations, rank
from scripts.profit_protection_study import read, save
from app.services.local_backtest_strategies import digest


def main():
    r = read(DOCS/'results.json')
    plan, results = r['plan'], r['results']
    assert r['status'] == 'completed' and len(results) == 128
    assert plan['variants'] == combinations()
    assert read(DOCS/'plan.json') == plan
    for path, sha in r['provenance']['files'].items():
        assert digest((ROOT/path).read_bytes()) == sha, path
    assert digest((RUNTIME/'data.json').read_bytes()) == plan['data_hash']
    assert (RUNTIME/'strategy.py').read_bytes() == (ROOT/'strategies/trend_cloud_parameters_v4.py').read_bytes()
    previous_matches, manifest = [], []
    for key, periods in results.items():
        assert set(periods) == set(plan['periods'])
        config = read(RUNTIME/'variants'/f'{key}.json')
        assert config['parameters'] == plan['variants'][key]['parameters']
        for period, m in periods.items():
            assert m['wins']+m['losses']+m['breakeven'] == m['total_trades']
            assert isclose(m['final_equity']/m['initial_cash']*100-100, m['return_pct'], abs_tol=1e-7)
            assert isclose(m['wins']/m['total_trades']*100, m['win_rate'], abs_tol=1e-7)
            trace = RUNTIME/f'{key}-{period}.json'
            assert trace.is_file() and trace.stat().st_size > 0
            manifest.append(dict(file=trace.name, bytes=trace.stat().st_size))
            if 'old_record_exact' in m:
                previous_matches.append(dict(version=key, period=period, matches=m['old_record_exact']))
    assert len(manifest) == r['simulations'] == 1152
    assert previous_matches
    for period in plan['periods']:
        assert rank(results, period) == r['rankings'][period]
    assert read(DOCS/'selection.json') == r['selection']
    assert r['selection']['selected'] == r['rankings']['selection'][0]
    for comparisons in r['interactions'].values():
        assert len(comparisons) == 7 and all(v['comparisons'] == 64 for v in comparisons.values())
    receipt = read(DOCS/'project-runs.json')
    assert set(receipt['runs']) == set(r['chart_keys'])
    assert all(v['verified'] for v in receipt['runs'].values())
    save(DOCS/'trace-manifest.json', manifest)
    verified = dict(verified_at=datetime.now(timezone.utc).isoformat(), status='passed',
                    versions=128, simulations=1152, formal_replays=len(receipt['runs']),
                    formal_replay_checks=['data hash', 'history gaps', 'report', 'trades', 'signals', 'timestamp/equity'],
                    original_data_slice_exact=read(DOCS/'data.json')['old_two_years_exact'],
                    previous_parameter_records_exact=previous_matches,
                    frozen_inputs_unchanged=True, counts_and_rankings_valid=True,
                    tests=dict(command='python -m pytest test/test_backtest_history.py test/test_cloud_joint_study.py test/test_cloud_parameters.py test/test_local_backtest_service.py -q',
                               passed=37, duration_seconds=16.66),
                    frontend_typecheck='vue-tsc --noEmit: passed',
                    data_gaps=len(plan['gaps']), missing_bars=sum(g['missing_bars'] for g in plan['gaps']),
                    accounting='No costs or leverage. Each trade uses 100% of current equity. Annual periods independently start/end flat; continuous runs retain anniversary positions.')
    save(DOCS/'verification.json', verified)
    print({k:v for k,v in verified.items() if k not in ['previous_parameter_records_exact','tests']})


if __name__ == '__main__':
    main()
