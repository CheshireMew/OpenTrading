"""Frozen historical representatives, through OpenTrading market service and simulator."""
import argparse
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from math import isclose
from pathlib import Path

from app.domain.backtest_history import validate_observed_bars
from app.domain.local_backtest import simulate
from app.infra.db import build_database_runtime
from app.infra.persistence.market.kline_store import KlineStore
from app.services.market.exchange_gateway import ExchangeGateway
from app.services.market.market_data_service import MarketDataService
from app.services.market.symbol_catalog import get_market_symbol_source
from app.services.local_backtest_strategies import digest, environment, load_strategy, validate_parameters
from config import settings
from scripts.cloud_joint_study import gap_sensitivity, token
from scripts.cloud_strategy_versions import snapshot
from scripts.profit_protection_study import ROOT, read, save, metrics
from scripts.trend_cloud_study import stamp

DOCS = ROOT/'docs/verification/cloud-cross-asset-20260911'
RUNTIME = ROOT/'.opentrading_runtime/cloud-cross-asset-20260911'
OLD = ROOT/'docs/verification'
STEP = 900000
END = '2026-09-10T00:00:00Z'
BATCHES = {
    'initial': ('eth-cloud-two-year-20260910/results.json', 'trend_cloud_comparison'),
    'experiments': ('eth-cloud-two-year-20260910/experiments-results.json', 'trend_cloud_experiments'),
    'protection': ('eth-profit-protection-20260910/results.json', 'trend_cloud_profit_protection'),
    'robustness': ('eth-cloud-robustness-20260910/results.json', 'trend_cloud_robustness_v1'),
    'manual': ('eth-cloud-manual-20260910/results.json', 'trend_cloud_manual_v1'),
    'entry': ('eth-cloud-entry-20260910/results.json', 'trend_cloud_entry_v2'),
    'context': ('eth-cloud-context-20260910/results.json', 'trend_cloud_context_v3'),
    'parameters': ('eth-cloud-parameters-20260910/results.json', 'trend_cloud_parameters_v4'),
    'joint': ('eth-cloud-joint-six-year-20260911/results.json', 'trend_cloud_parameters_v4'),
}
# Chosen before obtaining or testing BTC; these are existing versions, not new rules.
SELECTED = {
    'initial': None,
    'experiments': ['fixed_band', 'hlc3_atr16', 'hl2_atr14', 'hl2_atr16',
                    'ema31_atr__distance2', 'high_low_ema__distance2', 'high_low_ema__confirm2',
                    'high_low_ema__stop2', 'high_low_ema__target4', 'high_low_ema__stop2_target4', 'high_low_ema__trail3'],
    'robustness': ['anchor', 'no_protection', 'trend96', 'efficiency20', 'spacing4', 'alternate'],
    'manual': ['confirm2', 'retest8'],
    'entry': ['few_crossings', 'no_spike', 'structure_break', 'strong_close'],
    'context': ['support', 'support_room', 'support_touch', 'momentum', 'trend', 'all_three'],
    'parameters': ['baseline', 'activate0', 'activate300', 'stop100'],
    'joint': ['c55_w31_t0p4_d2_a2_g50_s1', 'c55_w31_t0p4_d2_a2_g50_s0', 'c65_w40_t0p8_d2_a3_g50_s0'],
}


def identifier(batch, key):
    return batch+'__'+key


def config_rows():
    rows = []
    for batch, (file, source) in BATCHES.items():
        old = read(OLD/file)
        variants = old.get('variants', old.get('plan', {}).get('variants', {}))
        if batch == 'initial':
            variants = {k: dict(name=v['name'], parameters=dict(variant=k, long_only=False)) for k, v in old['results'].items()}
        _, spec = load_strategy(ROOT/f'strategies/{source}.py')
        for key, v in variants.items():
            p = {**v['parameters'], 'record_indicators': False}
            if batch == 'experiments':
                p['fixed_pct'] = old['fixed_width_pct_from_first_year']
            p = validate_parameters(spec, p)
            selected = batch in SELECTED and (SELECTED[batch] is None or key in SELECTED[batch])
            name = v.get('name', key)
            if batch == 'experiments' and '__' in key:
                name = ('ATR候选：' if key.startswith('ema31_atr__') else '高低价通道：')+name
            if batch == 'joint':
                name = {'c55_w31_t0p4_d2_a2_g50_s1': '此前六年第一名：EMA55／门槛0.4／止损1%',
                        'c55_w31_t0p4_d2_a2_g50_s0': '六年第一名的无初始止损对照',
                        'c65_w40_t0p8_d2_a3_g50_s0': '此前两年组合第一名：EMA65／宽度40／保护3%与50%'} .get(key, key)
            rows.append(dict(id=identifier(batch,key), batch=batch, old_key=key, name=name, source=f'strategies/{source}.py',
                             source_record=f'docs/verification/{file}', parameters=p, selected=selected,
                             benchmark=batch == 'initial' and key in ('buy_hold','cash')))
    return rows


