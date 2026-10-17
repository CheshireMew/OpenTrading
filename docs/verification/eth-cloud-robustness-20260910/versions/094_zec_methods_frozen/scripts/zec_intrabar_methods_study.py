"""Frozen, single-factor ZEC comparisons over existing project snapshots."""
import argparse
from collections import Counter
from contextlib import redirect_stdout,redirect_stderr
import json
from statistics import mean

from app.domain.local_backtest import Bar,simulate
from app.domain.cloud_trade_attribution import calendar_returns,periods
from app.domain.backtest_history import align_execution_bars
from app.infra.db import build_database_runtime
from app.infra.research_files import read_json,file_hash
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import load_strategy,validate_parameters
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_width_reentry_study import ROOT,keep
from scripts.local_backtest_worker import execute

OUT=ROOT/'docs/verification/zec-intrabar-methods-20260913'
BASE_ID='2a0c67e629a77db26e664880bab12d44'
BASE=ROOT/'.heimdall_runtime/local_backtests'/BASE_ID
SOURCE=ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
FINE=ROOT/'.heimdall_runtime/cloud-timeframe-20260911/data/zec-5m.json'
FROZEN_FINE=OUT/'execution-data.json'
STEP=1800000
VARIANTS=[('wick','突破整根信号K线',{'confirmation_level':2}),
          ('direction','只顺过去6根中心方向',{'direction_filter':True}),
          ('width_stop','1.5倍平滑振幅止损，限制0.5%至2%',{'stop_method':1}),
          ('atr_stop','1.5倍ATR14止损，限制0.5%至2%',{'stop_method':2}),
          ('retry','止损后突破止损K线极值，最多重进一次',{'stop_reentry':True}),
          ('fine_control','5分钟成交核对，仍30分钟更新保护',{}),
          ('fine_protect','5分钟成交核对，每5分钟更新保护',{})]


class FrozenBacktests(LocalBacktestService):
    def prepare(self,command):
        config,source,metadata=super().prepare(command)
        original=read_json(BASE/'config.json')
        for k in ('symbol','timeframe','start','end','initial_cash','position_pct','data_gap_policy'):
            if config[k]!=original[k]: raise ValueError(f'冻结范围不同：{k}')
        if metadata['strategy']['warmup_bars']!=650: raise ValueError('预热范围不同')
        metadata.update(data_hash=file_hash(BASE/'data.json'),input_data_run=BASE_ID)
        if config.get('execution_timeframe'):
            metadata.update(execution_data_hash=file_hash(FROZEN_FINE),execution_source=str(FROZEN_FINE.relative_to(ROOT)))
        return config,source,metadata

    def _create(self,config,source,metadata,parent_id=None,data=None,identifier=None,*,execution_data=None):
        data=(BASE/'data.json').read_bytes() if data is None else data
        if config.get('execution_timeframe') and execution_data is None: execution_data=FROZEN_FINE.read_bytes()
        return super()._create(config,source,metadata,parent_id,data,identifier,execution_data=execution_data)


