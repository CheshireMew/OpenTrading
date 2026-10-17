"""ZEC seven-year, frozen 2x2 comparison using project data, service and worker."""
import argparse
from bisect import bisect_left
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
import json
from statistics import mean, median

from app.domain.local_backtest import Bar, simulate
from app.domain.cloud_trade_attribution import periods, calendar_returns
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash, sha
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_width_reentry_study import ROOT, keep
from scripts.local_backtest_worker import execute

OUT = ROOT/'docs/verification/zec-intrabar-no-stop-20260913'
OLD_DOCS = ROOT/'docs/verification/cloud-timeframe-20260911'
OLD_TRACE = ROOT/'.heimdall_runtime/cloud-timeframe-20260911/traces/zec/full1-30m-full.json'
FULL_DATA = ROOT/'.heimdall_runtime/cloud-timeframe-20260911/data/zec-30m.json'
DATA = OUT/'data.json'
STEP = 1800000
START, END = '2019-09-10T00:00:00Z', '2026-09-10T00:00:00Z'
CONFIG = dict(symbol='ZEC/USDT', timeframe='30m', start=START, end=END,
              initial_cash=10000, position_pct=100, data_gap_policy='observed_bars')
CASES = [('baseline', '原版：直接入场＋1%止损', False, 1),
         ('entry_only', '只改入场：第2或第3根盘中突破实体＋1%止损', True, 1),
         ('no_stop_only', '只取消固定止损：原入场', False, 0),
         ('combined', '两项一起改：盘中确认＋取消固定止损', True, 0)]


class FrozenZecBacktests(LocalBacktestService):
    def prepare(self, command):
        config, source, metadata = super().prepare(command)
        for k, v in CONFIG.items():
            if config[k] != v:
                raise ValueError(f'本次固定的 ZEC 七年范围不一致：{k}')
        if metadata['strategy']['warmup_bars'] != 650:
            raise ValueError('预热必须是650根')
        metadata.update(data_hash=file_hash(DATA), input_data_source=str(DATA.relative_to(ROOT)),
                        original_full_data_hash=file_hash(FULL_DATA))
        return config, source, metadata

    def _create(self, config, source, metadata, parent_id=None, data=None, identifier=None):
        data = DATA.read_bytes() if data is None else data
        if sha(data) != metadata['data_hash']:
            raise ValueError('冻结数据校验失败')
        return super()._create(config, source, metadata, parent_id, data, identifier)


