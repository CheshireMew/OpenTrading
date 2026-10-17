"""Fixed close-vs-intrabar comparison; reuses existing six-year data and worker."""
import argparse
from collections import Counter
import json
from app.domain.local_backtest import Bar, simulate
from app.domain.cloud_trade_attribution import periods, calendar_returns
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json, file_hash
from app.services.local_backtest_strategies import load_strategy, validate_parameters
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_width_reentry_study import ROOT, BASE, BASE_ID, STEP, FrozenDataBacktests, keep, run

OUT=ROOT/'docs/verification/eth-intrabar-confirmation-20260913'
SOURCE=ROOT/'strategies/trend_cloud_intrabar_confirmation_v1.py'
PREVIOUS=ROOT/'docs/verification/eth-signal-confirmation-20260913/results.json'
VARIANTS=[('close', '突破信号收盘价',1,0,'close_unlimited'),
          ('wick', '突破信号最高／最低价',2,0,'wick_unlimited'),
          ('body', '第2或第3根突破信号实体',3,2,'body_two_bars')]


def prepare(studies):
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'study.json').exists(): return read_json(OUT/'study.json')
    old=read_json(BASE/'result.json');rows=read_json(BASE/'data.json');config=read_json(BASE/'config.json')
    m,s=load_strategy(ROOT/'strategies/trend_cloud_parameters_v4.py')
    replay=simulate([Bar(*r) for r in rows],m,validate_parameters(s,config['parameters']),warmup=650,step_ms=STEP)
    checks={k:old[k]==replay[k] for k in ('report','trades','signals','fills','equity','levels')}
    keep(OUT/'baseline-parity.json',dict(checks=checks,baseline=BASE_ID,data_hash=file_hash(BASE/'data.json'),
         engine_hash=file_hash(ROOT/'app/domain/local_backtest.py'),report=replay['report']))
    if not all(checks.values()): raise ValueError(checks)
    print('新增盘中委托后，原版六年逐笔重放完全一致',flush=True)
    old_cases=read_json(PREVIOUS)['results']
    cases=[dict(id='baseline',name='原版直接入场',variant='baseline',period='六年已见历史',role='exploration',previously_seen=True,command=config,reuse_run=BASE_ID)]
    _,spec=load_strategy(SOURCE)
    for key,label,level,wait,oldkey in VARIANTS:
        rid=old_cases[oldkey]['run_id']
        cases.append(dict(id=f'{key}_at_close',name=f'等收盘：{label}',variant=f'{key}_at_close',period='六年已见历史',role='exploration',previously_seen=True,
                          command=read_json(ROOT/'.heimdall_runtime/local_backtests'/rid/'config.json'),reuse_run=rid))
        for policy in (0,1):
            p=validate_parameters(spec,dict(confirmation_level=level,max_wait_bars=wait,entry_bar_assumption=policy))
            cid=f'{key}_touch_{policy}'
            cases.append(dict(id=cid,name=f'盘中：{label}（同根先后假设{policy}）',variant=cid,period='六年已见历史',role='exploration',previously_seen=True,
                              command={**config,'strategy':SOURCE.stem,'parameters':p}))
    plan=dict(title='ETH 六年：积累信号后的盘中突破入场',family='ema55_cloud',parent=read_json(PREVIOUS)['study_id'],
              objective='把后续收盘确认改为预先挂价、盘中触发，检查是否减少等待代价并增加收益。',
              change_reason='用户要求价格突破原信号价位即入场，不再等后续 K 线收盘。',
              decision_rule='比较原版、已有三种收盘确认和三种盘中确认；只对同根入场止损的未知先后顺序做两种执行假设，不挑收益高的假设充当事实。',
              stop_rule='完成三个价位、两种成交先后假设的六次运行后停止，不扩展参数或标的。',
              max_new_runs=6,cases=cases,questions=[dict(id=k,text=v) for k,v in [
                  ('close','信号收盘价盘中突破，是否比等收盘和原版更好？'),
                  ('wick','信号最高最低价盘中突破，是否更好？'),
                  ('body','第2或第3根盘中突破信号实体，是否更好？'),
                  ('execution','盘中成交和同根止损顺序是否影响结论，是否仍然单次使用信号？')]])
    keep(OUT/'plan.json',plan);keep(OUT/'preview.json',studies.preview_summary(plan))
    state=studies.create(plan);keep(OUT/'study.json',state)
    print(state['id'],flush=True)
    return state