def prepare(studies):
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'study.json').exists(): return
    config=read_json(BASE/'config.json');rows=read_json(BASE/'data.json');old=read_json(BASE/'result.json')
    expected=read_json(ROOT/'docs/verification/zec-intrabar-no-stop-20260913/results.json')['results']['entry_only']
    assert file_hash(BASE/'result.json')==expected['result_hash'] and file_hash(BASE/'data.json')==expected['data_hash']
    m,s=load_strategy(SOURCE);p=validate_parameters(s,config['parameters'])
    replay=simulate([Bar(*b) for b in rows],m,p,warmup=650,step_ms=STEP)
    parity={k:replay[k]==old[k] for k in ('report','trades','signals','fills','equity','levels')}
    keep(OUT/'baseline-parity.json',dict(checks=parity,baseline=BASE_ID,data_hash=file_hash(BASE/'data.json'),
        result_hash=file_hash(BASE/'result.json'),source_hash=file_hash(SOURCE),engine_hash=file_hash(ROOT/'app/domain/local_backtest.py')))
    if not all(parity.values()): raise ValueError(parity)
    fine_meta=read_json(ROOT/'docs/verification/cloud-timeframe-20260911/data.json')['zec']['5m']
    assert file_hash(FINE)==fine_meta['data_hash']
    fine=[b for b in read_json(FINE) if rows[650][0]<=b[0]<=rows[-1][0]+STEP-300000]
    keep(FROZEN_FINE,fine)
    _,alignment=align_execution_bars([Bar(*b) for b in rows[650:]],[Bar(*b) for b in fine],STEP,300000)
    keep(OUT/'fine-data-check.json',dict(**alignment,fine_hash=file_hash(FROZEN_FINE),original_fine_hash=file_hash(FINE)))
    cases=[dict(id='baseline',name='当前原版：实体确认＋1%止损',variant='baseline',period='ZEC七年已见历史',
        role='exploration',previously_seen=True,command=config,reuse_run=BASE_ID)]
    for cid,name,changes in VARIANTS:
        command={**config,'strategy':SOURCE.stem,'parameters':validate_parameters(s,{**p,**changes})}
        if cid.startswith('fine_'): command.update(execution_timeframe='5m',intrabar_profit_protection=cid=='fine_protect')
        cases.append(dict(id=cid,name=name,variant=cid,period='ZEC七年已见历史',role='exploration',previously_seen=True,command=command))
    plan=dict(title='ZEC七年：逐项检验入场过滤、波动止损、重进与盘中保护',family='ema_cloud',
        parent='b32c488762b447c4a1f82bfbb3b23aba',objective='按用户要求分别测试上一轮提出的方法，明确哪些改善、哪些没有。',
        change_reason='原亏损诊断后，用户要求实际检验提出的每种方法。',
        decision_rule='前五种各只改对应因素，与当前原版比七年收益；保护频率只在相同5分钟成交数据的两组之间比较。',
        stop_rule='固定七次新运行后停止，不按结果再调倍数、阈值或组合。',max_new_runs=7,cases=cases,
        questions=[dict(id=k,text=v) for k,v in [
            ('wick','实体突破改为整根高低点突破是否改善？'),('direction','顺过去6根中心方向入场是否改善？'),
            ('width_stop','平滑振幅止损是否改善？'),('atr_stop','ATR止损是否改善？'),
            ('retry','初始止损后再突破极值，重进一次是否改善？'),
            ('protection','保持相同细周期成交数据，更频繁更新利润保护是否改善？'),
            ('execution','细周期成交核对本身改变多少结果，数据和信号是否保持因果一致？')]])
    keep(OUT/'plan.json',plan);keep(OUT/'preview.json',studies.preview_summary(plan))
    state=studies.create(plan);keep(OUT/'study.json',state)
    print(json.dumps(dict(study_id=state['id'],parity=parity,fine_match=alignment['matched'],fallback=alignment['fallback']),ensure_ascii=False),flush=True)


def run(studies,identifier):
    s=studies.submit(identifier)
    if s['errors']: raise ValueError(s['errors'])
    for case,rid,task in studies.case_runs(identifier):
        if case['reuse_run'] or task['status']=='completed': continue
        repo=studies.backtests.repository
        if not repo.patch(rid,allowed={'queued'},status='preparing'): raise ValueError(f'{rid}已被领取，请查状态')
        print('开始 '+case['name']+' '+rid,flush=True)
        try:
            with (studies.backtests.directory(rid)/'run.log').open('a',encoding='utf8') as log,redirect_stdout(log),redirect_stderr(log):
                execute(studies.backtests,rid)
        except Exception as exc:
            repo.patch(rid,allowed={'preparing','running'},status='failed',error=str(exc));raise
        t=repo.get(rid);assert t['status']=='completed'
        print(json.dumps(dict(case=case['id'],**{k:t['report'][k] for k in ('return_pct','total_trades','wins','losses','win_rate')}),ensure_ascii=False),flush=True)