def prepare(studies):
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'study.json').exists():
        return read_json(OUT/'study.json')
    meta = read_json(OLD_DOCS/'data.json')['zec']['30m']
    assert file_hash(FULL_DATA) == meta['data_hash']
    saved = next(x for x in read_json(OLD_DOCS/'verification.json')['manifest']
                 if ROOT/x['path'] == OLD_TRACE)
    assert file_hash(OLD_TRACE) == saved['hash']
    rows = read_json(FULL_DATA)
    times = [int(r[0]) for r in rows]
    start, end = [int(datetime.fromisoformat(s).timestamp()*1000) for s in (START, END)]
    i, j = bisect_left(times, start), bisect_left(times, end)
    assert i >= 650 and times[i] == start and times[i]-times[i-650] == 650*STEP
    rows = rows[i-650:j]
    keep(DATA, rows)
    old = read_json(OLD_TRACE)
    assert [int(datetime.fromisoformat(s).timestamp()*1000) for s in old['period']] == [start, end]
    source = ROOT/'strategies/trend_cloud_parameters_v4.py'
    m, spec = load_strategy(source)
    p = validate_parameters(spec, {k:v for k,v in old['parameters'].items() if k in spec.parameters})
    replay = simulate([Bar(*r) for r in rows], m, p, warmup=650, step_ms=STEP)
    checks = {k:replay[k] == old[k] for k in ('report','trades','signals')}
    checks['equity'] = [{k:x[k] for k in ('timestamp','equity')} for x in replay['equity']] == old['equity']
    keep(OUT/'baseline-parity.json', dict(checks=checks, original_trace=str(OLD_TRACE.relative_to(ROOT)),
         original_trace_hash=file_hash(OLD_TRACE), full_data_hash=file_hash(FULL_DATA),
         data_hash=file_hash(DATA), source_hash=file_hash(source),
         engine_hash=file_hash(ROOT/'app/domain/local_backtest.py'), report=replay['report']))
    if not all(checks.values()):
        raise ValueError(checks)
    history = read_json(OLD_DOCS/'results.json')
    keep(OUT/'selection.json', dict(chosen='full1/30m/full', period=[START,END],
         parameters=old['parameters'], original_report=old['report'],
         reason='用户要求多年最高的EMA通道版本；纠正先前选择最近两年冠军。',
         seven_year_ranking=sorted([dict(variant=k, timeframe=tf, return_pct=x['full']['return_pct'])
             for k,tfs in history['results']['zec'].items() for tf,x in tfs.items()
             if tf != '1d'], key=lambda x:x['return_pct'], reverse=True),
         previous_choice=dict(variant='base/30m', recent_return_pct=history['results']['zec']['base']['30m']['recent']['return_pct'],
                              seven_year_return_pct=history['results']['zec']['base']['30m']['full']['return_pct']),
         source_results_hash=file_hash(OLD_DOCS/'results.json')))
    cases=[]
    for cid, name, confirmed, stop in CASES:
        path=ROOT/'strategies'/('trend_cloud_intrabar_confirmation_v2.py' if confirmed else source.name)
        _, s = load_strategy(path)
        parameters = {k:v for k,v in p.items() if k in s.parameters}
        parameters['initial_stop_pct'] = stop
        if confirmed:
            parameters.update(confirmation_level=3, max_wait_bars=2, price_tick=.01, entry_bar_assumption=0)
        else:
            parameters['record_indicators'] = True
        cases.append(dict(id=cid, name=name, variant=cid, period='2019-09-10至2026-09-10 七年已见历史',
            role='exploration', previously_seen=True,
            command={**CONFIG, 'strategy':path.stem, 'parameters':validate_parameters(s,parameters)}))
    plan=dict(title='ZEC七年EMA144：盘中确认与取消固定止损的四组对照', family='ema_cloud',
        objective='分清第2或第3根盘中突破实体、取消1%初始止损，分别及一起对收益的影响。',
        change_reason='用户明确要求两个因素分别测试，并纠正应选多年收益最高的EMA通道原版。',
        decision_rule='对同一七年、同一数据做2×2对照；只报告这四组结果，不继续搜索参数。',
        stop_rule='四组完成并核对逐笔成交和退出后停止。', max_new_runs=4, cases=cases,
        questions=[dict(id=k,text=v) for k,v in [
            ('entry','单独把入场改为第2或第3根盘中突破实体，收益有何变化？'),
            ('stop','单独取消固定止损，收益有何变化？'),
            ('combined','两项一起改是否优于原版，改善主要来自哪项？'),
            ('execution','是否只在后两根确认、不重复使用信号，并保留反向退出和利润保护？')]])
    keep(OUT/'plan.json',plan)
    keep(OUT/'preview.json',studies.preview_summary(plan))
    state=studies.create(plan)
    keep(OUT/'study.json',state)
    print(json.dumps(dict(study_id=state['id'], parity=checks, baseline_return=old['report']['return_pct']),ensure_ascii=False),flush=True)


def run(studies, identifier):
    submitted=studies.submit(identifier)
    if submitted['errors']:
        raise ValueError(submitted['errors'])
    for case,rid,task in studies.case_runs(identifier):
        if task['status']=='completed':
            continue
        repo=studies.backtests.repository
        if not repo.patch(rid,allowed={'queued'},status='preparing'):
            raise ValueError(f'{rid} 已被领取，先查状态，不重复运行')
        print('开始 '+case['name']+' '+rid,flush=True)
        folder=studies.backtests.directory(rid)
        try:
            with (folder/'run.log').open('a',encoding='utf8') as log, redirect_stdout(log), redirect_stderr(log):
                execute(studies.backtests,rid)
        except Exception as exc:
            repo.patch(rid,allowed={'preparing','running'},status='failed',error=str(exc))
            raise
        done=repo.get(rid)
        assert done['status']=='completed' and done['metadata']['data_hash']==file_hash(DATA)
        print(json.dumps(dict(case=case['id'],**{k:done['report'][k] for k in ('return_pct','total_trades','wins','losses')}),ensure_ascii=False),flush=True)