def prepare():
    if (DOCS/'plan.json').exists():
        raise ValueError('Plan already frozen; do not overwrite')
    rows = config_rows()
    variants = {r['id']: r for r in rows if r['selected']}
    assert len(rows) == 280 and len(variants) == 50
    snapshots = {}
    for source in sorted({r['source'] for r in variants.values()}):
        src = ROOT/source
        dest = RUNTIME/'sources'/src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        snapshots[source] = dict(path=dest.relative_to(ROOT).as_posix(), sha256=digest(src.read_bytes()))
    pairs = [
        ('ATR换成平滑高低差', 'initial__ema31_atr', 'initial__ema31_range'),
        ('ATR候选增加不追价', 'initial__ema31_atr', 'experiments__ema31_atr__distance2'),
        ('高低价通道增加不追价', 'initial__high_low_ema', 'experiments__high_low_ema__distance2'),
        ('启动利润保护', 'robustness__no_protection', 'robustness__anchor'),
        ('EMA55启动利润保护', 'parameters__activate0', 'parameters__baseline'),
        ('EMA55保护启动2%改3%', 'parameters__baseline', 'parameters__activate300'),
        ('EMA55增加1%止损', 'parameters__baseline', 'parameters__stop100'),
        ('六年优胜版增加1%止损', 'joint__c55_w31_t0p4_d2_a2_g50_s0', 'joint__c55_w31_t0p4_d2_a2_g50_s1'),
    ]
    for key in ['confirm2','stop2','target4','stop2_target4','trail3']:
        pairs.append(('高低价通道：'+key, 'initial__high_low_ema', 'experiments__high_low_ema__'+key))
    for key in ['trend96','efficiency20','spacing4','alternate']:
        pairs.append(('保护版：'+key, 'robustness__anchor', 'robustness__'+key))
    for batch in ['manual','entry','context']:
        for key in SELECTED[batch]:
            pairs.append((variants[identifier(batch,key)]['name'], 'robustness__efficiency20', identifier(batch,key)))
    periods = {}
    for asset, first in [('eth',2020), ('btc',2018)]:
        periods[asset] = {f'y{year}': [f'{year}-09-10T00:00:00Z', f'{year+1}-09-10T00:00:00Z'] for year in range(first,2026)}
        periods[asset].update(full=[f'{first}-09-10T00:00:00Z',END], recent=['2024-09-10T00:00:00Z',END])
        if asset == 'btc':
            periods[asset]['same_six'] = ['2020-09-10T00:00:00Z',END]
    plan = dict(created_at=datetime.now(timezone.utc).isoformat(), variants=variants, sources=snapshots, periods=periods,
                pairs=[dict(name=n, baseline=a, changed=b) for n,a,b in pairs],
                strategy_versions=48, benchmarks=2, historical_entries=280, annual_start_month_day='09-10',
                initial_cash=10000, position_pct=100, warmup=650, timeframe='15m', data_gap_policy='observed_bars',
                engine_hash=digest((ROOT/'app/domain/local_backtest.py').read_bytes()), environment=environment(),
                historical_fixed_width_pct=next(r['parameters']['fixed_pct'] for r in rows if r['id']=='experiments__fixed_band'),
                execution='Use original version-specific entry/exit rules and project simulator. Close decisions, next observed open. No fees/slippage/leverage. Full current equity per trade, reinvested. Each annual run starts flat and closes at end; continuous full runs carry across years. Raw original Pine TP/SL labels are not orders.',
                ranking='Return only, separately within ETH6, BTC8 and BTC6. No win-rate or drawdown gate. Cash and buy-hold shown separately.',
                freeze='All 50 configurations fixed before BTC fetch/results. No BTC-specific adjustment. ETH history has already been seen; BTC transfer is retrospective cross-asset evidence, not proof against every form of overfitting.',
                coverage='All 12 early strategy versions plus 36 later representatives and 2 benchmarks. 280 historical entries include parameter sweeps and repeated baselines, not 280 independent ideas. Omitted entries retained in inventory; no new exhaustive grid.',
                reused='Only identical source/parameters/period/data/engine traces can replace a calculation; verify previous two-year trade traces where available.',
                gaps='Project market service only; validate original timestamps and OHLC. Re-fetch reported gaps once; never manufacture candles. Hold state across remaining internal gaps; missing intragap path unknown.',
                nominal_simulations=len(variants)*sum(len(x) for x in periods.values()))
    save(DOCS/'history-inventory.json', dict(entries=rows, counts={b:sum(r['batch']==b for r in rows) for b in BATCHES}))
    save(DOCS/'plan.json',plan)
    for k,v in variants.items():
        save(RUNTIME/'configs'/f'{k}.json',v)
    snapshot('029-frozen-cross-asset-representatives', [Path(__file__), DOCS/'plan.json',DOCS/'history-inventory.json',
             ROOT/'docs/verification/strategy-selection-20260911/REVIEW.md', ROOT/'app/domain/local_backtest.py',
             *[ROOT/s for s in snapshots]])
    print(f'Frozen {len(variants)} versions, {plan["nominal_simulations"]} period comparisons',flush=True)