def analyze(studies,identifier):
    rows=read_json(BASE/'data.json'); times=[int(r[0]) for r in rows];index={t:i for i,t in enumerate(times)}
    old=read_json(BASE/'result.json')
    old_origins={(times[index[t['entry_time']]-1],t['side']):t for t in old['trades']}
    results={}
    for case,rid,task in studies.case_runs(identifier):
        studies.verify_run(task)
        folder=studies.backtests.directory(rid);r=read_json(folder/'result.json');lineage=[];used=set()
        if '_touch_' in case['id']:
            observations={o['timestamp']:o for o in r['indicators']}
            for t in r['trades']:
                posted=t['entry_order_signal_time'];v=observations[posted]['values'];origin=int(v['确认起点时间'])
                identity=(origin,t['side']);assert identity not in used;used.add(identity)
                entry_index=index[t['entry_time']];bar=rows[entry_index];d=1 if t['side']=='long' else -1
                assert index[posted]+1==entry_index and entry_index>index[origin]
                n=entry_index-index[origin]
                limit=case['config']['parameters']['max_wait_bars']
                assert not limit or n<=limit
                assert t['entry_trigger']==v['下根突破入场价'] and t['entry_worst_price']==v['下根追价上限']
                expected=bar[1] if d*(bar[1]-t['entry_trigger'])>=0 else t['entry_trigger']
                assert t['entry_price']==expected and bar[3]<=expected<=bar[2]
                assert t['entry_worst_price'] is None or d*(expected-t['entry_worst_price'])<=0
                target=v['信号原始价位'];assert d*(t['entry_trigger']-target)>0
                opposite='原做空信号' if d==1 else '原做多信号'
                assert not any(observations[ts]['checks'][opposite] for ts in times[index[origin]+1:index[posted]+1])
                previous=old_origins.get(identity)
                lineage.append(dict(trade_id=t['trade_id'],origin=origin,order_posted=posted,entry_time=t['entry_time'],
                    side=t['side'],waited_bars=n,target=target,trigger=t['entry_trigger'],actual_entry=t['entry_price'],
                    entry_phase=t['entry_phase'],return_pct=t['return_pct'],exit_reason=t['exit_reason'],
                    entry_bar_ambiguous=t['entry_bar_ambiguous'],entry_bar_close=bar[4],
                    close_did_not_confirm=d*(bar[4]-target)<=0,
                    baseline_trade_id=previous['trade_id'] if previous else None,
                    baseline_return_pct=previous['return_pct'] if previous else None))
            keep(OUT/f'{case["id"]}-lineage.json',lineage)
        results[case['id']]=dict(name=case['name'],run_id=rid,parameters=case['config']['parameters'],report=r['report'],
            annual=calendar_returns(r['equity'],rows,periods(r['equity'][0]['timestamp'],r['equity'][-1]['timestamp'],'year')),
            exits=dict(Counter(t['exit_reason'] for t in r['trades'])),
            entry_bar_ambiguous=sum(t.get('entry_bar_ambiguous',False) for t in r['trades']),
            same_bar_initial_stops=sum(t['entry_time']==t['exit_time'] and t['exit_reason']=='stop_loss' for t in r['trades']),
            order_statuses=dict(Counter(s['status'] for s in r['signals'] if s.get('order_type')=='stop_entry')),
            checked_trades=len(lineage),unique_origins=len(used),close_did_not_confirm=sum(x['close_did_not_confirm'] for x in lineage),
            mean_wait_bars=sum(x['waited_bars'] for x in lineage)/len(lineage) if lineage else None,
            fills_at_open=sum(x['entry_phase']=='open' for x in lineage),fills_intrabar=sum(x['entry_phase']=='intrabar' for x in lineage),
            old_winner_now_loser=sum(x['baseline_return_pct'] is not None and x['baseline_return_pct']>0 and x['return_pct']<0 for x in lineage),
            old_loser_now_winner=sum(x['baseline_return_pct'] is not None and x['baseline_return_pct']<0 and x['return_pct']>0 for x in lineage),
            source_hash=task['metadata']['strategy_hash'],data_hash=task['metadata']['data_hash'],result_hash=file_hash(folder/'result.json'),
            chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart&theme=light&tz=8')
    keep(OUT/'results.json',dict(study_id=identifier,results=results,note='相同 ETH/USDT 15分钟六年已见历史；全仓复利；不计手续费滑点；成交先后是假设，非逐笔行情验证。'))
    for key,v in results.items():
        print(json.dumps(dict(case=key,**{x:v['report'][x] for x in ('return_pct','total_trades','wins','losses','win_rate')},ambiguous=v['entry_bar_ambiguous']),ensure_ascii=False),flush=True)


def finalize(studies,identifier):
    if studies.state(identifier)[4]=='completed': print('研究已完成');return
    for name,file in [('rules','RULES.md'),('parity','baseline-parity.json'),('results','results.json'),('conclusions','README.md')]:
        if name not in studies.state(identifier)[2]:studies.attach(identifier,name,OUT/file,name)
    for answer in read_json(OUT/'answers.json'):
        if answer['question'] not in studies.state(identifier)[1]:studies.answer(identifier,answer)
    state=studies.complete(identifier);keep(OUT/'completion.json',state)
    print(state['status'],state['cases'],'未答问题',len(state['unanswered']))


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','analyze','finalize']);action=p.parse_args().action
    db=build_database_runtime(settings);studies=ResearchStudyService(FrozenDataBacktests(db))
    try:
        if action=='prepare':prepare(studies)
        else: {'run':run,'analyze':analyze,'finalize':finalize}[action](studies,read_json(OUT/'study.json')['id'])
    finally:db.dispose()


if __name__=='__main__':main()