def analyze(studies, identifier):
    rows=read_json(DATA); times=[int(r[0]) for r in rows]; index={t:i for i,t in enumerate(times)}
    results={}
    for case,rid,task in studies.case_runs(identifier):
        studies.verify_run(task)
        folder=studies.backtests.directory(rid); r=read_json(folder/'result.json'); p=case['config']['parameters']
        if case['id']=='baseline':
            old=read_json(OLD_TRACE)
            assert all(r[k]==old[k] for k in ('report','trades','signals'))
            assert [{k:x[k] for k in ('timestamp','equity')} for x in r['equity']]==old['equity']
        lineage=[]; used=set()
        if case['id'] in ('entry_only','combined'):
            obs={o['timestamp']:o for o in r['indicators']}
            for t in r['trades']:
                posted=t['entry_order_signal_time']; v=obs[posted]['values']; origin=int(v['确认起点时间'])
                identity=(origin,t['side']); assert identity not in used; used.add(identity)
                n=index[t['entry_time']]-index[origin]; assert n in (1,2)
                assert index[posted]+1==index[t['entry_time']]
                d=1 if t['side']=='long' else -1; b=rows[index[t['entry_time']]]; sb=rows[index[origin]]
                target=max(sb[1],sb[4]) if d==1 else min(sb[1],sb[4])
                assert target==v['信号原始价位'] and d*(t['entry_trigger']-target)>0
                assert t['entry_trigger']==v['下根突破入场价'] and t['entry_worst_price']==v['下根追价上限']
                expected=b[1] if d*(b[1]-t['entry_trigger'])>=0 else t['entry_trigger']
                assert t['entry_price']==expected and b[3]<=expected<=b[2]
                assert d*(expected-t['entry_worst_price'])<=0
                opposite='原做空信号' if d==1 else '原做多信号'
                assert not any(obs[ts]['checks'][opposite] for ts in times[index[origin]+1:index[posted]+1])
                lineage.append(dict(trade_id=t['trade_id'],origin=origin,posted=posted,entry_time=t['entry_time'],
                    waited_bars=n,signal_body_edge=target,trigger=t['entry_trigger'],entry_price=expected,
                    side=t['side'],exit_reason=t['exit_reason'],return_pct=t['return_pct'],
                    entry_phase=t['entry_phase'],entry_bar_ambiguous=t['entry_bar_ambiguous']))
            keep(OUT/f'{case["id"]}-lineage.json',lineage)
        trades=r['trades']
        if p['initial_stop_pct']==0:
            assert not any(t['exit_reason']=='stop_loss' for t in trades)
        results[case['id']]=dict(name=case['name'],run_id=rid,parameters=p,report=r['report'],
            annual=calendar_returns(r['equity'],rows,periods(r['equity'][0]['timestamp'],r['equity'][-1]['timestamp'],'year')),
            exits={reason:dict(count=len(ts),wins=sum(t['profit']>0 for t in ts),losses=sum(t['profit']<0 for t in ts),
                               mean_return_pct=mean(t['return_pct'] for t in ts))
                for reason in sorted({t['exit_reason'] for t in trades}) for ts in [[t for t in trades if t['exit_reason']==reason]]},
            mean_win_pct=mean(t['return_pct'] for t in trades if t['profit']>0),
            mean_loss_pct=mean(t['return_pct'] for t in trades if t['profit']<0),
            worst_trade=min(trades,key=lambda t:t['return_pct']),best_trade=max(trades,key=lambda t:t['return_pct']),
            median_hold_hours=median((t['exit_time']-t['entry_time'])/3600000 for t in trades),
            checked_entries=len(lineage),unique_origins=len(used),wait_counts=dict(Counter(x['waited_bars'] for x in lineage)),
            entry_bar_ambiguous=sum(t.get('entry_bar_ambiguous',False) for t in trades),
            data_hash=task['metadata']['data_hash'],strategy_hash=task['metadata']['strategy_hash'],
            result_hash=file_hash(folder/'result.json'),
            chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart&theme=light&tz=8')
        print(json.dumps(dict(case=case['id'],**r['report'],exits=results[case['id']]['exits']),ensure_ascii=False),flush=True)
    base=results['baseline']['report']['return_pct']; entry=results['entry_only']['report']['return_pct']
    stop=results['no_stop_only']['report']['return_pct']; combined=results['combined']['report']['return_pct']
    keep(OUT/'results.json',dict(study_id=identifier,period=[START,END],results=results,
         effect_percentage_points=dict(entry_with_stop=entry-base,entry_without_stop=combined-stop,
             cancel_stop_original_entry=stop-base,cancel_stop_confirmed_entry=combined-entry,combined_vs_original=combined-base),
         note='同一ZEC30分钟七年历史，全仓复利，不计手续费滑点，无杠杆；收益差为百分点，不能当成独立可相加的贡献。'))


def finalize(studies,identifier):
    if studies.state(identifier)[4]=='completed':
        return
    for name,file in [('rules','RULES.md'),('selection','selection.json'),('parity','baseline-parity.json'),
                      ('results','results.json'),('conclusions','README.md')]:
        if name not in studies.state(identifier)[2]: studies.attach(identifier,name,OUT/file,name)
    for answer in read_json(OUT/'answers.json'):
        if answer['question'] not in studies.state(identifier)[1]: studies.answer(identifier,answer)
    state=studies.complete(identifier); keep(OUT/'completion.json',state)
    print(state['status'],state['cases'],'未答问题',len(state['unanswered']))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['prepare','run','analyze','finalize'])
    action=parser.parse_args().action
    db=build_database_runtime(settings); studies=ResearchStudyService(FrozenZecBacktests(db))
    try:
        if action=='prepare': prepare(studies)
        else: globals()[action](studies,read_json(OUT/'study.json')['id'])
    finally:
        db.dispose()


if __name__=='__main__': main()