def fetch():
    plan=read(DOCS/'plan.json')
    receipt=read(DOCS/'data.json') if (DOCS/'data.json').exists() else {}
    for asset,symbol in [('eth','ETH/USDT'),('btc','BTC/USDT')]:
        if asset in receipt:
            assert digest((ROOT/receipt[asset]['path']).read_bytes()) == receipt[asset]['data_hash']
            continue
        start,end=map(stamp,plan['periods'][asset]['full'])
        if asset=='eth':
            old=read(OLD/'eth-cloud-joint-six-year-20260911/plan.json')
            path=ROOT/'.opentrading_runtime/cloud-joint-six-year-20260911/data.json'
            raw=path.read_bytes()
            assert digest(raw)==old['data_hash']
            rows=json.loads(raw)
        else:
            db=build_database_runtime(settings)
            source=get_market_symbol_source(symbol)
            market=MarketDataService(exchange_gateway=ExchangeGateway(source.exchange_id),kline_store=KlineStore(database_runtime=db))
            def date(t): return datetime.fromtimestamp(t/1000,timezone.utc)
            combined={}
            try:
                first=start-plan['warmup']*STEP
                span=60*86400000
                for i,a in enumerate(range(first,end,span)):
                    b=min(a+span,end)
                    part=RUNTIME/'fetch'/f'btc-{i:03}.json'
                    if part.exists():
                        chunk=read(part)
                        assert chunk['start']==a and chunk['end']==b
                        values=chunk['rows']
                    else:
                        result=market.load_ohlcv_range(symbol,'15m',date(a),date(b-1))
                        values=result.rows
                        if not values:
                            raise ValueError(f'No BTC data in chunk {i}')
                        save(part,dict(start=a,end=b,rows=values))
                    combined.update({int(r[0]):r for r in values})
                    print(f'BTC data {i+1}/49: {len(combined)} candles, through {date(b).isoformat()}',flush=True)
                rows=sorted(combined.values(),key=lambda x:x[0])
                # Gaps include any incomplete chunk boundary; use the SAME project service for the recheck.
                holes=[]
                cursor=first
                for row in rows:
                    if row[0]>cursor: holes.append((cursor,int(row[0])))
                    cursor=int(row[0])+STEP
                if cursor<end: holes.append((cursor,end))
                checks=[]
                for a,b in holes:
                    values=market.load_live_ohlcv_range(symbol,'15m',date(a),date(b-1)).rows
                    combined.update({int(r[0]):r for r in values})
                    if values: market.kline_store.save(source.storage_symbol,'15m',values)
                    checks.append(dict(start=a,end=b,returned=len(values)))
                    print(f'BTC gap recheck: {(b-a)//STEP} absent, {len(values)} returned',flush=True)
                save(DOCS/'btc-gap-recheck.json',checks)
                rows=sorted(combined.values(),key=lambda x:x[0])
                path=RUNTIME/'btc-data.json'
                path.write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
                raw=path.read_bytes()
            finally:
                db.dispose()
        bars,gaps=validate_observed_bars(rows,start,end,STEP,plan['warmup'],stamp(END))
        # All separate comparison windows must have exact boundaries and full contiguous warmup.
        times=[b.timestamp for b in bars]
        for p,(a,b) in plan['periods'][asset].items():
            lo,hi=bisect_left(times,stamp(a)),bisect_left(times,stamp(b))
            validate_observed_bars(rows[lo-650:hi],stamp(a),stamp(b),STEP,650,stamp(END))
        receipt[asset]=dict(symbol=symbol,start=plan['periods'][asset]['full'][0],end=END,
                            path=path.relative_to(ROOT).as_posix(),data_hash=digest(raw),gaps=gaps,candles=len(bars),
                            missing_bars=sum(g['missing_bars'] for g in gaps),source='Project MarketDataService / Binance spot / KlineStore')
        save(DOCS/'data.json',receipt)
        print(f'{asset}: validated {len(bars)} candles; {len(gaps)} gaps',flush=True)


