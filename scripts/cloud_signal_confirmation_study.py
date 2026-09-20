"""Three predeclared entry-confirmation rules over the frozen ETH six years.

Reuses the project's research service, worker, snapshot adapter and accounting.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from statistics import median

from app.domain.local_backtest import Bar, simulate
from app.domain.cloud_trade_attribution import summary, periods, calendar_returns
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_width_reentry_study import ROOT, BASE, BASE_ID, STEP, FrozenDataBacktests, keep, run

OUT = ROOT/'docs/verification/eth-signal-confirmation-20260913'
SOURCE = ROOT/'strategies/trend_cloud_signal_confirmation_v1.py'
VARIANTS = [
    ('close_unlimited', '不限根数：突破信号收盘价', {'confirmation_level': 1, 'max_wait_bars': 0}),
    ('wick_unlimited', '不限根数：突破信号最高／最低价', {'confirmation_level': 2, 'max_wait_bars': 0}),
    ('body_two_bars', '第2或第3根：突破信号实体', {'confirmation_level': 3, 'max_wait_bars': 2}),
]


def prepare(studies):
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'study.json').exists():
        return read_json(OUT/'study.json')
    original = read_json(BASE/'result.json')
    rows = read_json(BASE/'data.json')
    module, spec = load_strategy(SOURCE)
    replay = simulate([Bar(*r) for r in rows], module,
        validate_parameters(spec, {'confirmation_level': 0, 'record_indicators': False}),
        warmup=650, step_ms=STEP)
    checks = {key: replay[key] == original[key] for key in ('report','trades','signals','fills','equity','levels')}
    keep(OUT/'baseline-parity.json', dict(checks=checks, baseline=BASE_ID, data_hash=file_hash(BASE/'data.json'),
        source_hash=file_hash(SOURCE), engine_hash=file_hash(ROOT/'app/domain/local_backtest.py'), report=replay['report']))
    if not all(checks.values()):
        raise ValueError(f'原版重放不一致：{checks}')
    print('原版完整交易、信号、资金曲线重放一致', flush=True)
    config = read_json(BASE/'config.json')
    cases = [dict(id='baseline', name='原版直接入场', variant='baseline', period='六年已见历史',
        role='exploration', previously_seen=True, command=config, reuse_run=BASE_ID)]
    for key,name,p in VARIANTS:
        cases.append(dict(id=key, name=name, variant=key, period='六年已见历史', role='exploration', previously_seen=True,
            command={**config, 'strategy': SOURCE.stem, 'parameters': validate_parameters(spec,p)}))
    plan = dict(title='ETH 六年：原信号积累后的 K 线确认', family='ema55_cloud',
        parent='54c5eb09288f43179307ff80cd604193',
        objective='比较收盘确认、最高最低确认、不限等待和第2或第3根实体确认，是否减少无效交易并提高收益。',
        change_reason='用户明确要求原信号先积累，后续收盘确认；反向信号重置，并一起测之前的有限根数确认。',
        decision_rule='相同六年数据按总收益比较，同时列交易数、胜负、年度收益、等待时间和原信号对应交易；不根据结果调参。',
        stop_rule='完成三个预先确定版本后停止，不扩大信号条件、参数或标的。', max_new_runs=3, cases=cases,
        questions=[dict(id=k,text=v) for k,v in [
            ('close','不限根数，收盘突破信号收盘价，是否改善？'),
            ('wick','不限根数，收盘突破信号最高或最低价，是否更好？'),
            ('limited','第2或第3根收盘突破信号实体，是否减少损耗？'),
            ('mechanics','是否正确记忆、反向重置、单次消费信号，实际等待多久？')]])
    keep(OUT/'plan.json',plan)
    keep(OUT/'preview.json',studies.preview_summary(plan))
    created=studies.create(plan)
    keep(OUT/'study.json',created)
    return created


def analyze(studies, identifier):
    rows=read_json(BASE/'data.json'); times=[int(r[0]) for r in rows]
    index={t:i for i,t in enumerate(times)}
    original=read_json(BASE/'result.json')
    baseline_by_origin={(times[index[t['entry_time']]-1],t['side']):t for t in original['trades']}
    results={}
    for case,rid,task in studies.case_runs(identifier):
        studies.verify_run(task)
        folder=studies.backtests.directory(rid)
        result=read_json(folder/'result.json')
        observations={o['timestamp']:o for o in result['indicators']}
        lineage=[]; delay=[]; used=set()
        if case['id']!='baseline':
            for t in result['trades']:
                confirm_time=times[index[t['entry_time']]-1]
                observation=observations[confirm_time]; v=observation['values']; checks=observation['checks']
                origin=int(v['确认起点时间']); origin_side=(origin,t['side'])
                assert origin_side not in used
                used.add(origin_side)
                n=index[confirm_time]-index[origin]
                assert n>=1 and n==v['已等待根数']
                if case['config']['parameters']['max_wait_bars']:
                    assert n<=case['config']['parameters']['max_wait_bars']
                assert all(checks[k] for k in ('本次确认入场','收盘突破确认价格','仍在通道对应方向','确认时不追远处'))
                assert t['entry_price']==rows[index[t['entry_time']]][1]
                # No reversal may occur after recording this origin and before confirmation.
                opposite='原做空信号' if t['side']=='long' else '原做多信号'
                assert not any(observations[ts]['checks'][opposite] for ts in times[index[origin]+1:index[confirm_time]+1])
                d=1 if t['side']=='long' else -1
                signal=rows[index[origin]]
                level=case['config']['parameters']['confirmation_level']
                target=signal[4] if level==1 else (signal[2] if d==1 else signal[3]) if level==2 else (max(signal[1],signal[4]) if d==1 else min(signal[1],signal[4]))
                assert target==v['确认价格'] and d*(rows[index[confirm_time]][4]-target)>0
                old=baseline_by_origin.get(origin_side)
                lineage.append(dict(trade_id=t['trade_id'], origin=origin, confirmation=confirm_time,
                    waited_bars=n, confirmation_target=target, side=t['side'],
                    return_pct=t['return_pct'], exit_reason=t['exit_reason'],
                    baseline_trade_id=old['trade_id'] if old else None, baseline_return_pct=old['return_pct'] if old else None,
                    entry_delay_minutes=(t['entry_time']-times[index[origin]+1])/60000,
                    original_next_open=rows[index[origin]+1][1], actual_entry=t['entry_price']))
                delay.append(n)
            keep(OUT/f'{case["id"]}-lineage.json',lineage)
        relevant_baseline=[t for key,t in baseline_by_origin.items() if key in used]
        not_used=[t for key,t in baseline_by_origin.items() if key not in used] if case['id']!='baseline' else []
        checks_count=Counter(k for o in result['indicators'] for k,value in o['checks'].items() if value)
        events=[dict(timestamp=o['timestamp'], values=o['values'], checks=o['checks']) for o in result['indicators']
            if any(o['checks'].get(k) for k in ('记录新信号','反向取消旧等待','等待过期','本次确认入场'))]
        if case['id']!='baseline': keep(OUT/f'{case["id"]}-events.json',events)
        annual=calendar_returns(result['equity'],rows,periods(result['equity'][0]['timestamp'],result['equity'][-1]['timestamp'],'year'))
        results[case['id']]=dict(name=case['name'],run_id=rid,parameters=case['config']['parameters'],report=result['report'],
            annual=annual, exits=dict(Counter(t['exit_reason'] for t in result['trades'])),
            mean_wait_bars=sum(delay)/len(delay) if delay else None,median_wait_bars=median(delay) if delay else None,
            max_wait_bars=max(delay) if delay else None,wait_over_2_bars=sum(n>2 for n in delay),
            event_counts=dict(checks_count),verification=dict(unique_origins=len(used),checked_trades=len(lineage)),
            matched_original=summary(relevant_baseline),unmatched_original=summary(not_used),
            original_signals_not_used=[t['trade_id'] for t in not_used],
            ignored_same_side=sum(s['status']=='ignored_same_side' for s in result['signals']),
            lineage_summary=dict(original_loser_now_wins=sum(x['baseline_return_pct'] is not None and x['baseline_return_pct']<0 and x['return_pct']>0 for x in lineage),
                original_winner_now_loses=sum(x['baseline_return_pct'] is not None and x['baseline_return_pct']>0 and x['return_pct']<0 for x in lineage)),
            source_hash=task['metadata']['strategy_hash'],data_hash=task['metadata']['data_hash'],result_hash=file_hash(folder/'result.json'),
            chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart&theme=light&tz=8')
    keep(OUT/'results.json',dict(study_id=identifier,results=results,
        note='Binance ETH/USDT 15m；2020-09-10—2026-09-10 UTC；原数据快照；全仓复利；无手续费滑点；已见历史。'))
    entry_price_attribution()
    print(json.dumps({k:dict(report=v['report'],mean_wait=v['mean_wait_bars'],max_wait=v['max_wait_bars'],over2=v['wait_over_2_bars'])
        for k,v in results.items()},ensure_ascii=False))


def entry_price_attribution():
    output = {}
    for key, _, _ in VARIANTS:
        path = OUT/f'{key}-lineage.json'
        records = read_json(path)
        matched = [x for x in records if x['baseline_trade_id'] is not None]
        prices = [(1 if x['side']=='long' else -1)*(x['actual_entry']/x['original_next_open']-1)*100 for x in matched]
        output[key] = dict(
            lineage_hash=file_hash(path), matched_trades=len(matched), new_origins=len(records)-len(matched),
            original_mean_return_pct=sum(x['baseline_return_pct'] for x in matched)/len(matched),
            confirmed_mean_return_pct=sum(x['return_pct'] for x in matched)/len(matched),
            less_favorable_entries=sum(p>0 for p in prices), more_favorable_entries=sum(p<0 for p in prices),
            same_price_entries=sum(p==0 for p in prices), mean_entry_displacement_pct=sum(prices)/len(prices))
    keep(OUT/'entry-price-attribution.json', dict(results=output,
        note='同一原信号配对；有向成交价差为做多更高或做空更低的百分比。属于延后入场价差，不是成本；不是退出方式不变的独立归因实验。'))


def finalize(studies,identifier):
    answers=read_json(OUT/'answers.json')
    if studies.state(identifier)[4]=='completed':
        print('研究已完成'); return
    for name,filename in [('rules','RULES.md'),('parity','baseline-parity.json'),('results','results.json'),('entry-prices','entry-price-attribution.json'),('conclusions','README.md')]:
        if name not in studies.state(identifier)[2]: studies.attach(identifier,name,OUT/filename,name)
    for answer in answers:
        if answer['question'] not in studies.state(identifier)[1]: studies.answer(identifier,answer)
    state=studies.complete(identifier); keep(OUT/'completion.json',state)
    print(state['status'],state['cases'],'未答问题',len(state['unanswered']))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run','analyze','finalize'])
    action=parser.parse_args().action
    db=build_database_runtime(settings); studies=ResearchStudyService(FrozenDataBacktests(db))
    try:
        if action=='prepare': print(json.dumps(prepare(studies),ensure_ascii=False))
        else:
            identifier=read_json(OUT/'study.json')['id']
            {'run':run,'analyze':analyze,'finalize':finalize}[action](studies,identifier)
    finally: db.dispose()


if __name__=='__main__': main()