def analyze(studies,identifier):
    rows=read_json(BASE/'data.json');times=[int(b[0]) for b in rows];idx={t:i for i,t in enumerate(times)}
    results={};rawchecks=None
    for case,rid,task in studies.case_runs(identifier):
        studies.verify_run(task);folder=studies.backtests.directory(rid);r=read_json(folder/'result.json')
        trades=r['trades'];observations={x['timestamp']:x for x in r['indicators']}
        checks=[(x['timestamp'],x['checks']['原做多信号'],x['checks']['原做空信号']) for x in r['indicators']]
        if rawchecks is None: rawchecks=checks
        else: assert checks==rawchecks
        lineage=[];used=Counter()
        for t in trades:
            posted=t['entry_order_signal_time'];v=observations[posted]['values']
            origin=int(v.get('最初信号时间') or v['确认起点时间']); retry=bool(v.get('重进委托',0))
            used[(origin,t['side'])]+=1
            assert used[(origin,t['side'])] <= (2 if case['id']=='retry' else 1)
            bar_time=t['entry_time']//STEP*STEP
            assert times[idx[posted]+1]==bar_time
            wait=idx[bar_time]-idx[int(v['确认起点时间'])]
            if not retry: assert wait in (1,2)
            assert t['entry_trigger']==v['下根突破入场价']
            if case['id']=='direction': assert t['direction']*v['中心线过去6根变化']>0
            if case['id']=='wick':
                signal_bar=rows[idx[int(v['确认起点时间'])]]
                assert v['信号原始价位']==(signal_bar[2] if t['side']=='long' else signal_bar[3])
            if retry:
                target_bar=rows[idx[int(v['确认起点时间'])]]
                assert v['信号原始价位']==(target_bar[2] if t['side']=='long' else target_bar[3])
                earlier=[x for x in trades if x['entry_time']<t['entry_time'] and x['exit_time']//STEP*STEP==target_bar[0] and x['side']==t['side']]
                assert earlier and earlier[-1]['exit_reason']=='stop_loss'
                assert not any(observations[ts]['checks']['原做空信号' if t['side']=='long' else '原做多信号'] for ts in times[idx[target_bar[0]]:idx[posted]+1])
            lineage.append(dict(trade_id=t['trade_id'],origin=origin,posted=posted,entry_time=t['entry_time'],retry=retry,
                side=t['side'],target=v['信号原始价位'],trigger=t['entry_trigger'],return_pct=t['return_pct'],exit_reason=t['exit_reason']))
        keep(OUT/f'{case["id"]}-lineage.json',lineage)
        retries=[t for t,l in zip(trades,lineage) if l['retry']]
        risk=[s['stop_loss_pct'] for s in r['signals'] if s.get('order_type')=='stop_entry' and s['status']=='executed']
        assert len(risk)==len(trades)
        if case['id'] in ('width_stop','atr_stop'): assert all(.5<=x<=2 for x in risk)
        else: assert all(x==1 for x in risk)
        results[case['id']]=dict(name=case['name'],run_id=rid,parameters=case['config']['parameters'],report=r['report'],
            annual=calendar_returns(r['equity'],rows,periods(r['equity'][0]['timestamp'],r['equity'][-1]['timestamp'],'year')),
            exits=dict(Counter(t['exit_reason'] for t in trades)),loss_exits=dict(Counter(t['exit_reason'] for t in trades if t['profit']<0)),
            mean_win_pct=mean(t['return_pct'] for t in trades if t['profit']>0),mean_loss_pct=mean(t['return_pct'] for t in trades if t['profit']<0),
            worst_trade_pct=min(t['return_pct'] for t in trades),protection_loss_count=sum(t['profit']<0 and t['exit_reason']=='profit_protection' for t in trades),
            entry_bar_ambiguous=sum(t['entry_bar_ambiguous'] for t in trades),
            initial_stop_pct=dict(min=min(risk),max=max(risk),mean=mean(risk)),
            retry=dict(trades=len(retries),wins=sum(t['profit']>0 for t in retries),losses=sum(t['profit']<0 for t in retries),
                       mean_return_pct=mean(t['return_pct'] for t in retries) if retries else None),
            checked_entries=len(lineage),raw_signal_checks_equal=True,execution_detail=r.get('execution_detail'),
            result_hash=file_hash(folder/'result.json'),data_hash=task['metadata']['data_hash'],strategy_hash=task['metadata']['strategy_hash'],
            chart=f'http://127.0.0.1:4173/research/backtests?run={rid}&view=chart&theme=light&tz=8')
        if case['id'].startswith('fine_'):
            results[case['id']]['execution_data_hash']=task['metadata']['execution_data_hash']
        print(json.dumps(dict(case=case['id'],**{k:results[case['id']][k] for k in ('report','loss_exits','mean_win_pct','mean_loss_pct','retry','execution_detail')}),ensure_ascii=False),flush=True)
    keep(OUT/'results.json',dict(study_id=identifier,results=results,
        note='前五个改法与baseline比；fine_protect只与fine_control比保护频率，两者使用完全相同细周期行情；所有历史已见。'))


def finalize(studies,identifier):
    if studies.state(identifier)[4]=='completed': return
    for name,file in [('rules','RULES.md'),('parity','baseline-parity.json'),('data','fine-data-check.json'),
                      ('results','results.json'),('conclusions','README.md'),('tests','test-results.json')]:
        if name not in studies.state(identifier)[2]:studies.attach(identifier,name,OUT/file,name)
    for answer in read_json(OUT/'answers.json'):
        if answer['question'] not in studies.state(identifier)[1]:studies.answer(identifier,answer)
    state=studies.complete(identifier);keep(OUT/'completion.json',state)
    print(state['status'],state['cases'],'未答问题',len(state['unanswered']))


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','analyze','finalize']);action=p.parse_args().action
    db=build_database_runtime(settings);studies=ResearchStudyService(FrozenBacktests(db))
    try:
        if action=='prepare': prepare(studies)
        else:globals()[action](studies,read_json(OUT/'study.json')['id'])
    finally:db.dispose()


if __name__=='__main__':main()