_state=None


def init_worker(plan,data):
    global _state
    cache={}
    assert digest((ROOT/'app/domain/local_backtest.py').read_bytes())==plan['engine_hash']
    for source,snapshot_info in plan['sources'].items():
        assert digest((ROOT/snapshot_info['path']).read_bytes())==snapshot_info['sha256']
    for asset,record in data.items():
        raw=(ROOT/record['path']).read_bytes()
        assert digest(raw)==record['data_hash']
        bars,gaps=validate_observed_bars(json.loads(raw),stamp(record['start']),stamp(record['end']),STEP,650,stamp(END))
        assert gaps==record['gaps']
        cache[asset]=(bars,[b.timestamp for b in bars])
    joint=read(OLD/'eth-cloud-joint-six-year-20260911/results.json')
    _state=(plan,data,cache,{token(v['parameters']):k for k,v in joint['plan']['variants'].items()})


def old_recent(v):
    batch,key=v['batch'],v['old_key']
    if batch=='initial':
        r=read(OLD/BATCHES[batch][0])['results'][key]
        return ROOT/f'.opentrading_runtime/local_backtests/{r["run_id"]}/result.json'
    if batch=='experiments': return ROOT/f'.opentrading_runtime/eth-cloud-two-year-20260910/experiment-{key}-full.json'
    prefix={'robustness':'cloud-robustness','manual':'cloud-manual','entry':'cloud-entry','context':'cloud-context','parameters':'cloud-parameters','joint':'cloud-joint-six-year'}[batch]
    date='20260911' if batch=='joint' else '20260910'
    suffix='recent' if batch=='joint' else 'full'
    return ROOT/f'.opentrading_runtime/{prefix}-{date}/{key}-{suffix}.json'


def compare_trace(actual,expected):
    for k in ['report','trades','signals']:
        assert actual[k]==expected[k], f'Historical {k} changed'
    if 'equity' in expected:
        assert [(p['timestamp'],p['equity']) for p in actual['equity']]==[(p['timestamp'],p['equity']) for p in expected['equity']], 'Equity changed'


