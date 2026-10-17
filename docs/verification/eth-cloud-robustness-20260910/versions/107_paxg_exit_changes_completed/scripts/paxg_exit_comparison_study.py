"""Two independent exit changes to the selected PAXG 4h configuration."""
import argparse
from collections import Counter

from app.infra.db import build_database_runtime
from app.infra.research_files import read_json,file_hash
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_strategy_versions import ROOT,snapshot
from scripts.cloud_width_reentry_study import keep
from scripts.intrabar_requested_followups import Frozen
from scripts.paxg_intrabar_combined_study import save_text
from scripts.zec_intrabar_methods_study import run
from scripts import zec_paxg_entry_parameters_study as audit

OUT=ROOT/'docs/verification/paxg-exit-comparison-20260913'
BASE=ROOT/'.heimdall_runtime/local_backtests/97f289b0295f2decd9c7d57c4e795c05'
SOURCE=ROOT/'strategies/trend_cloud_intrabar_exit_v4.py'
OLD=ROOT/'strategies/trend_cloud_intrabar_methods_v3.py'
ENGINE=ROOT/'app/domain/local_backtest.py'


def setup(db):
    return ResearchStudyService(Frozen(db,read_json(BASE/'config.json'),BASE/'data.json',BASE/'execution_data.json'))


def prepare(studies):
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'study.json').exists():return
    cfg=read_json(BASE/'config.json')
    assert file_hash(BASE/'strategy.py')==file_hash(OLD) and file_hash(BASE/'engine.py')==file_hash(ENGINE)
    cases=[]
    for cid,name,change in [('baseline','原版：2%止损＋反向平仓',{}),
                          ('stop4','只把固定止损改为4%',{'initial_stop_pct':4}),
                          ('no_reverse','只取消反向平仓，保留2%止损',{'reverse_exit':False})]:
        command={**cfg,'parameters':{**cfg['parameters'],**change}}
        if cid=='no_reverse':command['strategy']=SOURCE.stem
        c=dict(id=cid,name=name,variant=cid,period='2021-01-22至2026-09-10',role='exploration',previously_seen=True,command=command)
        if cid=='baseline':c['reuse_run']=BASE.name
        cases.append(c)
    plan=dict(title='PAXG最高组：4%止损与取消反向平仓',family='ema_cloud',parent='a3d31cc53e314d309ad3bfde95e78e67',
        objective='两个独立退出改动相对207.76%原版是否提高收益？',
        change_reason='用户要求4%固定止损另测一组，再测取消反向平仓一组；按两个独立改动比较。',
        decision_rule='同一行情、同一期间，比较原版与各单独改法的总收益，胜负、年度和退出原因辅助解释。',
        stop_rule='复用原版，仅新增2次，不叠加两个改法，不继续调参数。',max_new_runs=2,cases=cases,
        questions=[dict(id='stop4',text='固定止损从2%改4%是否改善？'),dict(id='no_reverse',text='保留2%止损，只取消反向平仓是否改善？')])
    rules='''PAXG/USDT，4小时信号，2021-01-22至2026-09-10。原版：EMA55，W=EMA(high-low,50)，突破1.2W，不追1.5W，仅信号第2或第3根盘中突破实体入场；浮盈2%启动、回吐50%，每5分钟收盘更新保护、下一根生效。固定2%止损，原反向信号平仓。原累计收益207.7555078322685%。

新增两组相互独立：stop4只改固定止损4%，保留反向平仓；no_reverse保留固定2%，只取消持仓中的反向信号退出与反手开仓。no_reverse仍计算全部原始信号，但持仓中的新信号不挂入场单，也不排队等以后补入；止损/利润保护退出后，空仓遇到新的原信号才重新等待确认。空仓尚未成交时，反向信号仍取消旧等待、换新方向。测试期末统一平仓。

原版直接复用。stop4复用旧v3策略；no_reverse使用独立v4副本，原v3不改。新开关默认开启时与原版逻辑一致；关闭时同时禁止反向平仓及反手委托，避免移除显式close却被反向入场间接平仓。引擎未改。

三组相同4小时、5分钟行情快照，650根预热；细行情完整且OHLC聚合一致才使用，否则保持原回退处理。每个原信号最多成交一次。全仓复利、不加杠杆、不计手续费滑点。最大回撤按4小时收盘权益计算，5分钟并非逐笔数据。历史已见，不是未见验证。保留每组代码、参数、行情、交易、指标、权益和完整记录。
'''
    save_text(OUT/'RULES.md',rules);keep(OUT/'plan.json',plan)
    keep(OUT/'tests.json',dict(passed=13,command='python -m pytest -q test/test_intrabar_reverse_exit.py test/test_zec_intrabar_methods.py',
        engine_hash=file_hash(ENGINE),source_hash=file_hash(SOURCE),original_source_hash=file_hash(OLD),
        coverage=['默认开关与旧版决策相同','关闭反向退出不会反手或排队开仓','平仓后须新信号','空仓反向取消旧等待','原止损及保护风险配置保留','细周期顺序与旧确认检查']))
    keep(OUT/'study.json',studies.create(plan))
    snapshot('106_paxg_exit_changes_frozen',[SOURCE,OLD,ENGINE,ROOT/'test/test_intrabar_reverse_exit.py',
        ROOT/'scripts/paxg_exit_comparison_study.py']+list(OUT.glob('*.json'))+[OUT/'RULES.md'])
    print('已冻结：原版复用，2次新增',flush=True)


