"""Frozen, single-factor ZEC comparisons over existing project snapshots."""
import argparse
from collections import Counter
from contextlib import redirect_stdout,redirect_stderr
import json
from dataclasses import asdict
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
        note='原周期成交的各改法与baseline比；fine_protect只与fine_control比保护频率，两者使用完全相同细周期行情；所有历史已见。'))


def recover(studies,identifier):
    """Recover only fully computed/hash-verified results after a DB write failure."""
    recovered=[]
    for case,rid,task in studies.case_runs(identifier):
        if not task or task['status']!='failed': continue
        folder=studies.backtests.directory(rid);metadata=read_json(folder/'metadata.json')
        assert case['id'].startswith('fine_') and 'slice(' in task['error']
        for file,key in [('result.json','result_hash'),('data.json','data_hash'),('strategy.py','strategy_hash'),('execution_data.json','execution_data_hash')]:
            assert file_hash(folder/file)==metadata[key]
        result=read_json(folder/'result.json');rows=read_json(folder/'data.json')
        repo=studies.backtests.repository
        for kind in ('trades','fills','equity','levels','indicators','candles','signals'):
            assert repo.records(rid,kind,0,1)['total']==0
        assert repo.patch(rid,allowed={'failed'},status='running',error=None,metadata=metadata)
        assert repo.finish(rid,result,[asdict(Bar(*row)) for row in rows],metadata)
        recovered.append(dict(run_id=rid,case=case['id'],result_hash=metadata['result_hash'],
            reason='修复持久层将execution_detail汇总字典误当成逐笔列表；仅补存已完整计算且哈希一致的结果，无重算。'))
    keep(OUT/'persistence-recovery.json',recovered)
    print('已补存',len(recovered),'个完整结果')