def calculate(task):
    asset,key=task
    plan,data,cache,joint_keys=_state
    v=plan['variants'][key]
    source_info=plan['sources'][v['source']]
    bars,times=cache[asset]
    result={}
    for period,(start,end) in plan['periods'][asset].items():
        provenance=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),data_hash=data[asset]['data_hash'],
                        source_hash=source_info['sha256'],engine_hash=plan['engine_hash'])
        path=RUNTIME/'traces'/asset/f'{key}-{period}.json'
        if path.exists():
            trace=read(path)
            assert trace['provenance']==provenance and trace['parameters']==v['parameters']
            result[period]=trace['metrics']
            continue
        reused=None
        # Source equality is mandatory, not just similarly named rules.
        if asset=='eth' and v['source']=='strategies/trend_cloud_parameters_v4.py':
            other=joint_keys.get(token(v['parameters']))
            op={'full':'full','recent':'recent',**{f'y{y}':f'y{y-2019}' for y in range(2020,2026)}}[period]
            if other:
                prior=ROOT/f'.opentrading_runtime/cloud-joint-six-year-20260911/{other}-{op}.json'
                candidate=read(prior)
                oldfiles=candidate['provenance']['files']
                assert candidate['parameters']==v['parameters'] and candidate['period']==[start,end]
                assert candidate['provenance']['data_hash']==data[asset]['data_hash']
                assert oldfiles[v['source']]==source_info['sha256'] and oldfiles['app/domain/local_backtest.py']==plan['engine_hash']
                actual=candidate
                reused=prior.relative_to(ROOT).as_posix()
        if reused is None:
            lo,hi=bisect_left(times,stamp(start)),bisect_left(times,stamp(end))
            assert lo>=650 and times[lo]==stamp(start) and times[hi-1]+STEP==stamp(end)
            module,spec=load_strategy(ROOT/source_info['path'])
            actual=simulate(bars[lo-650:hi],module,validate_parameters(spec,v['parameters']),warmup=650,
                            step_ms=STEP,initial_cash=plan['initial_cash'],position_pct=plan['position_pct'])
        assert isclose(actual['report']['profit'],sum(t['profit'] for t in actual['trades']),rel_tol=1e-10,abs_tol=1e-6)
        m=metrics(actual)
        m.pop('daily_equity',None)
        m.pop('monthly_returns',None)
        m['gap_sensitivity']=gap_sensitivity(actual['trades'],[g for g in data[asset]['gaps'] if g['start']>=stamp(start) and g['end']<=stamp(end)])
        if asset=='eth' and period=='recent':
            prior=old_recent(v)
            if prior.exists():
                compare_trace(actual,read(prior))
                m['old_two_year_exact']=prior.relative_to(ROOT).as_posix()
            else:
                # Older robustness runner keeps a differently named trace; return equality remains a useful check.
                old=read(OLD/BATCHES[v['batch']][0])['results'][v['old_key']]
                old=old['full']
                assert isclose(old['return_pct'],m['return_pct'],abs_tol=1e-8)
                m['old_two_year_metrics_equal']=True
        m['reused_trace']=reused
        trace={k:actual[k] for k in ['report','trades','signals']}
        trace['equity']=[dict(timestamp=p['timestamp'],equity=p['equity']) for p in actual['equity']]
        trace.update(metrics=m,provenance=provenance,parameters=v['parameters'],period=[start,end])
        save(path,trace)
        result[period]=m
    return asset,key,result


def study(workers):
    plan,data=read(DOCS/'plan.json'),read(DOCS/'data.json')
    assert set(data)=={'eth','btc'}
    provenance=dict(plan_hash=digest((DOCS/'plan.json').read_bytes()),data_hash=digest((DOCS/'data.json').read_bytes()),
                    runner_hash=digest(Path(__file__).read_bytes()),environment=environment())
    path=DOCS/'results.json'
    output=read(path) if path.exists() else dict(plan=plan,data=data,provenance=provenance,results={'eth':{},'btc':{}},status='running')
    assert output['provenance']==provenance
    with ProcessPoolExecutor(max_workers=workers,initializer=init_worker,initargs=(plan,data)) as pool:
        futures=[pool.submit(calculate,(asset,k)) for asset in ['eth','btc'] for k in plan['variants']]
        for i,f in enumerate(as_completed(futures),1):
            asset,k,value=f.result()
            output['results'][asset][k]=value
            save(path,output)
            print(f'{i}/100 {asset} {k}: {value["full"]["return_pct"]:+.2f}%',flush=True)
    output['rankings']={asset:{p:sorted((k for k,v in plan['variants'].items() if not v['benchmark']),
                                    key=lambda k:(-output['results'][asset][k][p]['return_pct'],k)) for p in periods}
                        for asset,periods in plan['periods'].items()}
    output['paired_changes']={asset:{p:[dict(**pair,return_change_pct_points=output['results'][asset][pair['changed']][p]['return_pct']-output['results'][asset][pair['baseline']][p]['return_pct']) for pair in plan['pairs']]
                                    for p in periods} for asset,periods in plan['periods'].items()}
    output.update(status='completed',completed_at=datetime.now(timezone.utc).isoformat(),
                  simulations=sum(len(values) for rs in output['results'].values() for values in rs.values()))
    assert output['simulations']==plan['nominal_simulations']
    save(path,output)
    print('Completed; ETH leader '+output['rankings']['eth']['full'][0]+'; BTC leader '+output['rankings']['btc']['full'][0],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','fetch','study'])
    parser.add_argument('--workers',type=int,default=6)
    args=parser.parse_args()
    {'prepare':prepare,'fetch':fetch,'study':lambda:study(args.workers)}[args.action]()