def finish(studies,sid):
    if studies.state(sid)[4]=='completed':return
    audit.OUT=OUT;records={};checks=None;hashes=set();cfg=read_json(BASE/'config.json')
    for c,rid,task in studies.case_runs(sid):
        studies.verify_run(task);folder=studies.backtests.directory(rid)
        r=read_json(folder/'result.json')
        current=[(x['timestamp'],x['checks']['原做多信号'],x['checks']['原做空信号']) for x in r['indicators']]
        if checks is None:checks=current
        else:assert current==checks
        if c['id']=='no_reverse':
            assert all(s['action']!='close' for s in r['signals'])
            assert all(t['exit_reason'] in ('stop_loss','profit_protection','end_of_backtest') for t in r['trades'])
            for i,t in enumerate(r['trades']):
                if i:
                    prior=r['trades'][i-1]
                    assert t['entry_order_signal_time']*1+14400000>prior['exit_time']
        expected={**cfg,'parameters':{**cfg['parameters'],**({'initial_stop_pct':4} if c['id']=='stop4' else {'reverse_exit':False} if c['id']=='no_reverse' else {})}}
        if c['id']=='no_reverse':expected['strategy']=SOURCE.stem
        assert c['config']==expected
        audit.audit_case('paxg',c,rid,task,studies.backtests)
        v=read_json(OUT/'paxg/cases'/f'{c["id"]}.json');records[c['id']]=v
        hashes.add((v['data_hash'],v['execution_data_hash']))
    assert len(hashes)==1
    keep(OUT/'results.json',dict(study_id=sid,results=records))
    keep(OUT/'verification.json',dict(same_raw_signals=True,same_data_hashes=list(hashes),new_runs=2,
        no_reverse_has_no_close_or_reversal=True,entries_checked={k:v['entries_checked'] for k,v in records.items()},
        source_hash=file_hash(SOURCE),engine_hash=file_hash(ENGINE),original_source_hash=file_hash(OLD)))
    b=records['baseline']['report'];answers=[]
    for key in ('stop4','no_reverse'):
        v=records[key];p=v['report'];better=p['return_pct']>b['return_pct']
        text=f'{v["name"]}：收益{b["return_pct"]:+.2f}%→{p["return_pct"]:+.2f}%；{p["total_trades"]}笔，{p["wins"]}赢/{p["losses"]}亏，胜率{p["win_rate"]:.2f}%，最大回撤{p["max_drawdown_pct"]:.2f}%。'+('收益改善。' if better else '收益没有改善。')
        answers.append(dict(question=key,conclusion=text,decision='keep' if better else 'reject',
            evidence=['artifact:results','case:baseline','case:'+key],scope='PAXG4小时、同一2021-01-22至2026-09-10，单因素对照。',
            limitation='全仓复利不计费用，历史已见；未把删掉亏损单当成可实现收益，按项目重新执行。'))
    keep(OUT/'answers.json',answers)
    lines=['# PAXG：固定4%止损、取消反向平仓','']+[a['conclusion']+'\n' for a in answers]+[
        '| 版本 | 收益 | 交易 | 赢 | 亏 | 胜率 | 最大回撤 |','|---|---:|---:|---:|---:|---:|---:|']
    for v in records.values():
        p=v['report'];lines.append(f'| [{v["name"]}]({v["chart"]}) | {p["return_pct"]:+,.2f}% | {p["total_trades"]} | {p["wins"]} | {p["losses"]} | {p["win_rate"]:.2f}% | {p["max_drawdown_pct"]:.2f}% |')
    lines+=['','两种独立改动；取消反向平仓的一组仍是2%止损。参数、周期、数据、利润保护和确认规则均在RULES.md。','',
        '| 年份 | 原版 | 4%止损 | 无反向平仓 |','|---|---:|---:|---:|']
    for i,y in enumerate(records['baseline']['annual']):lines.append('| '+y['label']+' | '+' | '.join(f'{v["annual"][i]["return_pct"]:+.2f}%' for v in records.values())+' |')
    lines+=['','首尾非完整年度。逐年使用连续权益。','',
        '| 版本 | 固定止损退出 | 反向信号退出 | 利润保护退出 | 平均亏损单 | 平均持仓天数 |','|---|---:|---:|---:|---:|---:|']
    for v in records.values():
        x=v['exits'];lines.append(f'| {v["name"]} | {x.get("stop_loss",0)} | {x.get("signal",0)+x.get("reversal",0)} | {x.get("profit_protection",0)} | {v["mean_loss_pct"]:.2f}% | {v["report"]["average_duration_minutes"]/1440:.2f} |')
    lines+=['','全部原始信号保持一致，检查每个信号只成交一次、委托先于成交和固定止损值。取消反向退出的一组未出现反向/信号平仓，并检查后续挂单来自上笔退出后的收盘。原版与固定4%使用旧v3，取消反向版独立v4，旧策略未覆盖。','',
        'results.json记录run_id、完整参数及年度；paxg/lineage保存逐笔确认来源；项目各run_id目录保存行情、策略/引擎、订单、交易、指标、权益。全仓复利，不计手续费滑点。已见历史比较，不能保证未来结果。','']
    save_text(OUT/'README.md','\n'.join(lines))
    for name,file in [('rules','RULES.md'),('results','results.json'),('report','README.md'),('verification','verification.json'),('tests','tests.json')]:
        if name not in studies.state(sid)[2]:studies.attach(sid,name,OUT/file,name)
    for a in answers:
        if a['question'] not in studies.state(sid)[1]:studies.answer(sid,a)
    keep(OUT/'completion.json',studies.complete(sid))
    snapshot('107_paxg_exit_changes_completed',[ROOT/'scripts/paxg_exit_comparison_study.py']+list(OUT.glob('*.json'))+[OUT/'README.md'])
    for a in answers:print(a['conclusion'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run','finish']);a=p.parse_args()
    db=build_database_runtime(settings)
    try:
        studies=setup(db)
        if a.action=='prepare':prepare(studies)
        else:globals()[a.action](studies,read_json(OUT/'study.json')['id'])
    finally:db.dispose()