def report(studies,identifier):
    """Save concise answers from the frozen results; no additional backtests."""
    results=read_json(OUT/'results.json')['results']
    b=results['baseline'];w=results['width_stop'];a=results['atr_stop']
    s=results['fine_control'];f=results['fine_protect'];retry=results['retry']['retry']
    conclusions={
        'wick':('reject','突破整根信号K线没有改善：七年收益从+364.30%降到-78.01%，胜率从47.96%降到45.09%。交易减少，但平均每笔收益也转负。'),
        'direction':('reject','顺过去6根中心线方向过滤，没有提高累计收益：+334.98%低于原版+364.30%。交易从4445笔减少到3912笔，胜率略升至48.54%，但不足以抵消减少的盈利机会。'),
        'width_stop':('keep','1.5倍平滑振幅止损、限制0.5%至2%，累计收益+481.81%，胜率55.78%，最大回撤39.28%；三项都优于固定1%。平均初始止损1.48%，平均亏损单扩大到-1.33%；不是所有年份都改善，2026年至9月10日为-32.19%。本次未加固定1.48%对照，尚不能拆开随波动调整与平均放宽止损各自的作用。'),
        'atr_stop':('keep','1.5倍ATR14止损、限制0.5%至2%，累计收益+450.73%，胜率55.82%，最大回撤39.23%，优于固定1%原版；累计收益略低于平滑振幅版本。平均初始止损1.49%，不能据此认定ATR有独特优势。'),
        'retry':('reject',f'止损后突破止损K线高低点、每个原信号最多重进一次，没有改善：累计收益-89.86%。实际重进{retry["trades"]}笔，{retry["wins"]}笔赚、{retry["losses"]}笔亏，平均每笔{retry["mean_return_pct"]:+.2f}%。重进还改变了后续可参与的交易，不能把它当作原版简单追加几笔交易。'),
        'protection':('keep','同样使用5分钟行情核对成交，仅把保护更新从30分钟改为5分钟，累计收益从+458.90%升到+582.26%，胜率48.20%升到50.93%，最大回撤40.56%降到34.61%。利润保护退出却亏损从91笔降到29笔；平均盈利单从+1.14%缩到+1.05%，改善来自整体取舍，未做到每笔都赚更多。2026年至9月10日仍亏24.40%。'),
        'execution':('keep','原版只细化成交数据，累计收益从+364.30%变为+458.90%，同根先后不明从252笔降到45笔；这属于成交估计变化，不能算作策略优化收益。122354根30分钟可匹配完整5分钟行情，300根回退原30分钟。全部8组原始突破信号一致，每笔确认时间、预先挂单价位和同一信号成交次数均通过核对。')}
    scope='ZEC/USDT（Binance现货行情用于多空模拟），30分钟信号，2019-09-10至2026-09-10；EMA144，原门槛1.2W、不追3W，信号后两根盘中突破实体，浮盈1%启动保护、回吐35%。'
    limitation='已见历史的固定规则比较，未检验未见数据；全仓复利、不加杠杆、不计手续费和滑点。前五种改法使用原30分钟保守成交，细周期两组另行配对；5分钟仍非逐笔行情。'
    answers=[]
    for key,(decision,conclusion) in conclusions.items():
        cases=['fine_control','fine_protect'] if key=='protection' else ['baseline','fine_control'] if key=='execution' else ['baseline',key]
        answers.append(dict(question=key,decision=decision,conclusion=conclusion,scope=scope,limitation=limitation,
                            evidence=['artifact:results']+['case:'+cid for cid in cases]))
    keep(OUT/'answers.json',answers)
    log=(OUT/'tests.log').read_text(encoding='utf-8-sig')
    assert '97 passed' in log and 'failed' not in log.lower()
    keep(OUT/'test-results.json',dict(passed=97,exit_code=0,log='tests.log',
        command='python -m pytest -q test/test_local_backtest_engine.py test/test_intrabar_stop_entry.py test/test_intrabar_no_fixed_stop.py test/test_local_backtest_service.py test/test_research_studies.py test/test_zec_intrabar_methods.py',
        coverage=['原引擎及盘中确认兼容','无固定止损','研究记录与服务','细周期完整性及因果顺序','重进次数和反向取消','波动止损边界','细周期快照复跑及篡改拦截','细周期结果持久化'],
        baseline_parity='baseline-parity.json',full_history_entry_audit={k:v['checked_entries'] for k,v in results.items()}))
    lines=['# ZEC：哪些改法有用，哪些没有','',
        '**本次有改善的是两种波动止损，以及更及时更新利润保护。整根突破、中心方向过滤和单次重进，没有提高七年累计收益。**','',scope,'',
        '共8组：保留已有原版，新增7次回测；所有规则在运行前固定，未追加调参或组合。每笔全部本金复投，不加杠杆，不计手续费和滑点。','',
        '| 方法 | 七年收益 | 交易数 | 赚钱 | 亏钱 | 持平 | 胜率 | 最大回撤 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for cid in ['baseline','wick','direction','width_stop','atr_stop','retry','fine_control','fine_protect']:
        v=results[cid];r=v['report']
        lines.append(f'| [{v["name"]}]({v["chart"]}) | {r["return_pct"]:+.2f}% | {r["total_trades"]} | {r["wins"]} | {r["losses"]} | {r["breakeven"]} | {r["win_rate"]:.2f}% | {r["max_drawdown_pct"]:.2f}% |')
    lines+=['','最后两组单独比较。+364.30%→+458.90%来自细化成交数据；+458.90%→+582.26%才是本次改变保护更新频率的比较。不能把两步一起算成保护规则的功劳。','']
    lines += [item['conclusion']+'\n' for item in answers]
    lines += ['## 逐年收益','', '2019年从9月10日起，2026年截至9月10日，均不是全年；按连续账户年初年末权益计算，年中不重置本金。','',
              '| 年份 | 原版 | 整根突破 | 中心方向 | 振幅止损 | ATR止损 | 重进 | 5分钟成交/30分钟保护 | 5分钟成交/5分钟保护 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    order=['baseline','wick','direction','width_stop','atr_stop','retry','fine_control','fine_protect']
    for i,year in enumerate(b['annual']):
        lines.append('| '+year['label']+' | '+' | '.join(f'{results[cid]["annual"][i]["return_pct"]:+.2f}%' for cid in order)+' |')
    lines += ['','## 解释和保留范围','',
        '波动止损平均约1.48%—1.49%，比原1%宽。它减少了止损次数，也让仍然失败的交易亏得更多。本轮结果支持保留这一候选，但没有证明改善必然来自波动适应，也不能从同一段已见历史证明未来有效。','',
        '更快保护并非逐笔实时执行：每根5分钟收盘才更新，下一根开始生效。300根细行情缺失或与30分钟不匹配的K线继续采用原30分钟处理；不匹配列表原样留档。最大回撤仍按30分钟收盘权益计算。','',
        '整根突破和重进分别有467、589笔同根成交先后不明，继续沿用原保守处理，因此否定的是本次具体规则与这套成交假设下的结果；本轮未擅自补跑细周期版本。','',
        '全部策略副本、完整原始行情、逐笔交易、订单、指标和资金曲线均已保存；旧版本未覆盖。研究ID：'+identifier+'。','',
        '- [预先固定的规则](RULES.md)、[计划与参数](plan.json)、[逐项答案](answers.json)、[结构化结果](results.json)。',
        '- [原版逐笔完全一致检查](baseline-parity.json)、[细周期数据核对](fine-data-check.json)、[自动检查记录](test-results.json)。',
        '- 每组的 `*-lineage.json` 记录原信号、委托、成交和重进来源；表内名称可打开项目K线图。',
        '- 完整结果目录：`.heimdall_runtime/local_backtests/<run_id>/`；各 `run_id` 保存在 results.json 中。',
        '- 细周期结果第一次写入数据库时发现汇总字典误当成逐笔列表的问题，已修复并通过服务复跑测试。已计算结果经哈希核对后补存，没有重算或改收益：[恢复记录](persistence-recovery.json)。','']
    path=OUT/'README.md'
    content='\n'.join(lines)
    if path.exists():assert path.read_text(encoding='utf-8')==content
    else:path.write_text(content,encoding='utf-8')
    print('已保存逐项结论、逐年结果和97项自动检查记录')


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
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','analyze','report','finalize','recover']);action=p.parse_args().action
    db=build_database_runtime(settings);studies=ResearchStudyService(FrozenBacktests(db))
    try:
        if action=='prepare': prepare(studies)
        else:globals()[action](studies,read_json(OUT/'study.json')['id'])
    finally:db.dispose()


if __name__=='__main__':main()
