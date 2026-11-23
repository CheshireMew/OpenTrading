"""Validate saved runs and compare ATR versus high-low smoothing without retuning."""
from datetime import datetime,timezone
from math import isclose

from app.services.local_backtest_strategies import digest
from scripts.cloud_cross_asset_study import DOCS,RUNTIME,ROOT
from scripts.profit_protection_study import read,save


def main():
    r=read(DOCS/'results.json');p=r['plan']
    assert r['status']=='completed' and p==read(DOCS/'plan.json')
    assert digest((DOCS/'plan.json').read_bytes())==r['provenance']['plan_hash']
    assert digest((ROOT/'app/domain/local_backtest.py').read_bytes())==p['engine_hash']
    assert len(p['variants'])==50 and sum(not v['benchmark'] for v in p['variants'].values())==48
    assert len(read(DOCS/'history-inventory.json')['entries'])==280
    for original,s in p['sources'].items():
        assert digest((ROOT/original).read_bytes())==s['sha256']
        assert digest((ROOT/s['path']).read_bytes())==s['sha256']
    manifest=[];previous=[];reused=0
    for asset,d in r['data'].items():
        assert digest((ROOT/d['path']).read_bytes())==d['data_hash']
        assert set(r['results'][asset])==set(p['variants'])
        for key,values in r['results'][asset].items():
            assert set(values)==set(p['periods'][asset])
            assert read(RUNTIME/'configs'/f'{key}.json')==p['variants'][key]
            for period,m in values.items():
                path=RUNTIME/'traces'/asset/f'{key}-{period}.json'
                raw=path.read_bytes();t=read(path)
                assert t['metrics']==m and t['parameters']==p['variants'][key]['parameters']
                assert t['period']==p['periods'][asset][period]
                assert t['provenance']['data_hash']==d['data_hash']
                assert t['provenance']['plan_hash']==r['provenance']['plan_hash']
                assert m['total_trades']==len(t['trades'])==m['wins']+m['losses']+m['breakeven']
                assert m['wins']==sum(v['profit']>0 for v in t['trades'])
                assert m['losses']==sum(v['profit']<0 for v in t['trades'])
                assert isclose(sum(v['profit'] for v in t['trades']),m['profit'],rel_tol=1e-10,abs_tol=1e-6)
                assert isclose(m['return_pct'],(m['final_equity']/10000-1)*100,abs_tol=1e-7)
                assert isclose(t['equity'][-1]['equity'],m['final_equity'],abs_tol=1e-7)
                assert all(a['timestamp']<b['timestamp'] for a,b in zip(t['equity'],t['equity'][1:]))
                if m['total_trades']:
                    assert isclose(m['win_rate'],100*m['wins']/m['total_trades'],abs_tol=1e-8)
                if m.get('old_two_year_exact') or m.get('old_two_year_metrics_equal'):
                    previous.append(dict(asset=asset,version=key,trace=m.get('old_two_year_exact'),metrics_only=bool(m.get('old_two_year_metrics_equal'))))
                reused+=bool(m['reused_trace'])
                manifest.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=digest(raw),bytes=len(raw)))
        for period,rank in r['rankings'][asset].items():
            assert rank==sorted((k for k,v in p['variants'].items() if not v['benchmark']),key=lambda k:(-r['results'][asset][k][period]['return_pct'],k))
        print(f'{asset}: {len(r["results"][asset])} versions verified',flush=True)
    assert len(manifest)==r['simulations']==950 and len(previous)==50
    atr={}
    for asset in ['eth','btc']:
        atr[asset]={}
        for period in ['full','recent']:
            a=read(RUNTIME/'traces'/asset/f'initial__ema31_atr-{period}.json')
            b=read(RUNTIME/'traces'/asset/f'initial__ema31_range-{period}.json')
            sig=lambda x:{(v['timestamp'],v['action']) for v in x['signals']}
            sa,sb=sig(a),sig(b)
            atr[asset][period]=dict(atr_signals=len(sa),range_signals=len(sb),shared=len(sa&sb),
                atr_only=len(sa-sb),range_only=len(sb-sa),trades_exact=a['trades']==b['trades'],
                atr_return=a['metrics']['return_pct'],range_return=b['metrics']['return_pct'])
    receipt=read(DOCS/'project-runs.json')
    assert len(receipt['runs'])==6 and all(v['verified'] for v in receipt['runs'].values())
    save(DOCS/'trace-manifest.json',manifest)
    save(DOCS/'verification.json',dict(status='passed',verified_at=datetime.now(timezone.utc).isoformat(),versions=48,benchmarks=2,
        period_results=950,reused_previous_six_year_traces=reused,new_simulations=950-reused,previous_two_year_checks=previous,
        formal_project_replays=6,atr_range_comparison=atr,tests=read(DOCS/'test-results.json'),
        frozen_sources_unchanged=True,trade_accounting_and_rankings_verified=True))
    print(dict(verified=950,reused=reused,previous_checks=len(previous),project_replays=6,atr=atr),flush=True)


if __name__=='__main__':
    main()
